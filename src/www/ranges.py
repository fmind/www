"""Bounded asynchronous byte-range responses for regular static files."""

from __future__ import annotations

import asyncio
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, cast

from litestar.datastructures import Headers
from litestar.types import ASGIApp, Message, Receive, Scope, Send

# One MiB matches Litestar's file-response default. Smaller reads turn a page
# with several multi-megabyte illustrations into hundreds of thread-pool hops,
# which can starve later static and navigation requests during a full archive
# traversal. Eight concurrent responses still bound buffered file data to 8 MiB.
_CHUNK_SIZE = 1024 * 1024
_MAX_INT64 = (1 << 63) - 1
_MAX_RANGES = 8
_INVALID_RANGE_BODY = b"invalid range\n"
_NO_OVERLAP_BODY = b"invalid range: failed to overlap\n"


class _MalformedRangeError(ValueError):
    """The Range field contains an invalid byte-range specifier."""


class _NoOverlapError(ValueError):
    """The byte-range starts beyond the current representation."""


@dataclass(frozen=True, slots=True)
class _ByteRange:
    start: int
    length: int

    @property
    def end(self) -> int:
        return self.start + self.length - 1

    def content_range(self, size: int) -> str:
        return f"bytes {self.start}-{self.end}/{size}"


def range_file_response(
    path: Path,
    *,
    content_type: str,
    cache_control: str,
    etag: str,
    use_pathsend: bool = False,
) -> ASGIApp:
    """Return an ASGI app that streams one local file with byte-range support."""

    async def response(scope: Scope, receive: Receive, send: Send) -> None:
        del receive
        if scope["type"] != "http":
            msg = "range file responses require an HTTP scope"
            raise RuntimeError(msg)

        file = await asyncio.to_thread(_open_regular_file, path)
        try:
            size = os.fstat(file.fileno()).st_size
            request_headers = Headers.from_scope(scope)
            range_header = request_headers.get("range")
            if_range = request_headers.get("if-range")
            method = scope.get("method", "GET")

            # If-Range uses strong ETag comparison. A mismatch deliberately
            # ignores even a malformed Range field and serves the whole file.
            honor_range = range_header is not None and _if_range_matches(if_range, etag)
            if method not in {"GET", "HEAD"}:
                honor_range = False

            ranges: list[_ByteRange] | None = None
            if honor_range and range_header is not None:
                try:
                    requested_ranges = _parse_ranges(range_header, size)
                except _NoOverlapError:
                    if size:
                        await _send_error(send, method, _NO_OVERLAP_BODY, size)
                        return
                    # Some clients send a Range field on every request. Go's
                    # net/http serves an empty representation normally rather
                    # than turning that harmless habit into a 416 response.
                    requested_ranges = []
                except _MalformedRangeError:
                    await _send_error(send, method, _INVALID_RANGE_BODY)
                    return

                # Matching net/http's safety rule avoids turning a short file
                # into a much larger response through overlapping ranges.
                if sum(byte_range.length for byte_range in requested_ranges) <= size:
                    ranges = requested_ranges

            response_headers = [
                (b"accept-ranges", b"bytes"),
                (b"cache-control", cache_control.encode("latin-1")),
                (b"etag", etag.encode("latin-1")),
            ]

            if ranges and len(ranges) > 1:
                boundary = os.urandom(30).hex()
                length = _multipart_length(boundary, ranges, content_type, size)
                response_headers.extend(
                    [
                        (b"content-length", str(length).encode("ascii")),
                        (b"content-type", f"multipart/byteranges; boundary={boundary}".encode("ascii")),
                    ]
                )
                status_code = 206
            elif ranges:
                byte_range = ranges[0]
                length = byte_range.length
                response_headers.extend(
                    [
                        (b"content-length", str(length).encode("ascii")),
                        (b"content-type", content_type.encode("latin-1")),
                        (b"content-range", byte_range.content_range(size).encode("ascii")),
                    ]
                )
                status_code = 206
            else:
                byte_range = _ByteRange(start=0, length=size)
                length = size
                response_headers.extend(
                    [
                        (b"content-length", str(length).encode("ascii")),
                        (b"content-type", content_type.encode("latin-1")),
                    ]
                )
                status_code = 200

            await send({"type": "http.response.start", "status": status_code, "headers": response_headers})
            if method == "HEAD" or length == 0:
                await send({"type": "http.response.body", "body": b"", "more_body": False})
                return

            extensions = scope.get("extensions") or {}
            if not ranges and use_pathsend and "http.response.pathsend" in extensions:
                # Granian hands the file to the kernel instead of paying one
                # event-loop/thread-pool round trip per chunk. The outer app
                # enables this only for files excluded from compression because
                # compression middleware requires ordinary response-body events.
                await send(cast(Message, {"type": "http.response.pathsend", "path": str(path)}))
                return

            if ranges and len(ranges) > 1:
                await _stream_multipart(file, ranges, boundary, content_type, size, send)
                return

            await asyncio.to_thread(file.seek, byte_range.start)
            await _stream(file, byte_range.length, send, final=True)
        finally:
            await asyncio.to_thread(file.close)

    return response


