"""Inventory-bound static files with conditional and range delivery."""

import asyncio
import mimetypes
from pathlib import Path
from typing import Any

from litestar import Request
from litestar.enums import HttpMethod, MediaType
from litestar.response import Response
from litestar.types import ASGIApp

from www.assets import ApplicationAssets
from www.ranges import etag_matches, range_file_response, strong_etag_matches


def _resolve_static_file(static_root: Path, relative_path: str) -> Path | None:
    path = (static_root / relative_path).resolve()
    return path if path.is_relative_to(static_root) and path.is_file() else None


async def static_asset_response(
    asset_path: str, request: Request[Any, Any, Any], application_assets: ApplicationAssets, static_root: Path
) -> ASGIApp:
    """Serve only files recorded in the immutable startup inventory."""
    relative_path = asset_path.lstrip("/")
    asset_url = f"/static/{relative_path}"
    digest = application_assets.hashes.get(asset_url)
    # Look up the immutable URL inventory before touching the filesystem.
    # Pre-resolved startup paths avoid per-request blocking I/O on the event loop;
    # synthetic test snapshots without `files` resolve safely on a worker thread.
    path: Path | None = None
    if digest is not None:
        if application_assets.files:
            path = application_assets.files.get(asset_url)
        else:
            path = await asyncio.to_thread(_resolve_static_file, static_root, relative_path)
    if path is None:
        body = b"404 page not found\n"
        is_head = request.method == HttpMethod.HEAD
        headers = {"cache-control": "no-cache", "content-type": "text/plain; charset=utf-8"}
        if is_head:
            # Litestar rejects content on HEAD responses; keep GET's length without the body.
            headers["content-length"] = str(len(body))
        response = Response(b"" if is_head else body, headers=headers, status_code=404)
        return response.to_asgi_response(app=None, request=request, is_head_response=is_head)

    # The startup snapshot hashes every regular asset, so the ETag also
    # provides the strong validator required for a safe If-Range response.
    # Only the canonical content-addressed URL is immutable. Unknown, empty,
    # or duplicated versions must revalidate instead of pinning stale bytes.
    immutable = request.query_params.getall("v", []) == [digest]
    cache_control = "public, max-age=31536000, immutable" if immutable else "public, max-age=86400, must-revalidate"
    etag = f'"{digest}"'
    if_match = request.headers.get("if-match")
    if if_match is not None and not strong_etag_matches(if_match, etag):
        # Evaluate this strong precondition before cache and range logic.
        response = Response(
            b"",
            headers={"cache-control": cache_control, "etag": etag},
            media_type=MediaType.TEXT,
            status_code=412,
        )
        return response.to_asgi_response(app=None, request=request)
    if etag_matches(request.headers.get("if-none-match", ""), etag):
        response = Response(b"", headers={"cache-control": cache_control, "etag": etag}, status_code=304)
        return response.to_asgi_response(app=None, request=request)
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if content_type.startswith("text/"):
        content_type += "; charset=utf-8"
    return range_file_response(path, content_type=content_type, cache_control=cache_control, etag=etag)
