"""Static file byte-range response tests."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

import pytest
from litestar import Litestar, route
from litestar.enums import HttpMethod
from litestar.middleware import DefineMiddleware
from litestar.testing import TestClient
from litestar.types import ASGIApp, HTTPRequestEvent, HTTPResponseStartEvent, Message, Scope

from www.config import Config
from www.middleware import SiteMiddleware
from www.ranges import range_file_response

_BODY = b"0123456789abcdef"
_CACHE_CONTROL = "public, max-age=86400, must-revalidate"
_CONTENT_TYPE = "video/mp4"
_ETAG = '"e8d89832"'


@pytest.fixture
def asset(tmp_path: Path) -> Path:
    path = tmp_path / "video.mp4"
    path.write_bytes(_BODY)
    return path


def _client(path: Path) -> TestClient[Any]:
    @route("/video.mp4", http_method=(HttpMethod.GET, HttpMethod.HEAD), sync_to_thread=False)
    def static_file() -> ASGIApp:
        return range_file_response(
            path,
            content_type=_CONTENT_TYPE,
            cache_control=_CACHE_CONTROL,
            etag=_ETAG,
        )

    app = Litestar(
        route_handlers=[static_file],
        middleware=[DefineMiddleware(SiteMiddleware, config=Config(), logger=Mock())],
        openapi_config=None,
    )
    return TestClient(app)


def test_full_get_and_head_keep_static_and_outer_security_headers(asset: Path) -> None:
    with _client(asset) as client:
        response = client.get("/video.mp4")
        head = client.head("/video.mp4")

    assert response.status_code == 200
    assert response.content == _BODY
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["cache-control"] == _CACHE_CONTROL
    assert response.headers["content-length"] == str(len(_BODY))
    assert response.headers["content-type"] == _CONTENT_TYPE
    assert response.headers["etag"] == _ETAG
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "content-disposition" not in response.headers

    assert head.status_code == 200
    assert head.content == b""
    assert head.headers["content-length"] == str(len(_BODY))
    assert head.headers["accept-ranges"] == "bytes"


def test_full_get_uses_server_pathsend_when_explicitly_enabled(asset: Path) -> None:
    messages = asyncio.run(
        _invoke(
            range_file_response(
                asset,
                content_type=_CONTENT_TYPE,
                cache_control=_CACHE_CONTROL,
                etag=_ETAG,
                use_pathsend=True,
            ),
            extensions={"http.response.pathsend": {}},
        )
    )

    assert messages[-1] == {"type": "http.response.pathsend", "path": str(asset)}


@pytest.mark.parametrize(
    ("range_header", "expected_body", "content_range"),
    [
        ("bytes=0-3", b"0123", "bytes 0-3/16"),
        ("bytes=10-", b"abcdef", "bytes 10-15/16"),
        ("bytes=-4", b"cdef", "bytes 12-15/16"),
        ("bytes=-100", _BODY, "bytes 0-15/16"),
        ("bytes=0-999", _BODY, "bytes 0-15/16"),
    ],
)
def test_single_byte_ranges(
    asset: Path,
    range_header: str,
    expected_body: bytes,
    content_range: str,
) -> None:
    with _client(asset) as client:
        response = client.get("/video.mp4", headers={"range": range_header})

    assert response.status_code == 206
    assert response.content == expected_body
    assert response.headers["content-range"] == content_range
    assert response.headers["content-length"] == str(len(expected_body))
    assert response.headers["accept-ranges"] == "bytes"


def test_zero_suffix_is_unsatisfiable(asset: Path) -> None:
    with _client(asset) as client:
        response = client.get("/video.mp4", headers={"range": "bytes=-0"})

    assert response.status_code == 416
    assert response.content == b"invalid range: failed to overlap\n"
    assert response.headers["content-range"] == "bytes */16"


def test_if_range_requires_the_exact_strong_etag(asset: Path) -> None:
    with _client(asset) as client:
        matching = client.get(
            "/video.mp4",
            headers={"range": "bytes=2-5", "if-range": _ETAG},
        )
        matching_multiple = client.get(
            "/video.mp4",
            headers={"range": "bytes=0-1,10-11", "if-range": _ETAG},
        )
        stale = client.get(
            "/video.mp4",
            headers={"range": "bytes=2-5", "if-range": '"stale"'},
        )
        weak = client.get(
            "/video.mp4",
            headers={"range": "bytes=2-5", "if-range": f"W/{_ETAG}"},
        )
        ignored_invalid = client.get(
            "/video.mp4",
            headers={"range": "bytes=invalid", "if-range": '"stale"'},
        )

    assert matching.status_code == 206
    assert matching.content == b"2345"
    expected_multiple = _multipart_body(
        matching_multiple.headers["content-type"],
        [("bytes 0-1/16", b"01"), ("bytes 10-11/16", b"ab")],
    )
    assert matching_multiple.status_code == 206
    assert matching_multiple.content == expected_multiple
    for response in (stale, weak, ignored_invalid):
        assert response.status_code == 200
        assert response.content == _BODY
        assert "content-range" not in response.headers


@pytest.mark.parametrize("if_range", [f"{_ETAG}garbage", f'{_ETAG}, "other"'])
def test_if_range_rejects_trailing_data(asset: Path, if_range: str) -> None:
    with _client(asset) as client:
        response = client.get(
            "/video.mp4",
            headers={"range": "bytes=2-5", "if-range": if_range},
        )

    assert response.status_code == 200
    assert response.content == _BODY
    assert "content-range" not in response.headers


def test_non_overlapping_range_returns_sized_416(asset: Path) -> None:
    with _client(asset) as client:
        response = client.get("/video.mp4", headers={"range": "bytes=16-"})
        head = client.head("/video.mp4", headers={"range": "bytes=16-"})

    assert response.status_code == 416
    assert response.content == b"invalid range: failed to overlap\n"
    assert response.headers["content-range"] == "bytes */16"
    assert response.headers["content-length"] == "33"
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert "accept-ranges" not in response.headers
    assert "content-disposition" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"

    assert head.status_code == 416
    assert head.content == b""
    assert head.headers["content-length"] == "33"
    assert head.headers["content-range"] == "bytes */16"


def test_empty_file_ignores_a_non_overlapping_range(tmp_path: Path) -> None:
    path = tmp_path / "empty.bin"
    path.write_bytes(b"")

    with _client(path) as client:
        response = client.get("/video.mp4", headers={"range": "bytes=0-"})

    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-length"] == "0"
    assert "content-range" not in response.headers


@pytest.mark.parametrize("range_header", ["bytes=bogus", "items=0-1", "bytes=10-5", "bytes=0-1,bogus"])
def test_malformed_ranges_return_unsized_416(asset: Path, range_header: str) -> None:
    with _client(asset) as client:
        response = client.get("/video.mp4", headers={"range": range_header})

    assert response.status_code == 416
    assert response.content == b"invalid range\n"
    assert response.headers["content-length"] == "14"
    assert "content-range" not in response.headers


def test_oversized_decimal_is_rejected_without_escaping_the_range_boundary(asset: Path) -> None:
    with _client(asset) as client:
        response = client.get("/video.mp4", headers={"range": f"bytes={'9' * 5_000}-"})

    assert response.status_code == 416
    assert response.content == b"invalid range\n"
    assert "content-range" not in response.headers


def test_multiple_byte_ranges_return_multipart_in_request_order(asset: Path) -> None:
    with _client(asset) as client:
        response = client.get("/video.mp4", headers={"range": "bytes=0-3, 10-11"})
        head = client.head("/video.mp4", headers={"range": "bytes=0-3, 10-11"})

    assert response.status_code == 206
    assert response.headers["accept-ranges"] == "bytes"
    assert "content-range" not in response.headers
    expected = _multipart_body(
        response.headers["content-type"],
        [("bytes 0-3/16", b"0123"), ("bytes 10-11/16", b"ab")],
    )
    assert response.content == expected
    assert response.headers["content-length"] == str(len(expected))

    assert head.status_code == 206
    assert head.content == b""
    expected_head = _multipart_body(
        head.headers["content-type"],
        [("bytes 0-3/16", b"0123"), ("bytes 10-11/16", b"ab")],
    )
    assert head.headers["content-length"] == str(len(expected_head))


def test_eight_satisfiable_ranges_are_allowed(asset: Path) -> None:
    selected_offsets = range(0, len(_BODY), 2)
    range_header = "bytes=-0,99-," + ",".join(f"{offset}-{offset}" for offset in selected_offsets)

    with _client(asset) as client:
        response = client.get("/video.mp4", headers={"range": range_header})

    expected = _multipart_body(
        response.headers["content-type"],
        [(f"bytes {offset}-{offset}/16", _BODY[offset : offset + 1]) for offset in selected_offsets],
    )
    assert response.status_code == 206
    assert response.content == expected


def test_multiple_ranges_drop_non_overlaps_and_empty_members(asset: Path) -> None:
    with _client(asset) as client:
        one_overlap = client.get("/video.mp4", headers={"range": "bytes=99-,2-5"})
        empty_members = client.get("/video.mp4", headers={"range": "bytes=,0-1,,4-5,"})

    assert one_overlap.status_code == 206
    assert one_overlap.content == b"2345"
    assert one_overlap.headers["content-range"] == "bytes 2-5/16"

    expected = _multipart_body(
        empty_members.headers["content-type"],
        [("bytes 0-1/16", b"01"), ("bytes 4-5/16", b"45")],
    )
    assert empty_members.status_code == 206
    assert empty_members.content == expected


@pytest.mark.parametrize(
    "range_header",
    [
        "bytes=0-15,0-0",
        "bytes=0-3,0-3",
        "bytes=" + ",".join(f"{index}-{index}" for index in range(9)),
    ],
    ids=("overlap", "repeat", "more-than-eight"),
)
def test_overlapping_repeated_or_excessive_ranges_are_rejected(asset: Path, range_header: str) -> None:
    with _client(asset) as client:
        response = client.get("/video.mp4", headers={"range": range_header})

    assert response.status_code == 416
    assert response.content == b"invalid range\n"
    assert "content-range" not in response.headers


def test_partial_head_has_selected_length_without_a_body(asset: Path) -> None:
    with _client(asset) as client:
        response = client.head("/video.mp4", headers={"range": "bytes=2-5"})

    assert response.status_code == 206
    assert response.content == b""
    assert response.headers["content-range"] == "bytes 2-5/16"
    assert response.headers["content-length"] == "4"


def test_large_file_is_emitted_in_bounded_chunks(tmp_path: Path) -> None:
    body = bytes(range(256)) * 8_193
    path = tmp_path / "large.bin"
    path.write_bytes(body)

    messages = asyncio.run(
        _invoke(range_file_response(path, content_type=_CONTENT_TYPE, cache_control="no-cache", etag=_ETAG))
    )
    body_messages = [message for message in messages if message["type"] == "http.response.body"]

    assert len(body_messages) == 3
    assert b"".join(message.get("body", b"") for message in body_messages) == body
    assert [message.get("more_body", False) for message in body_messages] == [True, True, False]


def test_large_multipart_ranges_are_emitted_in_bounded_chunks(tmp_path: Path) -> None:
    body = bytes(range(256)) * 8_193
    path = tmp_path / "large.bin"
    path.write_bytes(body)

    messages = asyncio.run(
        _invoke(
            range_file_response(path, content_type=_CONTENT_TYPE, cache_control="no-cache", etag=_ETAG),
            headers=[(b"range", b"bytes=0-1100000,1100001-2097407")],
        )
    )
    start = cast("HTTPResponseStartEvent", messages[0])
    body_messages = [message for message in messages if message["type"] == "http.response.body"]
    response_headers = {key.decode("ascii"): value.decode("latin-1") for key, value in start["headers"]}
    expected = _multipart_body(
        response_headers["content-type"],
        [("bytes 0-1100000/2097408", body[:1_100_001]), ("bytes 1100001-2097407/2097408", body[1_100_001:])],
    )

    assert start["status"] == 206
    assert b"".join(message.get("body", b"") for message in body_messages) == expected
    assert max(len(message.get("body", b"")) for message in body_messages) <= 1024 * 1024
    assert [message.get("more_body", False) for message in body_messages][-1] is False


def test_non_regular_path_is_rejected_before_response_start(tmp_path: Path) -> None:
    response = range_file_response(tmp_path, content_type=_CONTENT_TYPE, cache_control="no-cache", etag=_ETAG)

    with pytest.raises(ValueError, match="not a regular file"):
        asyncio.run(_invoke(response))


def _multipart_body(content_type: str, parts: list[tuple[str, bytes]]) -> bytes:
    prefix, separator, boundary = content_type.partition("boundary=")
    assert prefix == "multipart/byteranges; "
    assert separator
    assert boundary
    encoded_boundary = boundary.encode("ascii")
    body = bytearray()
    for index, (content_range, content) in enumerate(parts):
        body.extend(b"\r\n" if index else b"")
        body.extend(b"--" + encoded_boundary + b"\r\n")
        body.extend(f"Content-Range: {content_range}\r\n".encode("ascii"))
        body.extend(f"Content-Type: {_CONTENT_TYPE}\r\n\r\n".encode("latin-1"))
        body.extend(content)
    body.extend(b"\r\n--" + encoded_boundary + b"--\r\n")
    return bytes(body)


async def _invoke(
    app: ASGIApp,
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    extensions: dict[str, dict[object, object]] | None = None,
) -> list[Message]:
    messages: list[Message] = []

    async def receive() -> HTTPRequestEvent:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    scope = cast(
        "Scope",
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/large.bin",
            "raw_path": b"/large.bin",
            "query_string": b"",
            "root_path": "",
            "headers": headers or [],
            "extensions": extensions,
            "client": ("127.0.0.1", 1),
            "server": ("testserver", 80),
        },
    )
    await app(scope, receive, send)
    return messages