def _open_regular_file(path: Path) -> BinaryIO:
    # O_NONBLOCK prevents an attacker-controlled FIFO from stalling a worker
    # before fstat can enforce the regular-file boundary.
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            msg = f"static asset is not a regular file: {path}"
            raise ValueError(msg)
        return os.fdopen(descriptor, "rb", buffering=0)
    except BaseException:
        os.close(descriptor)
        raise


async def _stream(file: BinaryIO, remaining: int, send: Send, *, final: bool) -> None:
    while remaining:
        chunk = await asyncio.to_thread(file.read, min(remaining, _CHUNK_SIZE))
        if not chunk:
            msg = "static asset changed while it was being served"
            raise OSError(msg)
        remaining -= len(chunk)
        await send({"type": "http.response.body", "body": chunk, "more_body": remaining > 0 or not final})


async def _stream_multipart(
    file: BinaryIO,
    ranges: list[_ByteRange],
    boundary: str,
    content_type: str,
    size: int,
    send: Send,
) -> None:
    for index, byte_range in enumerate(ranges):
        await send(
            {
                "type": "http.response.body",
                "body": _multipart_preamble(boundary, byte_range, content_type, size, first=index == 0),
                "more_body": True,
            }
        )
        await asyncio.to_thread(file.seek, byte_range.start)
        await _stream(file, byte_range.length, send, final=False)
    await send({"type": "http.response.body", "body": _multipart_epilogue(boundary), "more_body": False})


async def _send_error(send: Send, method: str, body: bytes, size: int | None = None) -> None:
    headers = [
        (b"content-type", b"text/plain; charset=utf-8"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    if size is not None:
        headers.append((b"content-range", f"bytes */{size}".encode("ascii")))
    await send({"type": "http.response.start", "status": 416, "headers": headers})
    await send({"type": "http.response.body", "body": b"" if method == "HEAD" else body, "more_body": False})


def _parse_ranges(value: str, size: int) -> list[_ByteRange]:
    if not value.startswith("bytes="):
        raise _MalformedRangeError

    ranges: list[_ByteRange] = []
    no_overlap = False
    for raw_specifier in value.removeprefix("bytes=").split(","):
        specifier = raw_specifier.strip(" \t")
        if not specifier:
            continue
        if "-" not in specifier:
            raise _MalformedRangeError

        first, last = (part.strip(" \t") for part in specifier.split("-", 1))
        if first:
            start = _parse_decimal(first)
            if start >= size:
                no_overlap = True
                continue
            end = _parse_decimal(last) if last else size - 1
            if end < start:
                raise _MalformedRangeError
            end = min(end, size - 1)
            _append_range(ranges, _ByteRange(start=start, length=end - start + 1))
            continue

        if not last or last.startswith("-"):
            raise _MalformedRangeError
        suffix_length = min(_parse_decimal(last), size)
        if suffix_length == 0:
            no_overlap = True
            continue
        _append_range(ranges, _ByteRange(start=size - suffix_length, length=suffix_length))

    if no_overlap and not ranges:
        raise _NoOverlapError
    return ranges


def _append_range(ranges: list[_ByteRange], candidate: _ByteRange) -> None:
    # Bound both parser work and multipart amplification before response
    # construction; repeated or intersecting intervals provide no new bytes.
    if len(ranges) >= _MAX_RANGES or any(
        candidate.start <= existing.end and existing.start <= candidate.end for existing in ranges
    ):
        raise _MalformedRangeError
    ranges.append(candidate)


def _parse_decimal(value: str) -> int:
    digits = value.removeprefix("+")
    if not digits or not digits.isascii() or not digits.isdigit():
        raise _MalformedRangeError
    significant_digits = digits.lstrip("0") or "0"
    if len(significant_digits) > 19:
        raise _MalformedRangeError
    parsed = int(significant_digits)
    if parsed > _MAX_INT64:
        raise _MalformedRangeError
    return parsed


def _if_range_matches(value: str | None, etag: str) -> bool:
    if value is None or value == "":
        return True
    candidate = value.strip(" \t")
    if candidate.startswith("W/") or not candidate.startswith('"'):
        return False
    return candidate == etag


def _multipart_preamble(
    boundary: str,
    byte_range: _ByteRange,
    content_type: str,
    size: int,
    *,
    first: bool,
) -> bytes:
    separator = "" if first else "\r\n"
    return (
        f"{separator}--{boundary}\r\n"
        f"Content-Range: {byte_range.content_range(size)}\r\n"
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("latin-1")


def _multipart_epilogue(boundary: str) -> bytes:
    return f"\r\n--{boundary}--\r\n".encode("ascii")


def _multipart_length(boundary: str, ranges: list[_ByteRange], content_type: str, size: int) -> int:
    return sum(
        len(_multipart_preamble(boundary, byte_range, content_type, size, first=index == 0)) + byte_range.length
        for index, byte_range in enumerate(ranges)
    ) + len(_multipart_epilogue(boundary))
