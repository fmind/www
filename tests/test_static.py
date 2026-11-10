"""Inventory-bound static asset delivery, caching, and conditional preconditions."""

from pathlib import Path
from typing import Any

from litestar import Litestar, Request, route
from litestar.enums import HttpMethod
from litestar.params import FromPath
from litestar.testing import TestClient
from litestar.types import ASGIApp

from www.assets import ApplicationAssets
from www.static import static_asset_response


def _make_static_client(static_dir: Path, hashes: dict[str, str]) -> TestClient[Any]:
    assets = ApplicationAssets(root_files={}, hashes=hashes, stylesheet="body{}")
    resolved = static_dir.resolve()

    @route("/static/{asset_path:path}", http_method=(HttpMethod.GET, HttpMethod.HEAD))
    async def asset(asset_path: FromPath[str], request: Request[Any, Any, Any]) -> ASGIApp:
        return await static_asset_response(asset_path, request, assets, resolved)

    return TestClient(Litestar(route_handlers=[asset], openapi_config=None))


def test_inventory_bound_delivery_rejects_unregistered_deleted_and_escaped_paths(tmp_path: Path) -> None:
    (tmp_path / "public.txt").write_text("hello\n", encoding="utf-8")
    (tmp_path / "unlisted.txt").write_text("secret\n", encoding="utf-8")
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    (tmp_path / "escape.txt").symlink_to(outside)

    hashes = {
        "/static/public.txt": "1234abcd",
        "/static/missing.txt": "deadbeef",
        "/static/escape.txt": "cafebabe",
    }
    with _make_static_client(tmp_path, hashes) as client:
        for path in ("/static/unlisted.txt", "/static/missing.txt", "/static/escape.txt"):
            get_miss = client.get(path)
            assert get_miss.status_code == 404, path
            assert get_miss.content == b"404 page not found\n"
            assert get_miss.headers["cache-control"] == "no-cache"

            head_miss = client.head(path)
            assert head_miss.status_code == 404, path
            assert head_miss.content == b""
            assert head_miss.headers["content-length"] == str(len(b"404 page not found\n"))


def test_content_addressed_cache_control_and_conditional_preconditions(tmp_path: Path) -> None:
    (tmp_path / "note.txt").write_text("hello world\n", encoding="utf-8")
    (tmp_path / "blob.unknownext").write_bytes(b"\x00\x01\x02\x03")
    digest = "a1b2c3d4"
    etag = f'"{digest}"'
    hashes = {"/static/note.txt": digest, "/static/blob.unknownext": "00112233"}

    with _make_static_client(tmp_path, hashes) as client:
        immutable = client.get(f"/static/note.txt?v={digest}")
        assert immutable.status_code == 200
        assert immutable.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert immutable.headers["content-type"] == "text/plain; charset=utf-8"
        assert immutable.headers["etag"] == etag

        for suffix in ("", "?v=stale", f"?v={digest}&v={digest}"):
            revalidate = client.get(f"/static/note.txt{suffix}")
            assert revalidate.status_code == 200
            assert revalidate.headers["cache-control"] == "public, max-age=86400, must-revalidate"

        binary = client.get("/static/blob.unknownext")
        assert binary.status_code == 200
        assert binary.headers["content-type"] == "application/octet-stream"

        # RFC 9110 §13.2.2: If-Match evaluates before If-None-Match and Range.
        for method in ("GET", "HEAD"):
            precondition_failed = client.request(
                method,
                f"/static/note.txt?v={digest}",
                headers={"if-match": '"wrong"', "if-none-match": etag, "range": "bytes=0-4"},
            )
            assert precondition_failed.status_code == 412
            assert precondition_failed.content == b""
            assert precondition_failed.headers["etag"] == etag
            assert precondition_failed.headers["cache-control"] == "public, max-age=31536000, immutable"

            not_modified = client.request(
                method,
                f"/static/note.txt?v={digest}",
                headers={"if-match": etag, "if-none-match": f"W/{etag}"},
            )
            assert not_modified.status_code == 304
            assert not_modified.content == b""
            assert not_modified.headers["etag"] == etag
            assert not_modified.headers["cache-control"] == "public, max-age=31536000, immutable"
