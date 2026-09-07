"""Inventory-bound static files with conditional and range delivery."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from litestar import Request
from litestar.enums import HttpMethod
from litestar.response import Response
from litestar.types import ASGIApp

from www.assets import ApplicationAssets
from www.middleware import etag_matches, strong_etag_matches
from www.ranges import range_file_response


async def static_asset_response(
    asset_path: str, request: Request[Any, Any, Any], application_assets: ApplicationAssets, static_dir: Path
) -> ASGIApp:
    """Serve only files recorded in the immutable startup inventory."""
    relative_path = asset_path.lstrip("/")
    asset_url = f"/static/{relative_path}"
    digest = application_assets.hashes.get(asset_url)
    static_root = static_dir.resolve()
    # Look up the immutable URL inventory before touching the filesystem.
    # Unknown paths (including NULs and dot segments) are client misses,
    # and files added after startup must not become public accidentally.
    path = (static_root / relative_path).resolve() if digest is not None else None
    if path is None or not path.is_relative_to(static_root) or not path.is_file():
        response = Response(
            b"404 page not found\n",
            headers={"cache-control": "no-cache", "content-type": "text/plain; charset=utf-8"},
            status_code=404,
        )
        return response.to_asgi_response(
            app=None,
            request=request,
            is_head_response=request.method == HttpMethod.HEAD,
        )

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
        response = Response(b"", headers={"cache-control": cache_control, "etag": etag}, status_code=412)
        return response.to_asgi_response(app=None, request=request)
    if etag_matches(request.headers.get("if-none-match", ""), etag):
        response = Response(b"", headers={"cache-control": cache_control, "etag": etag}, status_code=304)
        return response.to_asgi_response(app=None, request=request)
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if content_type.startswith("text/"):
        content_type += "; charset=utf-8"
    return range_file_response(
        path,
        content_type=content_type,
        cache_control=cache_control,
        etag=etag,
        use_pathsend=True,
    )
