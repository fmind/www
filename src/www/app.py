"""Litestar application assembly for every human and machine surface."""

import hashlib
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import quote

from litestar import Litestar, Request, asgi, route
from litestar.concurrency import sync_to_thread
from litestar.config.compression import CompressionConfig
from litestar.enums import HttpMethod
from litestar.handlers import HTTPRouteHandler
from litestar.params import FromPath
from litestar.plugins import PluginProtocol
from litestar.response import Redirect, Response
from litestar.types import ASGIApp, Scope

from www.agent_discovery import AGENT_LINKS, AGENT_SKILL_PATH, prefers_markdown, public_skill, render_api_catalog
from www.assets import STYLESHEET_PATH, ApplicationAssets, StaticResponse, load_application_assets
from www.config import Config, Environment
from www.connect import CONNECT_URL, LINKEDIN_URL, render_contact_card
from www.content import ArticleCollection, article_summaries, load_articles, visible_articles
from www.data import (
    BADGES,
    BIOGRAPHY,
    EXPERIENCES,
    EXPERTISE,
    LEADERSHIP,
    METADATA,
    OPEN_SOURCE,
    SERVICES,
    SITE_PAGES,
    SPECIALIZATIONS,
    YOUTUBE_SERIES,
    get_structured_data,
    markdown_to_html,
)
from www.log import configure_logging
from www.mcp import create_mcp_http_app, create_mcp_server, render_mcp_server_card
from www.middleware import Logger, SiteMiddleware, trace_fields
from www.models import PageMetadata
from www.news import (
    NEWS_FEED_PATH,
    NewsEdition,
    adjacent_editions,
    load_news,
    render_news_feed,
    render_news_index_markdown,
    render_news_json,
    render_news_markdown,
    render_news_schema,
    split_news_index,
)
from www.pages import (
    ARTICLE_INDEX_STRUCTURED_DATA,
    agents_metadata,
    article_index_metadata,
    article_metadata,
    connect_metadata,
    home_metadata,
    news_edition_metadata,
    news_index_metadata,
    not_found_metadata,
    privacy_metadata,
    scan_metadata,
    site_index_metadata,
    site_page_metadata,
    site_structured_data,
)
from www.publications import (
    article_index_data,
    article_markdown_index,
    related_article_index,
    render_atom_feed,
    render_home_markdown,
    render_llms_full,
    render_llms_txt,
    render_profile_json,
    render_profile_schema,
    render_sitemap,
)
from www.ranges import etag_matches
from www.rendering import PageTemplate, Renderer
from www.search import SearchIndex
from www.sites.calculator import build_llm_self_hosting_view
from www.sites.mcp_context_cost.calculator import view_from_query
from www.static import static_asset_response
from www.telemetry import TELEMETRY_SHUTDOWN_TIMEOUT_SECONDS, configure_telemetry, shutdown_telemetry

_DAY_CACHE = "public, max-age=86400, must-revalidate"
_HOUR_CACHE = "public, max-age=3600, must-revalidate"
_HOUR_CACHE_WITHOUT_REVALIDATION = "public, max-age=3600"
_NO_CACHE = "no-cache"
# Static ETags and byte ranges describe the on-disk representation. Compressing
# it afterward invalidates both contracts. The page stylesheet is served from
# memory at /styles.css with a weak ETag, so it still benefits from Brotli.
# The MCP endpoint answers single JSON bodies (json_response=True, no subscriptions/listen),
# so it compresses like other responses.
_COMPRESSION_EXCLUDE = r"^/(?:static/|(?:(?:logo|banner)\.png|portrait\.jpg)$)"
_READ_METHODS = (HttpMethod.GET, HttpMethod.HEAD)

# A plain alias, not a `type` statement: Litestar 2.25+ must resolve handler
# `request` annotations to Request at runtime to accept the reserved kwarg.
AppRequest = Request[Any, Any, Any]

