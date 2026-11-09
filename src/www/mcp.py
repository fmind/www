"""Read-only Model Context Protocol portfolio server and discovery card."""

import json
from collections.abc import Mapping, Sequence
from importlib.metadata import version
from typing import Annotated, Any, cast, override

from mcp.server.caching import CACHEABLE_METHODS, CacheableMethod, CacheHint
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecurityMiddleware, TransportSecuritySettings
from mcp.shared.exceptions import MCPError
from mcp_types import (
    INVALID_PARAMS,
    CallToolResult,
    GetPromptResult,
    Icon,
    InputRequiredResult,
    Prompt,
    Tool,
    ToolAnnotations,
)
from mcp_types.version import LATEST_MODERN_VERSION
from pydantic import BaseModel, ConfigDict, Field
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from www.data import (
    BADGES,
    BIOGRAPHY,
    EXPERIENCES,
    EXPERTISE,
    LEADERSHIP,
    METADATA,
    OPEN_SOURCE,
    PAPERS,
    SERVICES,
    SPECIALIZATIONS,
    THESIS,
    YOUTUBE_SERIES,
)
from www.models import (
    Article,
    ArticleSummary,
    CertificationBadge,
    CertificationEntry,
    ExpertiseCard,
    LeadershipRole,
    Metadata,
    Playlist,
    Project,
    ResearchPaper,
    Service,
    Thesis,
    WorkExperience,
)
from www.news import NewsEdition, NewsEditionSummary, render_news_markdown, search_news_editions
from www.publications import article_sections, render_profile_json
from www.search import SEARCH_QUERY_LIMIT, SearchIndex, normalize_search_query
from www.sites.agent import HostingResult, compare_hosting
from www.sites.mcp_context_cost.calculator import (
    DEFAULT_REQUESTS,
    MAX_REQUESTS,
    SERVER_IDS,
    ContextResult,
    ServerId,
    compare_context,
)
from www.tags import tag_names

# The card advertises the newest stateless revision the installed SDK serves.
MCP_PROTOCOL_VERSION = LATEST_MODERN_VERSION
MCP_PROFILE_URI = "portfolio://profile.json"
MCP_CACHE_TTL_MS = 3_600_000
DEFAULT_SEARCH_RESULTS = 10
MAXIMUM_SEARCH_RESULTS = 50
# Bound text that results echo or interpolate; a brief may paste a whole job description.
TAG_LIMIT = 64
BRIEF_LIMIT = 10_000
AUDIENCE_LIMIT = 200

_TITLE = f"{METADATA.name} ({METADATA.alternate_name}) — {METADATA.job_title} Portfolio"
_WEBSITE_URL = f"{METADATA.site_url}/"

_ICON_URL = f"{METADATA.site_url}/static/img/favicons/icon-192.png"
_DESCRIPTION = f"{METADATA.description} Read-only access to the public profile, services, articles, news, and sites."
_ICONS = [Icon(src=_ICON_URL, mime_type="image/png", sizes=["192x192"])]
_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
_CACHE_HINTS = {
    cast(CacheableMethod, method): CacheHint(ttl_ms=MCP_CACHE_TTL_MS, scope="public") for method in CACHEABLE_METHODS
}

_PROMPT_ARGUMENT_TITLES = {
    ("assess_fit", "brief"): "Role or project brief",
    ("brief_me", "audience"): "Audience",
}
_PROMPT_RESULT_DESCRIPTIONS = {
    "assess_fit": "A structured, evidence-based fit assessment using the portfolio tools.",
    "brief_me": "An audience-specific briefing grounded in the full portfolio.",
}


