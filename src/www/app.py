"""Litestar application assembly for every human and machine surface."""

from __future__ import annotations

import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from litestar import Litestar, Request, asgi, route
from litestar.concurrency import sync_to_thread
from litestar.config.compression import CompressionConfig
from litestar.enums import HttpMethod
from litestar.params import FromPath
from litestar.plugins.opentelemetry import OpenTelemetryConfig, OpenTelemetryPlugin
from litestar.response import Redirect, Response
from litestar.types import ASGIApp, Scope
from mcp.server.transport_security import TransportSecuritySettings

from www.assets import ApplicationAssets, StaticResponse, load_application_assets
from www.config import Config, Environment
from www.content import ArticleCollection, article_summaries, load_articles, visible_articles
from www.data import (
    BADGES,
    BIOGRAPHY,
    EXPERIENCES,
    EXPERTISE,
    LEADERSHIP,
    METADATA,
    OPEN_SOURCE,
    SITE_PAGES,
    SPECIALIZATIONS,
    YOUTUBE_SERIES,
    get_services,
    get_structured_data,
    markdown_to_html,
)
from www.log import configure_logging
from www.mcp import create_mcp_server, render_mcp_server_card, render_profile_json
from www.middleware import Logger, SiteMiddleware, etag_matches, strong_etag_matches, trace_fields
from www.models import PageMetadata, SitePage
from www.pages import (
    article_index_metadata,
    article_metadata,
    home_metadata,
    not_found_metadata,
    site_index_metadata,
    site_page_metadata,
    site_structured_data,
)
from www.publications import (
    article_index_data,
    article_markdown_index,
    related_article_index,
    render_atom_feed,
    render_llms_full,
    render_llms_txt,
    render_sitemap,
)
from www.ranges import range_file_response
from www.rendering import PageTemplate, Renderer
from www.search import SearchIndex
from www.sites import build_llm_self_hosting_view
from www.telemetry import TELEMETRY_SHUTDOWN_TIMEOUT_SECONDS, configure_telemetry, shutdown_telemetry

_DAY_CACHE = "public, max-age=86400, must-revalidate"
_HOUR_CACHE = "public, max-age=3600, must-revalidate"
_HOUR_CACHE_WITHOUT_REVALIDATION = "public, max-age=3600"
_YEAR_CACHE = "public, max-age=31536000, immutable"
_NO_CACHE = "no-cache"
_MCP_MAX_BODY_SIZE = 1 << 20
# Static ETags and byte ranges describe the on-disk representation. Compressing
# it afterward invalidates both contracts. Page CSS is inline, so HTML still
# benefits from Brotli without needing separate encoded static representations.
_COMPRESSION_EXCLUDE = r"^/(?:mcp|static)(?:/|$)"
_READ_METHODS = (HttpMethod.GET, HttpMethod.HEAD)

type AppRequest = Request[Any, Any, Any]


def _static_response(
    body: bytes,
    content_type: str,
    cache_control: str,
    *,
    cors: bool = False,
    status_code: int = 200,
    extra_headers: dict[str, str] | None = None,
) -> Response[bytes]:
    headers = {
        "cache-control": cache_control,
        "content-type": content_type,
        **(extra_headers or {}),
    }
    if cors:
        headers["access-control-allow-origin"] = "*"
    return Response(body, headers=headers, status_code=status_code)


def _redirect(path: str) -> Redirect:
    return Redirect(path, status_code=301)


def _request_nonce(request: AppRequest) -> str:
    return request.scope["state"]["csp_nonce"]


def _raw_query(request: AppRequest) -> str:
    return request.scope.get("query_string", b"").decode("latin-1")


def _raw_path(request: AppRequest) -> str:
    return request.scope.get("raw_path", b"").split(b"?", 1)[0].decode("latin-1")


