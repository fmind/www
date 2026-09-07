"""Read-only Model Context Protocol portfolio server and discovery card."""

from __future__ import annotations

import json
from importlib.metadata import version
from typing import Annotated, Any, cast, override

from mcp.server.caching import CACHEABLE_METHODS, CacheableMethod, CacheHint
from mcp.server.context import CallNext, HandlerResult, ServerMiddleware, ServerRequestContext
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import GetPromptResult, Icon, InputRequiredResult, Prompt, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from www.data import (
    BADGES,
    BIOGRAPHY,
    EXPERIENCES,
    EXPERTISE,
    LEADERSHIP,
    METADATA,
    OPEN_SOURCE,
    PAPERS,
    SPECIALIZATIONS,
    THESIS,
    YOUTUBE_SERIES,
    get_services,
)
from www.models import (
    ArticleSummary,
    CertificationBadge,
    CertificationEntry,
    ExpertiseCard,
    LeadershipRole,
    Metadata,
    Playlist,
    Portfolio,
    Project,
    ResearchPaper,
    Service,
    Thesis,
    WorkExperience,
)
from www.publications import portfolio_snapshot
from www.search import SearchIndex, normalize_search_query

MCP_PROTOCOL_VERSION = "2026-07-28"
MCP_PROFILE_URI = "portfolio://profile.json"
MCP_CACHE_TTL_MS = 3_600_000
DEFAULT_SEARCH_RESULTS = 10
MAXIMUM_SEARCH_RESULTS = 50

_ICON_URL = f"{METADATA.site_url}/static/img/favicons/icon-192.png"
_ICONS = [Icon(src=_ICON_URL, mime_type="image/png", sizes=["192x192"])]
_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
_CACHE_HINTS = {
    cast(CacheableMethod, method): CacheHint(ttl_ms=MCP_CACHE_TTL_MS, scope="public") for method in CACHEABLE_METHODS
}
_PORTFOLIO_ADAPTER = TypeAdapter(Portfolio)

_PROMPT_ARGUMENT_TITLES = {
    ("assess_fit", "brief"): "Role or project brief",
    ("brief_me", "audience"): "Audience",
}
_PROMPT_RESULT_DESCRIPTIONS = {
    "assess_fit": "A structured, evidence-based fit assessment using the portfolio tools.",
    "brief_me": "An audience-specific briefing grounded in the full portfolio.",
}


class _LegacyCapabilities(ServerMiddleware[Any]):
    """Retain the established handshake-era discovery shape."""

    async def __call__(
        self,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> HandlerResult:
        result = await call_next(ctx)
        if ctx.method != "initialize" or not isinstance(result, dict):
            return result
        # MCPServer 2.1 has no public default-notification-options seam for its
        # HTTP adapter. Middleware is the supported result boundary and keeps
        # existing clients' exact capability contract without private access.
        return {
            **result,
            "capabilities": {
                "prompts": {"listChanged": True},
                "resources": {"listChanged": True},
                "tools": {"listChanged": True},
            },
        }


class _PortfolioMCPServer(MCPServer[None]):
    """Preserve prompt metadata that MCPServer 2.1.1 does not derive."""

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
        result = await super().get_prompt(name, arguments, context)
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


def build_version() -> str:
    """Return the package version in the server implementation format."""
    return f"v{version('www')}"


def create_mcp_server(articles: tuple[ArticleSummary, ...], index: SearchIndex) -> MCPServer[None]:
    """Build the immutable portfolio MCP server."""
    server: MCPServer[None] = _PortfolioMCPServer(
        name="www",
        title="Médéric Hurier (Fmind) — AI Architect Portfolio",
        description="Read-only portfolio tools, resources, and prompts for Fmind.",
        instructions=(
            f"Query the portfolio of {METADATA.name} ({METADATA.alternate_name}): {METADATA.headline_primary}. "
            "Explore profile, leadership, work experience, credentials, publications, projects, and services."
        ),
        website_url=f"{METADATA.site_url}/",
        icons=_ICONS,
        version=build_version(),
        cache_hints=_CACHE_HINTS,
        middleware=[_LegacyCapabilities()],
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
            Field(description="words to search for across article titles, tags, descriptions, and full text"),
        ],
        limit: Annotated[
            int,
            Field(description="maximum number of results to return (default 10, maximum 50)"),
        ] = 0,
    ) -> SearchArticlesResult:
        normalized = normalize_search_query(query)
        if not normalized:
            raise ToolError("query must not be empty")
        count = DEFAULT_SEARCH_RESULTS if limit <= 0 else min(limit, MAXIMUM_SEARCH_RESULTS)
        ranked = index.search(normalized)
        return SearchArticlesResult(
            query=normalized,
            articles=tuple(item.summary() for item in ranked[:count]),
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
        return ServicesResult(services=get_services())

    @server.prompt(
        name="assess_fit",
        title="Assess a role or project fit",
        description="Evaluate a role or project brief against Fmind's profile, experience, expertise, and services.",
    )
    def assess_fit(
        brief: Annotated[
            str,
            Field(description="The responsibilities, outcomes, constraints, and required expertise to assess."),
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
                description=(
                    "Who will read the briefing, such as an executive, engineering leader, or conference organizer."
                )
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
        return json.dumps(serialize_portfolio(articles), ensure_ascii=False, separators=(",", ":"))

    return server


def serialize_portfolio(articles: tuple[ArticleSummary, ...]) -> dict[str, Any]:
    """Serialize the portfolio once for both JSON and MCP delivery surfaces."""
    encoded = _PORTFOLIO_ADAPTER.dump_python(portfolio_snapshot(articles), mode="json")
    if not isinstance(encoded, dict):  # pragma: no cover - fixed TypeAdapter root
        msg = "portfolio serialization must produce an object"
        raise TypeError(msg)
    return encoded


def render_profile_json(articles: tuple[ArticleSummary, ...]) -> bytes:
    """Render the canonical, human-readable profile document with a final newline."""
    return (json.dumps(serialize_portfolio(articles), ensure_ascii=False, indent=2) + "\n").encode()


async def render_mcp_server_card(server: MCPServer[None]) -> bytes:
    """Render discovery from the actual registered protocol primitives."""
    tools = await server.list_tools()
    prompts = await server.list_prompts()
    resources = await server.list_resources()
    card = {
        "$schema": "https://static.modelcontextprotocol.io/schemas/mcp-server-card/v1.json",
        "version": "1.0",
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "serverInfo": {
            "name": "www",
            "title": "Médéric Hurier (Fmind) — AI Architect Portfolio",
            "version": build_version(),
            "websiteUrl": f"{METADATA.site_url}/",
        },
        "description": "Read-only portfolio tools, resources, and prompts for Fmind.",
        "iconUrl": _ICON_URL,
        "documentationUrl": f"{METADATA.site_url}/llms.txt",
        "transport": {"type": "streamable-http", "endpoint": f"{METADATA.site_url}/mcp"},
        "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
        "instructions": (
            "Use the tools for focused queries, the portfolio resource for a complete snapshot, and prompts for "
            "guided assessments."
        ),
        "resources": [resource.model_dump(include={"name", "title", "description"}) for resource in resources],
        "tools": [tool.model_dump(include={"name", "title", "description"}) for tool in tools],
        "prompts": [prompt.model_dump(include={"name", "title", "description"}) for prompt in prompts],
    }
    return (json.dumps(card, ensure_ascii=False, indent=2) + "\n").encode()
