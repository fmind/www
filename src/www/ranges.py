"""HTTP validators and bounded asynchronous byte-range responses for regular static files."""

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
# traversal.
_CHUNK_SIZE = 1024 * 1024
_MAX_INT64 = (1 << 63) - 1
_INVALID_RANGE_BODY = b"invalid range\n"
_NO_OVERLAP_BODY = b"invalid range: failed to overlap\n"


class _MalformedRangeError(ValueError):
    """The Range field contains an invalid byte-range specifier."""


class _NoOverlapError(ValueError):
    """The byte-range starts beyond the current representation."""


def etag_matches(header: str, current: str) -> bool:
    """Apply weak comparison to an If-None-Match field (RFC 9110 §13.1.2)."""
    value = header.strip()
    if value == "*":
        return True
    candidates = tuple(item.strip() for item in value.split(",") if item.strip())
    if "*" in candidates:
        return False
    target = current.removeprefix("W/")
    return any(candidate.removeprefix("W/") == target for candidate in candidates)


def strong_etag_matches(header: str, current: str) -> bool:
    """Match one current strong validator in an If-Match field."""
    value = header.strip()
    if value == "*":
        return True
    candidates = tuple(item.strip() for item in value.split(",") if item.strip())
    if "*" in candidates:
        return False
    return any(candidate == current and not candidate.startswith("W/") for candidate in candidates)


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
) -> ASGIApp:
    """Return an ASGI app that streams one local file with single byte-range support.

    A full GET uses the server's pathsend extension when offered, so the route
    must be excluded from compression, which needs ordinary response-body events.
    """

    async def response(scope: Scope, receive: Receive, send: Send) -> None:
        del receive
        file = await asyncio.to_thread(_open_regular_file, path)
        try:
            size = os.fstat(file.fileno()).st_size
            request_headers = Headers.from_scope(scope)
            if_range = request_headers.get("if-range")
            method = scope.get("method", "GET")

            # RFC 9110: only GET supports Range; unknown units are ignored and
            # unit names are case-insensitive. If-Range requires a strong ETag.
            # Section 14.2 lets a server ignore Range, so a list of ranges gets
            # the full representation instead of multipart/byteranges.
            unit, _, specifier = request_headers.get("range", "").partition("=")
            honor_range = (
                method == "GET"
                and unit.lower() == "bytes"
                and "," not in specifier
                and _if_range_matches(if_range, etag)
            )

            byte_range: _ByteRange | None = None
            if honor_range:
                try:
                    byte_range = _parse_range(specifier, size)
                except _NoOverlapError:
                    if size:
                        await _send_error(send, _NO_OVERLAP_BODY, size)
                        return
                    # An empty representation can satisfy clients that always send Range.
                except _MalformedRangeError:
                    await _send_error(send, _INVALID_RANGE_BODY)
                    return

            partial = byte_range is not None
            if byte_range is None:
                byte_range = _ByteRange(start=0, length=size)
            response_headers = [
                (b"accept-ranges", b"bytes"),
                (b"cache-control", cache_control.encode("latin-1")),
                (b"etag", etag.encode("latin-1")),
                (b"content-length", str(byte_range.length).encode("ascii")),
                (b"content-type", content_type.encode("latin-1")),
            ]
            if partial:
                response_headers.append((b"content-range", byte_range.content_range(size).encode("ascii")))

            await send({"type": "http.response.start", "status": 206 if partial else 200, "headers": response_headers})
            if method == "HEAD" or byte_range.length == 0:
                await send({"type": "http.response.body", "body": b"", "more_body": False})
                return

            if not partial and "http.response.pathsend" in (scope.get("extensions") or {}):
                # Granian hands the file to the kernel instead of paying one
                # event-loop/thread-pool round trip per chunk.
                await send(cast(Message, {"type": "http.response.pathsend", "path": str(path)}))
                return

            await asyncio.to_thread(file.seek, byte_range.start)
            await _stream(file, byte_range.length, send)
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


async def _stream(file: BinaryIO, remaining: int, send: Send) -> None:
    while remaining:
        chunk = await asyncio.to_thread(file.read, min(remaining, _CHUNK_SIZE))
        if not chunk:
            msg = "static asset changed while it was being served"
            raise OSError(msg)
        remaining -= len(chunk)
        await send({"type": "http.response.body", "body": chunk, "more_body": remaining > 0})


async def _send_error(send: Send, body: bytes, size: int | None = None) -> None:
    headers = [
        (b"cache-control", b"no-cache"),
        (b"content-type", b"text/plain; charset=utf-8"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    if size is not None:
        headers.append((b"content-range", f"bytes */{size}".encode("ascii")))
    await send({"type": "http.response.start", "status": 416, "headers": headers})
    await send({"type": "http.response.body", "body": body, "more_body": False})


def _parse_range(value: str, size: int) -> _ByteRange | None:
    """Parse one byte-range-spec; an empty one selects nothing and is ignored."""
    specifier = value.strip(" \t")
    if not specifier:
        return None
    if "-" not in specifier:
        raise _MalformedRangeError

    first, last = (part.strip(" \t") for part in specifier.split("-", 1))
    if first:
        start = _parse_decimal(first)
        if start >= size:
            raise _NoOverlapError
        end = _parse_decimal(last) if last else size - 1
        if end < start:
            raise _MalformedRangeError
        return _ByteRange(start=start, length=min(end, size - 1) - start + 1)

    if not last or last.startswith("-"):
        raise _MalformedRangeError
    suffix_length = min(_parse_decimal(last), size)
    if suffix_length == 0:
        raise _NoOverlapError
    return _ByteRange(start=size - suffix_length, length=suffix_length)


def _parse_decimal(digits: str) -> int:
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