# The template and server-owned view of each page registered in data.SITE_PAGES.
_SITE_VIEWS: dict[str, tuple[PageTemplate, Callable[[AppRequest], object]]] = {
    "llm-self-hosting": (
        PageTemplate.LLM_SELF_HOSTING,
        lambda request: build_llm_self_hosting_view(request.query_params),
    ),
    "mcp-context-cost": (
        PageTemplate.MCP_CONTEXT_COST,
        lambda request: view_from_query(request.query_params.dict()),
    ),
}


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


@dataclass(frozen=True, slots=True)
class _Snapshot:
    """An immutable startup body with its validator, hashed once instead of per request."""

    body: bytes
    etag: str

    @classmethod
    def of(cls, body: bytes) -> _Snapshot:
        # Weak: compression may re-encode the body, but the content is identical.
        return cls(body, f'W/"{hashlib.sha256(body).hexdigest()}"')


def _snapshot_response(
    request: AppRequest,
    snapshot: _Snapshot,
    content_type: str,
    cache_control: str,
    *,
    cors: bool = False,
    extra_headers: dict[str, str] | None = None,
) -> Response[bytes]:
    """Serve a snapshot, or a 304 that keeps the 200's validator, cache, Vary, and CORS fields."""
    headers = {**(extra_headers or {}), "etag": snapshot.etag}
    if etag_matches(request.headers.get("if-none-match", ""), snapshot.etag):
        headers["cache-control"] = cache_control
        if cors:
            headers["access-control-allow-origin"] = "*"
        return Response(b"", headers=headers, status_code=304)
    return _static_response(snapshot.body, content_type, cache_control, cors=cors, extra_headers=headers)


def _snapshot_route(
    path: str,
    snapshot: _Snapshot,
    content_type: str,
    cache_control: str = _HOUR_CACHE,
    *,
    cors: bool = False,
    extra_headers: dict[str, str] | None = None,
) -> HTTPRouteHandler:
    """Route one startup snapshot; these routes differ only by their arguments."""

    @route(path, http_method=_READ_METHODS, sync_to_thread=False)
    def snapshot_route(request: AppRequest) -> Response[bytes]:
        return _snapshot_response(
            request, snapshot, content_type, cache_control, cors=cors, extra_headers=extra_headers
        )

    return snapshot_route


def _markdown_response(
    request: AppRequest, snapshot: _Snapshot, canonical_url: str, *, negotiated: bool, noindex: bool = False
) -> Response[bytes]:
    """Serve a Markdown representation that credits its canonical HTML page."""
    headers = {"link": f'<{canonical_url}>; rel="canonical"'}
    if negotiated:
        headers["vary"] = "Accept"
    if noindex:
        headers["x-robots-tag"] = "noindex"
    return _snapshot_response(
        request, snapshot, "text/markdown; charset=utf-8", _HOUR_CACHE, cors=True, extra_headers=headers
    )


def _redirect(path: str) -> Redirect:
    return Redirect(path, status_code=301)


def _redirect_keeping_query(request: AppRequest, path: str) -> Redirect:
    query = _raw_query(request)
    return _redirect(path + (f"?{query}" if query else ""))


def _request_nonce(request: AppRequest) -> str:
    return request.scope["state"]["csp_nonce"]


def _raw_query(request: AppRequest) -> str:
    return request.scope.get("query_string", b"").decode("latin-1")


def _request_path(request: AppRequest) -> str:
    # Routing strips trailing slashes. SiteMiddleware keeps the decoded public
    # path, so an encoded slash (/agents%2F) redirects like a literal one.
    return request.scope["state"]["request_path"]


@contextmanager
def _timed(phases: dict[str, float], name: str) -> Generator[None]:
    """Record one startup phase's wall time in seconds."""
    started = perf_counter()
    try:
        yield
    finally:
        phases[name] = round(perf_counter() - started, 3)