class _PortfolioMCPServer(MCPServer[None]):
    """Preserve prompt metadata and reject inputs that MCPServer would accept silently."""

    @override
    async def list_tools(self) -> list[Tool]:
        # Advertise the closed argument set that call_tool enforces.
        return [
            tool.model_copy(update={"input_schema": {**tool.input_schema, "additionalProperties": False}})
            for tool in await super().list_tools()
        ]

    @override
    async def call_tool(
        self, name: str, arguments: dict[str, Any], context: Context[None, Any] | None = None
    ) -> CallToolResult | InputRequiredResult:
        tool = next((tool for tool in await super().list_tools() if tool.name == name), None)
        if tool is None:
            # The spec lists unknown tools, like unknown prompts, as protocol errors
            # (-32602); the SDK would answer with an isError tool result instead.
            raise MCPError(INVALID_PARAMS, f"Unknown tool: {name}")
        # The SDK ignores unknown keys, so a misspelled argument would silently
        # apply its default. Fail like an invalid value: an isError tool result.
        known = tool.input_schema.get("properties", {})
        if unknown := sorted(set(arguments) - set(known)):
            expected = ", ".join(known) or "no arguments"
            raise ToolError(f"Unknown argument(s) for {name}: {', '.join(unknown)}; expected: {expected}")
        return await super().call_tool(name, arguments, context)

    @override
    async def list_prompts(self) -> list[Prompt]:
        prompts = await super().list_prompts()
        return [
            prompt.model_copy(
                update={
                    "arguments": [
                        argument.model_copy(
                            update={"title": _PROMPT_ARGUMENT_TITLES.get((prompt.name, argument.name), argument.title)}
                        )
                        for argument in prompt.arguments or []
                    ]
                }
            )
            for prompt in prompts
        ]

    @override
    async def get_prompt(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        context: Context[None, Any] | None = None,
    ) -> GetPromptResult | InputRequiredResult:
        try:
            result = await super().get_prompt(name, arguments, context)
        except ValueError as exc:
            # MCPServer reports unknown prompts and missing or extra arguments as
            # ValueError, which the dispatcher logs at ERROR and returns as an
            # internal error. They are caller mistakes: -32602 without an alert.
            raise MCPError(INVALID_PARAMS, str(exc)) from exc
        if isinstance(result, InputRequiredResult):
            return result
        description = _PROMPT_RESULT_DESCRIPTIONS.get(name)
        return result if description is None else result.model_copy(update={"description": description})


class _ResultModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class ProfileResult(_ResultModel):
    metadata: Metadata
    biography: tuple[str, ...]
    leadership: tuple[LeadershipRole, ...]
    expertise: tuple[ExpertiseCard, ...]


class ExperienceResult(_ResultModel):
    experience: tuple[WorkExperience, ...]


class CertificationsResult(_ResultModel):
    certifications: tuple[CertificationBadge, ...]
    specializations: tuple[CertificationEntry, ...]


class PublicationsResult(_ResultModel):
    thesis: Thesis
    papers: tuple[ResearchPaper, ...]
    articles: tuple[ArticleSummary, ...]


class ProjectsResult(_ResultModel):
    open_source: tuple[Project, ...]
    youtube_series: tuple[Playlist, ...]


class ServicesResult(_ResultModel):
    services: tuple[Service, ...]


class SearchArticlesResult(_ResultModel):
    query: str
    articles: tuple[ArticleSummary, ...]
    total: int


class ArticleResult(_ResultModel):
    article: ArticleSummary
    canonical_url: str
    markdown: str
    sections: tuple[dict[str, str], ...]


class SearchNewsResult(_ResultModel):
    query: str
    editions: tuple[NewsEditionSummary, ...]
    total: int


class NewsResult(_ResultModel):
    edition: NewsEditionSummary
    canonical_url: str
    markdown: str


def build_version() -> str:
    """Return the package version in the server implementation format."""
    return f"v{version('www')}"