def _security_policy() -> bytes:
    now = datetime.now(UTC)
    try:
        expires = now.replace(year=now.year + 1)
    except ValueError:
        # A policy generated on leap day remains valid for a complete year.
        expires = now.replace(year=now.year + 1, month=3, day=1)
    timestamp = expires.isoformat(timespec="seconds").replace("+00:00", "Z")
    body = "\n".join(
        (
            f"# Security contact information for {METADATA.site_url.removeprefix('https://')} ({METADATA.name})",
            "# Spec: https://www.rfc-editor.org/rfc/rfc9116",
            "",
            f"Contact: mailto:{METADATA.email}",
            f"Expires: {timestamp}",
            "Preferred-Languages: en,fr",
            f"Canonical: {METADATA.site_url}/.well-known/security.txt",
            f"Canonical: {METADATA.site_url}/security.txt",
            "",
        )
    )
    return body.encode()


def create_app(
    config: Config | None = None,
    *,
    assets: ApplicationAssets | None = None,
    collection: ArticleCollection | None = None,
    content_dir: Path = Path("content/articles"),
    static_dir: Path = Path("static"),
    logger: Logger | None = None,
) -> Litestar:
    """Build one fail-fast application from immutable startup snapshots."""
    runtime_config = config or Config.load()
    application_assets = assets or load_application_assets(static_dir)
    article_collection = collection or load_articles(content_dir, static_dir)
    site_logger = logger or configure_logging(runtime_config)

    public_articles = visible_articles(article_collection.all)
    page_articles = visible_articles(
        article_collection.all,
        include_drafts=runtime_config.environment is Environment.DEVELOPMENT,
    )
    summaries = article_summaries(public_articles)
    public_search = SearchIndex(public_articles)
    # Public pages and MCP can share the immutable index. Only a development
    # preview containing drafts needs a second copy of the full-text counters.
    page_search = public_search if page_articles == public_articles else SearchIndex(page_articles)
    related = related_article_index(page_articles)
    markdown_by_slug = article_markdown_index(article_collection.all)

    home_structured_data = get_structured_data()
    home_page = home_metadata(home_structured_data)
    not_found_page = not_found_metadata(home_structured_data)
    site_index = SitePage(
        slug="",
        title="Sites",
        description="Source-backed decision tools for AI architecture, infrastructure, and operating economics.",
        audience="",
        url=f"{METADATA.site_url}/sites/",
    )
    site_index_page = site_index_metadata(site_structured_data(site_index))
    site_pages_by_slug = {page.slug: page for page in SITE_PAGES}
    site_metadata_by_slug = {
        slug: site_page_metadata(page, site_structured_data(page)) for slug, page in site_pages_by_slug.items()
    }
    article_metadata_by_slug = {
        slug: article_metadata(article, get_structured_data(article))
        for slug, article in article_collection.by_slug.items()
    }
    renderer = Renderer(application_assets)
    # Rendering owns the single reviewed trusted-markup boundary for these
    # application-generated fragments.
    biography_html = tuple(markdown_to_html(paragraph) for paragraph in BIOGRAPHY)
    home_context: dict[str, object] = {
        "articles": page_articles,
        "biography_html": biography_html,
        "expertise": EXPERTISE,
        "experiences": EXPERIENCES,
        "leadership": LEADERSHIP,
        "badges": BADGES,
        "specializations": SPECIALIZATIONS,
        "open_source": OPEN_SOURCE,
        "youtube_series": YOUTUBE_SERIES,
        "services": get_services(),
    }

    profile = render_profile_json(summaries)
    feed = render_atom_feed(public_articles).encode()
    sitemap = render_sitemap(public_articles).encode()
    llms = render_llms_txt(public_articles)
    llms_full = render_llms_full(llms, public_articles).encode()
    llms_bytes = llms.encode()
    server_card = render_mcp_server_card()

    def render_page(
        request: AppRequest,
        template: PageTemplate,
        page: PageMetadata,
        context: dict[str, object] | None = None,
        *,
        status_code: int = 200,
    ) -> Response[str]:
        html = renderer.render(template, page=page, nonce=_request_nonce(request), context=context)
        return Response(html, headers={"cache-control": _NO_CACHE}, media_type="text/html", status_code=status_code)

    def render_not_found(request: AppRequest) -> Response[str]:
        return render_page(request, PageTemplate.NOT_FOUND, not_found_page, status_code=404)

    @route("/static/{asset_path:path}", http_method=_READ_METHODS)
    async def static_asset(asset_path: FromPath[str], request: AppRequest) -> ASGIApp:
        relative_path = asset_path.lstrip("/")
        route = f"/static/{relative_path}"
        digest = application_assets.hashes.get(route)
        static_root = static_dir.resolve()
        # Look up the immutable URL inventory before touching the filesystem.
        # Unknown paths (including NULs and dot segments) are client misses,
        # and files added after startup must not become public accidentally.
        path = (static_root / relative_path).resolve() if digest is not None else None
        if path is None or not path.is_relative_to(static_root) or not path.is_file():
            response = _static_response(
                b"404 page not found\n",
                "text/plain; charset=utf-8",
                _NO_CACHE,
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
        cache_control = _YEAR_CACHE if immutable else _DAY_CACHE
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

    @route("/static", http_method=_READ_METHODS, sync_to_thread=False)
    def static_root(request: AppRequest) -> Redirect | Response[bytes]:
        if not _raw_path(request).endswith("/"):
            query = _raw_query(request)
            return _redirect("/static/" + (f"?{query}" if query else ""))
        return _static_response(b"404 page not found\n", "text/plain; charset=utf-8", _NO_CACHE, status_code=404)

    # Cloud Run reserves some paths ending in "z"; keep one portable probe URL.
    @route("/health", http_method=_READ_METHODS, sync_to_thread=False)
    def health() -> Response[bytes]:
        return Response(b'{"status":"ok"}', headers={"content-type": "application/json; charset=utf-8"})

    @route(list(application_assets.root_files), http_method=_READ_METHODS, sync_to_thread=False)
    def root_file(request: AppRequest) -> Response[bytes]:
        response: StaticResponse = application_assets.root_files[request.scope["path"]]
        return _static_response(response.body, response.content_type, _DAY_CACHE)

    @route(["/security.txt", "/.well-known/security.txt"], http_method=_READ_METHODS, sync_to_thread=False)
    def security_policy() -> Response[bytes]:
        return _static_response(_security_policy(), "text/plain; charset=utf-8", _DAY_CACHE)

    @route("/api/profile", http_method=_READ_METHODS, sync_to_thread=False)
    def profile_api() -> Response[bytes]:
        return _static_response(
            profile,
            "application/json; charset=utf-8",
            _HOUR_CACHE_WITHOUT_REVALIDATION,
            cors=True,
        )

    @route(
        ["/mcp/server-card", "/.well-known/mcp/server-card.json"],
        http_method=_READ_METHODS,
        sync_to_thread=False,
    )
    def mcp_server_card() -> Response[bytes]:
        return _static_response(
            server_card,
            "application/mcp-server-card+json; charset=utf-8",
            _HOUR_CACHE,
            cors=True,
        )

    @route("/llms.txt", http_method=_READ_METHODS, sync_to_thread=False)
    def llms_index() -> Response[bytes]:
        return _static_response(llms_bytes, "text/plain; charset=utf-8", _HOUR_CACHE)

    @route("/llms-full.txt", http_method=_READ_METHODS, sync_to_thread=False)
    def llms_full_index() -> Response[bytes]:
        return _static_response(llms_full, "text/plain; charset=utf-8", _HOUR_CACHE)

    @route("/sitemap.xml", http_method=_READ_METHODS, sync_to_thread=False)
    def sitemap_index() -> Response[bytes]:
        return _static_response(sitemap, "application/xml; charset=utf-8", _HOUR_CACHE)

    @route("/articles/feed.xml", http_method=_READ_METHODS, sync_to_thread=False)
    def atom_feed() -> Response[bytes]:
        return _static_response(feed, "application/atom+xml; charset=utf-8", _HOUR_CACHE)

    @route("/articles", http_method=_READ_METHODS, sync_to_thread=True)
    def articles_index(request: AppRequest) -> Redirect | Response[str]:
        if not _raw_path(request).endswith("/"):
            query = _raw_query(request)
            return _redirect("/articles/" + (f"?{query}" if query else ""))
        view = article_index_data(
            page_articles,
            page_search,
            request.query_params.get("tag", ""),
            request.query_params.get("q", ""),
        )
        return render_page(
            request,
            PageTemplate.ARTICLES,
            article_index_metadata(view, home_structured_data),
            {"view": view},
        )

    @route("/articles/{slug:str}", http_method=_READ_METHODS, sync_to_thread=True)
    def article_redirect_or_markdown(
        slug: FromPath[str], request: AppRequest
    ) -> Redirect | Response[bytes] | Response[str]:
        if _raw_path(request).endswith("/"):
            article = article_collection.by_slug.get(slug)
            if article is None or (article.draft and runtime_config.environment is Environment.PRODUCTION):
                return render_not_found(request)
            related_sites = tuple(page for page in SITE_PAGES if page.relates_to(article.slug))
            return render_page(
                request,
                PageTemplate.ARTICLE,
                article_metadata_by_slug[article.slug],
                {
                    "article": article,
                    "article_html": article.html,
                    "related_articles": related[article.slug],
                    "related_site_pages": related_sites,
                },
            )
        if slug.endswith(".md"):
            article_slug = slug.removesuffix(".md")
            article = article_collection.by_slug.get(article_slug)
            if article is None or (article.draft and runtime_config.environment is Environment.PRODUCTION):
                return render_not_found(request)
            return _static_response(
                markdown_by_slug[article_slug].encode(),
                "text/markdown; charset=utf-8",
                _HOUR_CACHE,
                cors=True,
            )
        query = _raw_query(request)
        target = f"/articles/{quote(slug, safe='')}/"
        return _redirect(target + (f"?{query}" if query else ""))

    @route("/sites", http_method=_READ_METHODS, sync_to_thread=True)
    def sites_index(request: AppRequest) -> Redirect | Response[str]:
        if not _raw_path(request).endswith("/"):
            return _redirect("/sites/")
        return render_page(
            request,
            PageTemplate.SITES,
            site_index_page,
            {"site_pages": SITE_PAGES},
        )

    @route("/sites/{slug:str}", http_method=_READ_METHODS, sync_to_thread=True)
    def site_page(slug: FromPath[str], request: AppRequest) -> Redirect | Response[str]:
        if not _raw_path(request).endswith("/"):
            query = _raw_query(request)
            target = f"/sites/{quote(slug, safe='')}/"
            return _redirect(target + (f"?{query}" if query else ""))
        page = site_pages_by_slug.get(slug)
        if page is None or slug != "llm-self-hosting":
            return render_not_found(request)
        related_articles = tuple(article for article in public_articles if page.relates_to(article.slug))
        return render_page(
            request,
            PageTemplate.LLM_SELF_HOSTING,
            site_metadata_by_slug[slug],
            {
                "view": build_llm_self_hosting_view(request.query_params),
                "related_articles": related_articles,
            },
        )

    @route("/", http_method=_READ_METHODS, sync_to_thread=True)
    def home(request: AppRequest) -> Response[str]:
        return render_page(request, PageTemplate.HOME, home_page, home_context)

    @route(
        ["/articles/{slug:str}/{nested_path:path}", "/sites/{slug:str}/{nested_path:path}"],
        http_method=_READ_METHODS,
    )
    async def nested_content_not_found(
        slug: FromPath[str], nested_path: FromPath[str], request: AppRequest
    ) -> Response[str]:
        del slug, nested_path
        # A Litestar handler registered for multiple paths is registered more
        # than once; explicit offload avoids its sync wrapper being applied twice.
        return await sync_to_thread(render_not_found, request)

    @route("/{path:path}", http_method=_READ_METHODS, sync_to_thread=True)
    def not_found(path: FromPath[str], request: AppRequest) -> Response[str]:
        del path
        return render_not_found(request)

    mcp_server = create_mcp_server(summaries, public_search)
    mcp_app = mcp_server.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        max_request_body_size=_MCP_MAX_BODY_SIZE,
        transport_security=TransportSecuritySettings(
            allowed_hosts=[
                "www.fmind.dev",
                "www.fmind.dev:*",
                "fmind.dev",
                "fmind.dev:*",
                "testserver.local",
                "testserver.local:*",
                "localhost",
                "localhost:*",
                "127.0.0.1",
                "127.0.0.1:*",
            ],
            allowed_origins=[
                "https://www.fmind.dev",
                "https://fmind.dev",
                "http://testserver.local",
                "http://testserver.local:*",
                "http://localhost",
                "http://localhost:*",
                "http://127.0.0.1",
                "http://127.0.0.1:*",
            ],
        ),
    )
    mcp_route = asgi("/mcp", is_mount=True, copy_scope=True)(mcp_app)
    tracer_provider = configure_telemetry()
    plugins = (
        [
            OpenTelemetryPlugin(
                OpenTelemetryConfig(
                    tracer_provider=tracer_provider,
                    # Match net/http instrumentation's single server span.
                    exclude_spans=["receive", "send"],
                )
            )
        ]
        if tracer_provider is not None
        else []
    )

    @asynccontextmanager
    async def lifespan(_: Litestar) -> AsyncIterator[None]:
        try:
            async with mcp_app.router.lifespan_context(mcp_app):
                yield
        finally:
            if tracer_provider is not None and not shutdown_telemetry(tracer_provider):
                site_logger.error(
                    "telemetry shutdown incomplete",
                    timeout_seconds=TELEMETRY_SHUTDOWN_TIMEOUT_SECONDS,
                )

    def method_not_allowed(request: AppRequest, _: Exception) -> Response[str]:
        # The Go router's unqualified catch-all rendered the same noindex 404
        # document for unsupported methods instead of exposing a framework 405.
        return render_not_found(request)

    def internal_server_error(_: AppRequest, __: Exception) -> Response[bytes]:
        return _static_response(
            b"Internal Server Error\n",
            "text/plain; charset=utf-8",
            _NO_CACHE,
            status_code=500,
        )

    def record_exception(exc: Exception, scope: Scope) -> None:
        if getattr(exc, "status_code", 500) < 500:
            return
        state = scope.get("state", {})
        error_values: dict[str, object] = {
            "method": scope.get("method", ""),
            "path": state.get("request_path", scope.get("path", "")),
            "error_type": type(exc).__name__,
            "exc_info": exc,
        }
        error_values.update(trace_fields())
        site_logger.error(
            "unhandled request failure",
            **error_values,
        )

    application = Litestar(
        route_handlers=[
            static_asset,
            static_root,
            health,
            root_file,
            security_policy,
            profile_api,
            mcp_server_card,
            llms_index,
            llms_full_index,
            sitemap_index,
            atom_feed,
            articles_index,
            article_redirect_or_markdown,
            sites_index,
            site_page,
            home,
            mcp_route,
            nested_content_not_found,
            not_found,
        ],
        compression_config=CompressionConfig(backend="brotli", exclude=_COMPRESSION_EXCLUDE),
        exception_handlers={405: method_not_allowed, 500: internal_server_error},
        after_exception=[record_exception],
        lifespan=[lifespan],
        logging_config=None,
        openapi_config=None,
        plugins=plugins,
    )
    # Litestar applies configured middleware only after route resolution. Wrap
    # its full ASGI handler so routing errors and mounted MCP responses receive
    # the same security, analytics, and access-log boundary as normal pages.
    application.asgi_handler = SiteMiddleware(application.asgi_handler, runtime_config, site_logger)
    return application


app = create_app()