def _security_policy() -> bytes:
    # RFC 9116 section 2.5.5 recommends an expiry less than a year ahead.
    expires = datetime.now(UTC) + timedelta(days=364)
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
    news: tuple[NewsEdition, ...] | None = None,
    logger: Logger | None = None,
) -> Litestar:
    """Build one fail-fast application from immutable startup snapshots."""
    started = perf_counter()
    # Wall seconds per startup phase, logged once so cold starts show where time goes.
    phases: dict[str, float] = {}
    runtime_config = config or Config.load()
    site_logger = logger or configure_logging(runtime_config)
    with _timed(phases, "assets"):
        application_assets = assets or load_application_assets()
    with _timed(phases, "articles"):
        article_collection = collection or load_articles(image_sizes=application_assets.image_sizes)
    with _timed(phases, "news"):
        editions = load_news() if news is None else news

    public_articles = visible_articles(article_collection.all)
    page_articles = visible_articles(
        article_collection.all,
        include_drafts=runtime_config.environment is Environment.DEVELOPMENT,
    )
    # Drafts are routable only in development, exactly like the archive.
    routable_articles = {article.slug: article for article in page_articles}
    summaries = article_summaries(public_articles)
    with _timed(phases, "search"):
        public_search = SearchIndex(public_articles)
        # Public pages and MCP can share the immutable index. Only a development
        # preview containing drafts needs a second copy of the full-text counters.
        page_search = public_search if page_articles == public_articles else SearchIndex(page_articles)
    with _timed(phases, "publications"):
        related = related_article_index(page_articles)
        markdown_by_slug = article_markdown_index(article_collection.all)
        markdown_snapshots = {slug: _Snapshot.of(text.encode()) for slug, text in markdown_by_slug.items()}
        profile = _Snapshot.of(render_profile_json(summaries))
        profile_schema = _Snapshot.of(render_profile_schema())
        feed = _Snapshot.of(render_atom_feed(public_articles).encode())
        news_modified = max((edition.modified() for edition in editions), default=None)
        sitemap = _Snapshot.of(render_sitemap(public_articles, news_modified).encode())
        llms = render_llms_txt(public_articles)
        llms_full = _Snapshot.of(render_llms_full(llms, public_articles, markdown_by_slug).encode())
        llms_index_snapshot = _Snapshot.of(llms.encode())
        home_markdown = _Snapshot.of(render_home_markdown(summaries))
        api_catalog = _Snapshot.of(render_api_catalog())
        skill_body, skill_index = (_Snapshot.of(body) for body in public_skill())
        root_files = {path: _Snapshot.of(response.body) for path, response in application_assets.root_files.items()}
        news_api = _Snapshot.of(render_news_json(editions))
        news_schema = _Snapshot.of(render_news_schema())
        news_index_markdown = _Snapshot.of(render_news_index_markdown(editions).encode())
        news_markdown = {edition.slug: _Snapshot.of(render_news_markdown(edition).encode()) for edition in editions}
        news_feed = _Snapshot.of(render_news_feed(editions).encode())
        # Weak: compression may re-encode the body, but the CSS it carries is identical.
        stylesheet_snapshot = _Snapshot(
            application_assets.stylesheet.encode(), f'W/"{application_assets.stylesheet_digest}"'
        )
    server_card: _Snapshot | None = None

    # Page metadata and validated JSON-LD feed the renderer, so they count toward its phase.
    renderer_started = perf_counter()
    home_structured_data = get_structured_data()
    home_page = home_metadata(home_structured_data)
    connect_page = connect_metadata()
    scan_page = scan_metadata()
    contact_card = render_contact_card()
    not_found_page = not_found_metadata()
    agents_page = agents_metadata()
    privacy_page = privacy_metadata()
    site_index_page = site_index_metadata()
    site_pages_by_slug = {page.slug: page for page in SITE_PAGES}
    if unmatched := sorted(site_pages_by_slug.keys() ^ _SITE_VIEWS.keys()):
        msg = (
            f"data.SITE_PAGES and the site views in app.py must list the same slugs; unmatched: {', '.join(unmatched)}"
        )
        raise RuntimeError(msg)
    site_metadata_by_slug = {
        slug: site_page_metadata(page, site_structured_data(page)) for slug, page in site_pages_by_slug.items()
    }
    news_page = news_index_metadata()
    editions_by_slug = {edition.slug: edition for edition in editions}
    edition_metadata_by_slug = {edition.slug: news_edition_metadata(edition) for edition in editions}
    edition_neighbours = adjacent_editions(editions)
    news_context: dict[str, object] = {"index": split_news_index(editions), "news_feed_path": NEWS_FEED_PATH}
    article_metadata_by_slug = {
        slug: article_metadata(article, get_structured_data(article))
        for slug, article in article_collection.by_slug.items()
    }
    # Rendering owns the single reviewed trusted-markup boundary for these
    # application-generated fragments.
    biography_html = tuple(markdown_to_html(paragraph) for paragraph in BIOGRAPHY)
    renderer = Renderer(
        application_assets,
        article_html=tuple(article.html for article in article_collection.all),
        biography_html=biography_html,
        structured_data=(
            home_structured_data,
            ARTICLE_INDEX_STRUCTURED_DATA,
            site_index_page.structured_data,
            connect_page.structured_data,
            scan_page.structured_data,
            agents_page.structured_data,
            privacy_page.structured_data,
            news_page.structured_data,
            *(page.structured_data for page in edition_metadata_by_slug.values()),
            *(page.structured_data for page in site_metadata_by_slug.values()),
            *(page.structured_data for page in article_metadata_by_slug.values()),
        ),
    )
    phases["renderer"] = round(perf_counter() - renderer_started, 3)
    home_context: dict[str, object] = {
        "biography_html": biography_html,
        "expertise": EXPERTISE,
        "experiences": EXPERIENCES,
        "leadership": LEADERSHIP,
        "badges": BADGES,
        "specializations": SPECIALIZATIONS,
        "open_source": OPEN_SOURCE,
        "youtube_series": YOUTUBE_SERIES,
        "services": SERVICES,
    }

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

    static_root_dir = Path("static").resolve()

    @route("/static/{asset_path:path}", http_method=_READ_METHODS)
    async def static_asset(asset_path: FromPath[str], request: AppRequest) -> ASGIApp:
        return await static_asset_response(asset_path, request, application_assets, static_root_dir)

    @route(["/banner.png", "/logo.png", "/portrait.jpg"], http_method=_READ_METHODS)
    async def branding_asset(request: AppRequest) -> ASGIApp:
        return await static_asset_response(request.scope["path"], request, application_assets, static_root_dir)

    # The router does not backtrack from /static/{asset_path} to the catch-all, so the bare
    # directory needs its own miss; without it Litestar answers with a JSON 404.
    @route("/static", http_method=_READ_METHODS, sync_to_thread=False)
    def static_root() -> Response[bytes]:
        return _static_response(b"404 page not found\n", "text/plain; charset=utf-8", _NO_CACHE, status_code=404)

    @route(STYLESHEET_PATH, http_method=_READ_METHODS, sync_to_thread=False)
    def stylesheet(request: AppRequest) -> Response[bytes]:
        # Only the current content-addressed URL is immutable; any other version revalidates.
        immutable = request.query_params.getall("v", []) == [application_assets.stylesheet_digest]
        cache_control = "public, max-age=31536000, immutable" if immutable else _DAY_CACHE
        return _snapshot_response(request, stylesheet_snapshot, "text/css; charset=utf-8", cache_control)

    # Cloud Run reserves some paths ending in "z"; keep one portable probe URL.
    @route("/health", http_method=_READ_METHODS, sync_to_thread=False)
    def health() -> Response[bytes]:
        return Response(b'{"status":"ok"}', headers={"content-type": "application/json; charset=utf-8"})

    @route(list(application_assets.root_files), http_method=_READ_METHODS, sync_to_thread=False)
    def root_file(request: AppRequest) -> Response[bytes]:
        path = request.scope["path"]
        response: StaticResponse = application_assets.root_files[path]
        return _snapshot_response(request, root_files[path], response.content_type, _DAY_CACHE)

    @route(["/security.txt", "/.well-known/security.txt"], http_method=_READ_METHODS, sync_to_thread=False)
    def security_policy() -> Response[bytes]:
        return _static_response(_security_policy(), "text/plain; charset=utf-8", _DAY_CACHE)

    json_type = "application/json; charset=utf-8"
    schema_type = "application/schema+json; charset=utf-8"
    text_type = "text/plain; charset=utf-8"
    atom_type = "application/atom+xml; charset=utf-8"
    snapshot_routes = [
        _snapshot_route(
            "/api/profile",
            profile,
            json_type,
            _HOUR_CACHE_WITHOUT_REVALIDATION,
            cors=True,
            extra_headers={"link": '</api/profile/schema.json>; rel="describedby"; type="application/schema+json"'},
        ),
        _snapshot_route("/api/profile/schema.json", profile_schema, schema_type, cors=True),
        _snapshot_route(
            "/api/news",
            news_api,
            json_type,
            cors=True,
            extra_headers={"link": '</api/news/schema.json>; rel="describedby"; type="application/schema+json"'},
        ),
        _snapshot_route("/api/news/schema.json", news_schema, schema_type, cors=True),
        _snapshot_route("/llms.txt", llms_index_snapshot, text_type, cors=True),
        # Agents read the bulk export; search engines should index the individual articles instead.
        _snapshot_route("/llms-full.txt", llms_full, text_type, cors=True, extra_headers={"x-robots-tag": "noindex"}),
        _snapshot_route("/sitemap.xml", sitemap, "application/xml; charset=utf-8"),
        _snapshot_route("/articles/feed.xml", feed, atom_type),
        _snapshot_route(NEWS_FEED_PATH, news_feed, atom_type),
        _snapshot_route(
            "/.well-known/api-catalog",
            api_catalog,
            'application/linkset+json; profile="https://www.rfc-editor.org/info/rfc9727"; charset=utf-8',
            cors=True,
            extra_headers={"link": AGENT_LINKS},
        ),
        _snapshot_route("/.well-known/agent-skills/index.json", skill_index, json_type, cors=True),
        _snapshot_route(AGENT_SKILL_PATH, skill_body, "text/markdown; charset=utf-8", cors=True),
    ]

    @route(
        ["/mcp/server-card", "/.well-known/mcp/server-card.json"],
        http_method=_READ_METHODS,
        sync_to_thread=False,
    )
    def mcp_server_card(request: AppRequest) -> Response[bytes]:
        if server_card is None:
            raise RuntimeError("MCP discovery requires application startup")
        return _snapshot_response(
            request,
            server_card,
            "application/mcp-server-card+json; charset=utf-8",
            _HOUR_CACHE,
            cors=True,
        )

    @route("/news", http_method=_READ_METHODS, sync_to_thread=True)
    def news_index(request: AppRequest) -> Redirect | Response[bytes] | Response[str]:
        if not _request_path(request).endswith("/"):
            return _redirect("/news/")
        if prefers_markdown(request.headers.get("accept", "")):
            return _markdown_response(request, news_index_markdown, f"{METADATA.site_url}/news/", negotiated=True)
        response = render_page(request, PageTemplate.NEWS, news_page, news_context)
        response.headers["vary"] = "Accept"
        return response

    @route("/news/{slug:str}", http_method=_READ_METHODS, sync_to_thread=True)
    def news_edition(slug: FromPath[str], request: AppRequest) -> Redirect | Response[bytes] | Response[str]:
        if _request_path(request).endswith("/"):
            edition = editions_by_slug.get(slug)
            if edition is None:
                return render_not_found(request)
            if prefers_markdown(request.headers.get("accept", "")):
                return _markdown_response(request, news_markdown[slug], edition.url, negotiated=True, noindex=True)
            older, newer = edition_neighbours[slug]
            response = render_page(
                request,
                PageTemplate.NEWS_EDITION,
                edition_metadata_by_slug[slug],
                {"edition": edition, "older": older, "newer": newer, "news_feed_path": NEWS_FEED_PATH},
            )
            response.headers["vary"] = "Accept"
            response.headers["link"] = f'<{edition.markdown_path()}>; rel="alternate"; type="text/markdown"'
            return response
        if slug.endswith(".md"):
            edition = editions_by_slug.get(slug.removesuffix(".md"))
            if edition is None:
                return render_not_found(request)
            return _markdown_response(request, news_markdown[edition.slug], edition.url, negotiated=False, noindex=True)
        return _redirect(f"/news/{quote(slug, safe='')}/")

    @route("/agents", http_method=_READ_METHODS, sync_to_thread=True)
    def agents(request: AppRequest) -> Redirect | Response[str]:
        if _request_path(request).endswith("/"):
            return _redirect("/agents")
        return render_page(request, PageTemplate.AGENTS, agents_page)

    @route("/privacy", http_method=_READ_METHODS, sync_to_thread=True)
    def privacy(request: AppRequest) -> Redirect | Response[str]:
        if _request_path(request).endswith("/"):
            return _redirect("/privacy")
        return render_page(request, PageTemplate.PRIVACY, privacy_page)

    @route("/connect", http_method=_READ_METHODS, sync_to_thread=True)
    def connect(request: AppRequest) -> Redirect | Response[str]:
        if _request_path(request).endswith("/"):
            return _redirect("/connect")
        return render_page(
            request,
            PageTemplate.CONNECT,
            connect_page,
            {"linkedin_url": LINKEDIN_URL},
        )

    @route("/scan", http_method=_READ_METHODS, sync_to_thread=True)
    def scan(request: AppRequest) -> Redirect | Response[str]:
        if _request_path(request).endswith("/"):
            return _redirect("/scan")
        return render_page(request, PageTemplate.SCAN, scan_page, {"connect_url": CONNECT_URL})

    @route("/connect.vcf", http_method=_READ_METHODS, sync_to_thread=False)
    def contact() -> Response[bytes]:
        return _static_response(
            contact_card,
            "text/vcard; charset=utf-8",
            _NO_CACHE,
            extra_headers={"content-disposition": 'attachment; filename="mederic-hurier.vcf"'},
        )

    @route("/articles", http_method=_READ_METHODS, sync_to_thread=True)
    def articles_index(request: AppRequest) -> Redirect | Response[str]:
        if not _request_path(request).endswith("/"):
            return _redirect_keeping_query(request, "/articles/")
        view = article_index_data(
            page_articles,
            page_search,
            request.query_params.get("tag", ""),
            request.query_params.get("q", ""),
        )
        return render_page(
            request,
            PageTemplate.ARTICLES,
            article_index_metadata(view),
            {"view": view},
        )

    @route("/articles/{slug:str}", http_method=_READ_METHODS, sync_to_thread=True)
    def article_redirect_or_markdown(
        slug: FromPath[str], request: AppRequest
    ) -> Redirect | Response[bytes] | Response[str]:
        if _request_path(request).endswith("/"):
            article = routable_articles.get(slug)
            if article is None:
                return render_not_found(request)
            if prefers_markdown(request.headers.get("accept", "")):
                return _markdown_response(request, markdown_snapshots[slug], article.url, negotiated=True)
            related_sites = tuple(page for page in SITE_PAGES if page.relates_to(article.slug))
            response = render_page(
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
            response.headers["vary"] = "Accept"
            response.headers["link"] = f'<{article.markdown_path()}>; rel="alternate"; type="text/markdown"'
            return response
        if slug.endswith(".md"):
            article = routable_articles.get(slug.removesuffix(".md"))
            if article is None:
                return render_not_found(request)
            # The fixed export is a duplicate representation; search engines credit the article page.
            return _markdown_response(request, markdown_snapshots[article.slug], article.url, negotiated=False)
        return _redirect_keeping_query(request, f"/articles/{quote(slug, safe='')}/")

    @route("/sites", http_method=_READ_METHODS, sync_to_thread=True)
    def sites_index(request: AppRequest) -> Redirect | Response[str]:
        if not _request_path(request).endswith("/"):
            return _redirect("/sites/")
        return render_page(
            request,
            PageTemplate.SITES,
            site_index_page,
            {"site_pages": SITE_PAGES},
        )

    @route("/sites/{slug:str}", http_method=_READ_METHODS, sync_to_thread=True)
    def site_page(slug: FromPath[str], request: AppRequest) -> Redirect | Response[str]:
        if not _request_path(request).endswith("/"):
            return _redirect_keeping_query(request, f"/sites/{quote(slug, safe='')}/")
        if slug not in site_pages_by_slug:
            return render_not_found(request)
        template, build_view = _SITE_VIEWS[slug]
        return render_page(request, template, site_metadata_by_slug[slug], {"view": build_view(request)})

    @route("/", http_method=_READ_METHODS, sync_to_thread=True)
    def home(request: AppRequest) -> Response[str] | Response[bytes]:
        headers = {"vary": "Accept", "link": AGENT_LINKS}
        if prefers_markdown(request.headers.get("accept", "")):
            return _snapshot_response(
                request, home_markdown, "text/markdown; charset=utf-8", _HOUR_CACHE, cors=True, extra_headers=headers
            )
        response = render_page(request, PageTemplate.HOME, home_page, home_context)
        response.headers.update(headers)
        return response

    # Routes, not a 404 exception handler: exception handlers run synchronously
    # on the event loop and skip route compression. The router does not backtrack
    # from /articles/{slug} to /{path}, so nested content paths need their own entry.
    @route(
        [
            "/{path:path}",
            "/articles/{slug:str}/{nested_path:path}",
            "/news/{slug:str}/{nested_path:path}",
            "/sites/{slug:str}/{nested_path:path}",
        ],
        http_method=_READ_METHODS,
    )
    async def not_found(request: AppRequest) -> Response[str]:
        # Litestar wraps a multi-path sync handler once per path, so offload explicitly.
        return await sync_to_thread(render_not_found, request)

    with _timed(phases, "mcp"):
        mcp_server = create_mcp_server(
            summaries,
            public_search,
            public_articles,
            markdown_by_slug,
            editions,
            profile_json_bytes=profile.body,
        )
        mcp_app = create_mcp_http_app(mcp_server)
    # An exact route, not a mount: a mount matches by prefix without a segment
    # boundary, so /mcpx or /mcp/foo would get Starlette's plain-text 404.
    mcp_route = asgi("/mcp", copy_scope=True)(mcp_app)
    tracer_provider = configure_telemetry()
    plugins: list[PluginProtocol] = []
    if tracer_provider is not None:
        # Deferred with the SDK: tracing is opt-in, so untraced processes never import it here.
        from litestar.plugins.opentelemetry import OpenTelemetryConfig, OpenTelemetryPlugin

        plugins.append(
            OpenTelemetryPlugin(
                # Emit one server span per request.
                OpenTelemetryConfig(tracer_provider=tracer_provider, exclude_spans=["receive", "send"])
            )
        )

    @asynccontextmanager
    async def lifespan(_: Litestar) -> AsyncGenerator[None]:
        nonlocal server_card
        try:
            server_card = _Snapshot.of(await render_mcp_server_card(mcp_server))
            async with mcp_app.router.lifespan_context(mcp_app):
                yield
        finally:
            if tracer_provider is not None and not shutdown_telemetry(tracer_provider):
                site_logger.error(
                    "telemetry shutdown incomplete",
                    timeout_seconds=TELEMETRY_SHUTDOWN_TIMEOUT_SECONDS,
                )

    def method_not_allowed(request: AppRequest, _: Exception) -> Response[str]:
        # Keep unsupported methods on the same noindex 404 surface as unknown paths.
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
        error_values.update(trace_fields(state.get("cloud_trace", ""), tracing=tracer_provider is not None))
        site_logger.error(
            "unhandled request failure",
            **error_values,
        )

    application = Litestar(
        route_handlers=[
            static_asset,
            branding_asset,
            stylesheet,
            static_root,
            health,
            root_file,
            security_policy,
            *snapshot_routes,
            mcp_server_card,
            news_index,
            news_edition,
            connect,
            privacy,
            agents,
            scan,
            contact,
            articles_index,
            article_redirect_or_markdown,
            sites_index,
            site_page,
            home,
            mcp_route,
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
    # its full ASGI handler so routing errors and MCP responses receive
    # the same security, analytics, and access-log boundary as normal pages.
    application.asgi_handler = SiteMiddleware(
        application.asgi_handler, runtime_config, site_logger, tracing=tracer_provider is not None
    )
    phases["total"] = round(perf_counter() - started, 3)
    site_logger.info("application startup timed", phase_seconds=phases)
    return application


app = create_app()