def create_mcp_server(
    articles: tuple[ArticleSummary, ...],
    index: SearchIndex,
    publications: tuple[Article, ...],
    markdown_by_slug: Mapping[str, str],
    news: Sequence[NewsEdition] = (),
    *,
    profile_json_bytes: bytes | None = None,
) -> MCPServer[None]:
    """Build the immutable portfolio MCP server."""
    profile_json = (profile_json_bytes or render_profile_json(articles)).decode()
    summaries_by_slug = {summary.slug: summary for summary in articles}
    article_results = {
        article.slug: ArticleResult(
            article=summaries_by_slug.get(article.slug) or article.summary(),
            canonical_url=article.url,
            markdown=markdown_by_slug[article.slug],
            sections=article_sections(article),
        )
        for article in publications
        if not article.draft
    }
    news_summaries = tuple(edition.summary() for edition in news)
    news_results = {
        edition.slug: NewsResult(
            edition=summary,
            canonical_url=edition.url,
            markdown=render_news_markdown(edition),
        )
        for edition, summary in zip(news, news_summaries, strict=True)
    }
    server: MCPServer[None] = _PortfolioMCPServer(
        name="www",
        title=_TITLE,
        description=_DESCRIPTION,
        instructions=(
            f"Query the portfolio of {METADATA.name} ({METADATA.alternate_name}): {METADATA.headline_primary}. "
            "Explore profile, leadership, work experience, credentials, publications, projects, and services. "
            "Search and read published articles with citations, browse daily curated tech news, or compare LLM hosting and MCP context costs using the calculators."
        ),
        website_url=_WEBSITE_URL,
        icons=_ICONS,
        version=build_version(),
        cache_hints=_CACHE_HINTS,
        # Immutable snapshots never notify; serving subscriptions/listen would let any
        # anonymous POST hold an SSE stream and a request slot until the platform timeout.
        subscriptions=False,
    )

    @server.tool(
        name="get_profile",
        title="Get profile",
        description=(
            "Return the core profile: identity, headline, job title, contact, socials, biography, and areas of expertise."
        ),
        annotations=_READ_ONLY,
        structured_output=True,
    )
    def get_profile() -> ProfileResult:
        return ProfileResult(
            metadata=METADATA,
            biography=BIOGRAPHY,
            leadership=LEADERSHIP,
            expertise=EXPERTISE,
        )

    @server.tool(
        name="list_experience",
        title="List work experience",
        description="List professional work experience: companies, roles, descriptions, and skill tags.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    def list_experience() -> ExperienceResult:
        return ExperienceResult(experience=EXPERIENCES)

    @server.tool(
        name="list_certifications",
        title="List credentials",
        description="List professional certifications, badges, and course specializations with their issuers.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    def list_certifications() -> CertificationsResult:
        return CertificationsResult(certifications=BADGES, specializations=SPECIALIZATIONS)

    @server.tool(
        name="list_publications",
        title="List publications",
        description="List academic and written publications: the PhD thesis, peer-reviewed papers, and hosted articles.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    def list_publications() -> PublicationsResult:
        return PublicationsResult(thesis=THESIS, papers=PAPERS, articles=articles)

    @server.tool(
        name="search_articles",
        title="Search articles",
        description=(
            "Search the hosted articles by relevance (BM25 over titles, tags, descriptions, and full text) and return "
            "the best matches. Use it to answer what Fmind has written about a topic instead of listing every publication."
        ),
        annotations=_READ_ONLY,
        structured_output=True,
    )
    def search_articles(
        query: Annotated[
            str,
            Field(
                max_length=SEARCH_QUERY_LIMIT,
                description=f"words to search for across article titles, tags, descriptions, and full text (at most {SEARCH_QUERY_LIMIT} characters)",
            ),
        ],
        limit: Annotated[
            int,
            # strict: JSON true, "3", and 2.0 are not integers and must not be coerced.
            Field(
                strict=True,
                ge=1,
                le=MAXIMUM_SEARCH_RESULTS,
                description=f"maximum number of results to return (default {DEFAULT_SEARCH_RESULTS}, maximum {MAXIMUM_SEARCH_RESULTS})",
            ),
        ] = DEFAULT_SEARCH_RESULTS,
        tag: Annotated[
            str | None,
            Field(
                max_length=TAG_LIMIT,
                description=f"optionally keep only articles with this tag, case-insensitive: {', '.join(tag_names())}",
            ),
        ] = None,
    ) -> SearchArticlesResult:
        normalized = normalize_search_query(query)
        if not normalized:
            raise ToolError("query must not be empty")
        wanted = None
        if tag is not None:
            wanted = next((name for name in tag_names() if name.casefold() == tag.strip().casefold()), None)
            if wanted is None:
                raise ToolError(f"unknown tag {tag!r}; use one of: {', '.join(tag_names())}")
        ranked = tuple(item for item in index.search(normalized) if wanted is None or wanted in item.tags)
        return SearchArticlesResult(
            query=normalized,
            articles=tuple(item.summary() for item in ranked[:limit]),
            total=len(ranked),
        )

    @server.tool(
        name="list_projects",
        title="List projects",
        description="List open-source projects and educational YouTube series.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    def list_projects() -> ProjectsResult:
        return ProjectsResult(open_source=OPEN_SOURCE, youtube_series=YOUTUBE_SERIES)

    @server.tool(
        name="get_services",
        title="Get professional services",
        description="List the professional services on offer (AI architecture advisory and mentoring) with availability and how to book.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    def services() -> ServicesResult:
        return ServicesResult(services=SERVICES)

    @server.tool(
        name="get_article",
        title="Read an article",
        description="Read a public article's complete Markdown, dates, canonical URL, and hosted section links. Use a slug from search_articles; unknown and draft articles are unavailable.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    def get_article(
        slug: Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")],
    ) -> ArticleResult:
        result = article_results.get(slug)
        if result is None:
            raise ToolError("Article not found. Use search_articles to find a public article slug.")
        return result

    @server.tool(
        name="search_news",
        title="Search news",
        description=(
            "Search or list the daily curated tech news editions (titles, domains, URLs, descriptions, and dates). "
            "Omit query to list the latest editions, or pass a query to return matching editions and links."
        ),
        annotations=_READ_ONLY,
        structured_output=True,
    )
    def search_news(
        query: Annotated[
            str | None,
            Field(
                max_length=SEARCH_QUERY_LIMIT,
                description=(
                    "optional words or YYYY-MM-DD date to search for across news titles, domains, descriptions, "
                    f"and edition dates (at most {SEARCH_QUERY_LIMIT} characters); omit for the latest editions"
                ),
            ),
        ] = None,
        limit: Annotated[
            int,
            Field(
                strict=True,
                ge=1,
                le=MAXIMUM_SEARCH_RESULTS,
                description=f"maximum number of editions to return (default {DEFAULT_SEARCH_RESULTS}, maximum {MAXIMUM_SEARCH_RESULTS})",
            ),
        ] = DEFAULT_SEARCH_RESULTS,
    ) -> SearchNewsResult:
        if query is None:
            return SearchNewsResult(
                query="",
                editions=news_summaries[:limit],
                total=len(news_summaries),
            )
        normalized = normalize_search_query(query)
        if not normalized:
            raise ToolError("query must not be empty")
        ranked = search_news_editions(news, normalized)
        return SearchNewsResult(
            query=normalized,
            editions=ranked[:limit],
            total=len(ranked),
        )

    @server.tool(
        name="get_news",
        title="Read a news edition",
        description=(
            "Read a published daily news edition's complete Markdown, curated links, dates, and canonical URL. "
            "Use an edition slug (YYYY-MM-DD or YYYY-MM-DD-topic) from search_news."
        ),
        annotations=_READ_ONLY,
        structured_output=True,
    )
    def get_news(
        slug: Annotated[
            str,
            Field(
                min_length=10,
                max_length=200,
                pattern=r"^\d{4}-\d{2}-\d{2}(?:-[a-z0-9]+(?:-[a-z0-9]+)*)?$",
            ),
        ],
    ) -> NewsResult:
        result = news_results.get(slug)
        if result is None:
            raise ToolError("News edition not found. Use search_news to find a published edition slug.")
        return result

    @server.tool(
        name="compare_llm_hosting",
        title="Compare LLM hosting costs",
        description="Compare a GKE infrastructure budget with managed APIs. Call with parameters={} for defaults and supported models, hardware, and plans. Simple mode accepts preset, model, billing, requests (calls/day), and window (auto, 24, 8, or 1 hour/day); set mode=simple when overriding requests. It sizes replicas under illustrative throughput assumptions. Interactive presets run 24/7; job and pipeline presets schedule running hours inside active windows. Commitments bill idle hours. Advanced mode keeps the fleet fixed and exposes custom token budgets, throughput, and running time. Break-even holds that fleet fixed and checks its capacity. Totals include compute and GKE; operations and additional services are excluded. Returns assumptions, USD costs, GPU/TPU accelerator comparisons, constraints, sources, and a shareable URL. Invalid inputs fail; no resources are provisioned. See /agents#calculator.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    def compare_llm_hosting(
        parameters: Annotated[
            dict[Annotated[str, Field(max_length=64)], Annotated[str, Field(strict=True, max_length=128)]],
            Field(
                max_length=64,
                description="Calculator URL parameters as strings; use an empty object for defaults and available choices.",
            ),
        ],
    ) -> HostingResult:
        try:
            return compare_hosting(parameters)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(
        name="compare_mcp_context_cost",
        title="Compare MCP context costs",
        description="Count the tool-definition tokens that measured MCP servers (GitHub default toolset, Filesystem, Memory, Playwright) add to every model request, then price them as standard input for the managed APIs in the hosting snapshot. Omit servers for all four. Returns tokens per request and month, context share and USD per 1,000 requests and per 30-day month for each model, dated sources, limitations and a shareable page URL. Reference tokens, not provider billing. See /agents#mcp-context.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    def compare_mcp_context_cost(
        servers: Annotated[
            list[ServerId] | None,
            Field(min_length=1, max_length=len(SERVER_IDS), description="Distinct server ids; omit for all."),
        ] = None,
        requests_per_day: Annotated[
            int,
            Field(
                strict=True,
                ge=1,
                le=MAX_REQUESTS,
                description="Model requests per day; count every call in agent loops.",
            ),
        ] = DEFAULT_REQUESTS,
    ) -> ContextResult:
        try:
            return compare_context(servers, requests_per_day)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    @server.prompt(
        name="assess_fit",
        title="Assess a role or project fit",
        description="Evaluate a role or project brief against Fmind's profile, experience, expertise, and services.",
    )
    def assess_fit(
        brief: Annotated[
            str,
            Field(
                max_length=BRIEF_LIMIT,
                description=(
                    "The responsibilities, outcomes, constraints, and required expertise to assess "
                    f"(at most {BRIEF_LIMIT:,} characters)."
                ),
            ),
        ],
    ) -> str:
        return (
            f"Assess this brief against Fmind's portfolio: {brief}\n\n"
            "Use get_profile, list_experience, list_certifications, and get_services. Distinguish direct evidence, "
            "transferable strengths, gaps, and concrete next steps."
        )

    @server.prompt(
        name="brief_me",
        title="Brief me about Fmind",
        description="Create an audience-specific introduction to Fmind from the complete portfolio.",
    )
    def brief_me(
        audience: Annotated[
            str,
            Field(
                max_length=AUDIENCE_LIMIT,
                description=(
                    "Who will read the briefing, such as an executive, engineering leader, or conference organizer "
                    f"(at most {AUDIENCE_LIMIT} characters)."
                ),
            ),
        ],
    ) -> str:
        return (
            f"Brief this audience about Fmind: {audience}. Use the portfolio resource and relevant tools. Lead with "
            "audience value, support claims with specific experience or publications, and keep the result concise."
        )

    @server.resource(
        MCP_PROFILE_URI,
        name="profile",
        title="Full portfolio",
        description=(
            "The complete portfolio (profile, leadership, experience, credentials, publications, projects, services) "
            "as a single JSON document."
        ),
        mime_type="application/json",
    )
    def profile_resource() -> str:
        return profile_json

    return server


async def render_mcp_server_card(server: MCPServer[None]) -> bytes:
    """Render discovery from the actual registered protocol primitives."""
    tools = await server.list_tools()
    prompts = await server.list_prompts()
    resources = await server.list_resources()
    card = {
        "version": "1.0",
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "serverInfo": {
            "name": "www",
            "title": _TITLE,
            "version": build_version(),
            "websiteUrl": _WEBSITE_URL,
        },
        "description": _DESCRIPTION,
        "iconUrl": _ICON_URL,
        "documentationUrl": f"{METADATA.site_url}/agents",
        "transport": {"type": "streamable-http", "endpoint": f"{METADATA.site_url}/mcp"},
        "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
        "instructions": (
            "Use the tools for focused queries, the portfolio resource for a complete snapshot, and prompts for "
            "guided assessments."
        ),
        "resources": [
            resource.model_dump(
                mode="json", by_alias=True, include={"uri", "name", "title", "description", "mime_type"}
            )
            for resource in resources
        ],
        "tools": [tool.model_dump(include={"name", "title", "description"}) for tool in tools],
        "prompts": [prompt.model_dump(include={"name", "title", "description"}) for prompt in prompts],
    }
    return (json.dumps(card, ensure_ascii=False, indent=2) + "\n").encode()


class _PostOnly:
    """Answer every MCP method but POST before the SDK transport sees it.

    The transport omits Allow on DELETE and answers other methods with
    Allow: GET, POST, DELETE, although stateless JSON mode serves neither GET
    nor DELETE.
    """

    def __init__(self, app: ASGIApp, validator: TransportSecurityMiddleware) -> None:
        self._app = app
        self._validator = validator

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["method"] == "POST":
            await self._app(scope, receive, send)
            return
        # Legacy Streamable HTTP explicitly permits 405 when no GET stream is
        # offered. An idle SDK stream otherwise reaches Cloud Run's timeout.
        response = await self._validator.validate_request(Request(scope, receive)) or Response(
            "MCP accepts POST only; notification streams and sessions are not supported.\n",
            status_code=405,
            headers={"Allow": "POST"},
            media_type="text/plain",
        )
        await response(scope, receive, send)


def create_mcp_http_app(server: MCPServer[None]) -> Starlette:
    """Serve finite MCP requests without opening unused notification streams."""
    # The public host plus loopback for local runs and the image smoke test. The apex
    # is absent on purpose: production redirects it to www before this app sees it.
    security = TransportSecuritySettings(
        allowed_hosts=[
            "www.fmind.dev",
            "www.fmind.dev:*",
            "localhost",
            "localhost:*",
            "127.0.0.1",
            "127.0.0.1:*",
        ],
        allowed_origins=[
            "https://www.fmind.dev",
            "http://localhost",
            "http://localhost:*",
            "http://127.0.0.1",
            "http://127.0.0.1:*",
        ],
    )
    app = server.streamable_http_app(
        # The site routes the exact public path here without rewriting it.
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        max_request_body_size=1 << 20,
        transport_security=security,
    )
    # The SDK route forwards every method to its transport, and Starlette
    # cannot route "every method but POST", so wrap that single route.
    (route,) = app.router.routes
    if not isinstance(route, Route):
        raise TypeError(f"Expected the MCP SDK to serve one Route, got {route!r}")
    guard = Middleware(_PostOnly, validator=TransportSecurityMiddleware(security))
    app.router.routes[0] = Route(route.path, route.endpoint, middleware=[guard])
    return app
