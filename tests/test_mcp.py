"""Read-only MCP portfolio contract tests."""

from __future__ import annotations

import json

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, InputRequiredResult, TextContent

from www.content import article_summaries, load_articles, visible_articles
from www.mcp import create_mcp_server, render_mcp_server_card, render_profile_json
from www.search import SearchIndex


@pytest.fixture(scope="module")
def mcp_server() -> MCPServer[None]:
    articles = visible_articles(load_articles().all)
    return create_mcp_server(article_summaries(articles), SearchIndex(articles))


@pytest.mark.anyio
async def test_server_lists_seven_read_only_tools_and_two_prompts(mcp_server: MCPServer[None]) -> None:
    tools = await mcp_server.list_tools()
    prompts = await mcp_server.list_prompts()

    assert [tool.name for tool in tools] == [
        "get_profile",
        "list_experience",
        "list_certifications",
        "list_publications",
        "search_articles",
        "list_projects",
        "get_services",
    ]
    assert all(tool.annotations and tool.annotations.read_only_hint is True for tool in tools)
    assert all(tool.annotations and tool.annotations.open_world_hint is False for tool in tools)
    assert all(tool.output_schema and tool.output_schema["type"] == "object" for tool in tools)
    required_article_fields = {
        "date",
        "updated",
        "title",
        "description",
        "slug",
        "url",
        "image_url",
        "image_alt",
        "tags",
        "reading_minutes",
    }
    for name in ("list_publications", "search_articles"):
        article_tool = next(tool for tool in tools if tool.name == name)
        assert article_tool.output_schema is not None
        article_schema = article_tool.output_schema["$defs"]["ArticleSummary"]
        assert set(article_schema["required"]) == required_article_fields
        assert set(article_schema["properties"]) - required_article_fields == {"canonical", "syndicated"}
    search_tool = next(tool for tool in tools if tool.name == "search_articles")
    assert search_tool.input_schema["properties"]["query"]["description"] == (
        "words to search for across article titles, tags, descriptions, and full text"
    )
    assert search_tool.input_schema["properties"]["limit"]["description"] == (
        "maximum number of results to return (default 10, maximum 50)"
    )
    assert [prompt.name for prompt in prompts] == ["assess_fit", "brief_me"]
    assert [
        [argument.model_dump(by_alias=True, exclude_none=True) for argument in prompt.arguments or []]
        for prompt in prompts
    ] == [
        [
            {
                "name": "brief",
                "title": "Role or project brief",
                "description": "The responsibilities, outcomes, constraints, and required expertise to assess.",
                "required": True,
            }
        ],
        [
            {
                "name": "audience",
                "title": "Audience",
                "description": (
                    "Who will read the briefing, such as an executive, engineering leader, or conference organizer."
                ),
                "required": True,
            }
        ],
    ]
    assert all(prompt.arguments and prompt.arguments[0].required for prompt in prompts)
    assert mcp_server.website_url == "https://www.fmind.dev/"
    assert mcp_server.icons
    assert mcp_server.icons[0].src == "https://www.fmind.dev/static/img/favicons/icon-192.png"
    assert mcp_server.icons[0].mime_type == "image/png"
    assert mcp_server.icons[0].sizes == ["192x192"]


@pytest.mark.anyio
async def test_read_only_tools_return_their_structured_portfolio_slices(mcp_server: MCPServer[None]) -> None:
    expected_keys = {
        "get_profile": {"metadata", "biography", "leadership", "expertise"},
        "list_experience": {"experience"},
        "list_certifications": {"certifications", "specializations"},
        "list_publications": {"thesis", "papers", "articles"},
        "list_projects": {"open_source", "youtube_series"},
        "get_services": {"services"},
    }

    for name, keys in expected_keys.items():
        result = await mcp_server.call_tool(name, {})
        assert isinstance(result, CallToolResult)
        assert isinstance(result.structured_content, dict)
        assert result.structured_content.keys() == keys

    profile = await mcp_server.call_tool("get_profile", {})
    assert isinstance(profile, CallToolResult)
    assert isinstance(profile.structured_content, dict)
    assert profile.structured_content["metadata"]["alternate_name"] == "Fmind"

    publications = await mcp_server.call_tool("list_publications", {})
    projects = await mcp_server.call_tool("list_projects", {})
    assert isinstance(publications, CallToolResult)
    assert isinstance(publications.structured_content, dict)
    assert "canonical" not in publications.structured_content["articles"][0]
    assert "syndicated" not in publications.structured_content["articles"][0]
    assert isinstance(projects, CallToolResult)
    assert isinstance(projects.structured_content, dict)
    assert "repo" not in projects.structured_content["open_source"][0]


