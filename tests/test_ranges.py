"""Static file byte-range response tests."""

import asyncio
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from litestar import Litestar, route
from litestar.enums import HttpMethod
from litestar.middleware import DefineMiddleware
from litestar.testing import TestClient
from litestar.types import ASGIApp, HTTPRequestEvent, Message

from tests.conftest import asgi_scope
from www.config import Config
from www.middleware import SiteMiddleware
from www.ranges import _stream, etag_matches, range_file_response, strong_etag_matches

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


def test_full_get_uses_server_pathsend_when_offered(asset: Path) -> None:
    response = range_file_response(asset, content_type=_CONTENT_TYPE, cache_control=_CACHE_CONTROL, etag=_ETAG)
    extensions: dict[str, dict[object, object]] = {"http.response.pathsend": {}}
    full = asyncio.run(_invoke(response, extensions=extensions))
    partial = asyncio.run(_invoke(response, headers=[(b"range", b"bytes=0-3")], extensions=extensions))

    assert full[-1] == {"type": "http.response.pathsend", "path": str(asset)}
    # The server would send the whole file, so a range streams its own bytes.
    assert partial[-1] == {"type": "http.response.body", "body": b"0123", "more_body": False}


@pytest.mark.parametrize(
    ("range_header", "expected_body", "content_range"),
    [
        ("bytes=0-3", b"0123", "bytes 0-3/16"),
        ("BYTES=0-3", b"0123", "bytes 0-3/16"),
        ("Bytes=0-3", b"0123", "bytes 0-3/16"),
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

    assert response.status_code == 416
    assert response.content == b"invalid range: failed to overlap\n"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["content-range"] == "bytes */16"
    assert response.headers["content-length"] == "33"
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert "accept-ranges" not in response.headers
    assert "content-disposition" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"


def test_etag_validators_enforce_rfc9110_weak_and_strong_comparison() -> None:
    assert etag_matches("*", '"abc"')
    assert etag_matches('W/"other", "abc"', '"abc"')
    assert etag_matches('"abc"', 'W/"abc"')
    assert not etag_matches('"other", *', '"abc"')
    assert not etag_matches("", '"abc"')

    assert strong_etag_matches("*", '"abc"')
    assert strong_etag_matches('"other", "abc"', '"abc"')
    assert not strong_etag_matches('W/"abc"', '"abc"')
    assert not strong_etag_matches('"other", *', '"abc"')
    assert not strong_etag_matches("", '"abc"')


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


@pytest.mark.parametrize(
    "range_header",
    [
        "bytes=bogus",
        "bytes=10-5",
        "bytes=-",
        "bytes=--5",
        "bytes=x-5",
        "bytes=0-x",
        # RFC 9110 positions are digits only, without a sign.
        "bytes=+1-5",
        "bytes=-+5",
        # 19 digits, but above the signed 64-bit range.
        "bytes=9223372036854775808-",
    ],
)
def test_malformed_ranges_return_unsized_416(asset: Path, range_header: str) -> None:
    with _client(asset) as client:
        response = client.get("/video.mp4", headers={"range": range_header})

    assert response.status_code == 416
    assert response.content == b"invalid range\n"
    assert response.headers["content-length"] == "14"
    assert "content-range" not in response.headers


def test_a_file_that_shrinks_mid_stream_fails_instead_of_sending_a_short_body() -> None:
    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    # The response already promised 10 bytes; the server must abort, not end the body early.
    with pytest.raises(OSError, match="changed while it was being served"):
        asyncio.run(_stream(BytesIO(b"abc"), 10, send))
    assert sent == [{"type": "http.response.body", "body": b"abc", "more_body": True}]


def test_oversized_decimal_is_rejected_without_escaping_the_range_boundary(asset: Path) -> None:
    with _client(asset) as client:
        response = client.get("/video.mp4", headers={"range": f"bytes={'9' * 5_000}-"})

    assert response.status_code == 416
    assert response.content == b"invalid range\n"
    assert "content-range" not in response.headers


@pytest.mark.parametrize(
    "range_header",
    [
        "bytes=0-3, 10-11",
        "bytes=99-,2-5",
        "bytes=0-1,bogus",
        "bytes=0-3,",
        "bytes=" + ",".join(f"{index}-{index}" for index in range(9)),
    ],
    ids=("two", "one-overlap", "malformed-member", "empty-member", "nine"),
)
def test_range_lists_are_ignored_and_get_the_full_representation(asset: Path, range_header: str) -> None:
    # RFC 9110 section 14.2 lets a server ignore Range; there is no multipart/byteranges response.
    with _client(asset) as client:
        response = client.get("/video.mp4", headers={"range": range_header, "if-range": _ETAG})

    assert response.status_code == 200
    assert response.content == _BODY
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-length"] == str(len(_BODY))
    assert response.headers["content-type"] == _CONTENT_TYPE
    assert "content-range" not in response.headers


@pytest.mark.parametrize("range_header", ["bytes=2-5", "bytes=16-", "bytes=0-3,10-11", "bytes=bogus", "items=0-1"])
def test_head_ignores_ranges_and_returns_full_metadata(asset: Path, range_header: str) -> None:
    with _client(asset) as client:
        response = client.head("/video.mp4", headers={"range": range_header})

    assert response.status_code == 200
    assert response.content == b""
    assert "content-range" not in response.headers
    assert response.headers["content-length"] == str(len(_BODY))
    assert response.headers["content-type"] == _CONTENT_TYPE


@pytest.mark.parametrize("range_header", ["items=0-1", "bytes", "bytes=", "bytes= "])
def test_unknown_units_and_empty_range_sets_are_ignored(asset: Path, range_header: str) -> None:
    with _client(asset) as client:
        response = client.get("/video.mp4", headers={"range": range_header})

    assert response.status_code == 200
    assert response.content == _BODY
    assert "content-range" not in response.headers


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


def test_non_regular_path_is_rejected_before_response_start(tmp_path: Path) -> None:
    response = range_file_response(tmp_path, content_type=_CONTENT_TYPE, cache_control="no-cache", etag=_ETAG)

    with pytest.raises(ValueError, match="not a regular file"):
        asyncio.run(_invoke(response))


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

    await app(asgi_scope(raw_path=b"/large.bin", headers=headers or [], extensions=extensions), receive, send)
    return messages