@pytest.mark.anyio
async def test_search_tool_normalizes_caps_and_rejects_empty_query(mcp_server: MCPServer[None]) -> None:
    result = await mcp_server.call_tool("search_articles", {"query": "  kubeflow  ", "limit": 3})

    assert isinstance(result, CallToolResult)
    assert isinstance(result.structured_content, dict)
    assert result.structured_content["query"] == "kubeflow"
    assert len(result.structured_content["articles"]) <= 3
    assert result.structured_content["total"] >= 1

    default = await mcp_server.call_tool("search_articles", {"query": "the"})
    capped = await mcp_server.call_tool("search_articles", {"query": "the", "limit": 100})
    assert isinstance(default, CallToolResult)
    assert isinstance(default.structured_content, dict)
    assert len(default.structured_content["articles"]) == 10
    assert isinstance(capped, CallToolResult)
    assert isinstance(capped.structured_content, dict)
    assert len(capped.structured_content["articles"]) == 50

    with pytest.raises(ToolError, match="query must not be empty"):
        await mcp_server.call_tool("search_articles", {"query": "  "})


@pytest.mark.anyio
async def test_profile_resource_and_prompt_are_grounded(mcp_server: MCPServer[None]) -> None:
    resources = await mcp_server.list_resources()
    contents = await mcp_server.read_resource("portfolio://profile.json")
    prompt = await mcp_server.get_prompt(
        "assess_fit",
        {"brief": "Secure an enterprise agent platform"},
    )
    briefing = await mcp_server.get_prompt("brief_me", {"audience": "engineering leaders"})

    assert len(resources) == 1
    assert resources[0].name == "profile"
    assert str(resources[0].uri) == "portfolio://profile.json"
    assert resources[0].mime_type == "application/json"
    assert not isinstance(contents, InputRequiredResult)
    portfolio = json.loads(next(iter(contents)).content)
    assert portfolio["metadata"]["alternate_name"] == "Fmind"
    assert len(portfolio["articles"]) == 59
    assert not isinstance(prompt, InputRequiredResult)
    assert prompt.description == "A structured, evidence-based fit assessment using the portfolio tools."
    prompt_content = prompt.messages[0].content
    assert isinstance(prompt_content, TextContent)
    assert "Secure an enterprise agent platform" in prompt_content.text
    assert "list_experience" in prompt_content.text
    assert not isinstance(briefing, InputRequiredResult)
    assert briefing.description == "An audience-specific briefing grounded in the full portfolio."
    briefing_content = briefing.messages[0].content
    assert isinstance(briefing_content, TextContent)
    assert "engineering leaders" in briefing_content.text
    assert "portfolio resource" in briefing_content.text


def test_server_card_describes_the_same_transport_and_primitives() -> None:
    card = json.loads(render_mcp_server_card())

    assert card["protocolVersion"] == "2026-07-28"
    assert card["transport"] == {
        "type": "streamable-http",
        "endpoint": "https://www.fmind.dev/mcp",
    }
    assert len(card["tools"]) == 7
    assert len(card["prompts"]) == 2
    assert card["resources"][0]["name"] == "profile"


def test_profile_json_omits_private_and_zero_value_fields() -> None:
    articles = article_summaries(visible_articles(load_articles().all))
    profile = json.loads(render_profile_json(articles))

    assert render_profile_json(articles).endswith(b"\n")
    assert "article_slugs" not in profile["site_pages"][0]
    assert "canonical" not in profile["articles"][0]
    assert "syndicated" not in profile["articles"][0]
    assert "repo" not in profile["open_source"][0]
    assert profile["articles"][0]["date"].endswith("Z")
