"""MCP context arithmetic, boundary validation and shared HTTP/MCP discovery."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from litestar.testing import TestClient
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult

from www.app import create_app
from www.content import article_summaries, load_articles, visible_articles
from www.data import SITE_PAGES
from www.mcp import create_mcp_server
from www.publications import article_markdown_index
from www.search import SearchIndex
from www.sites.data import API_BASELINES
from www.sites.mcp_context_cost.calculator import (
    PATH,
    SERVER_IDS,
    build_context_view,
    compare_context,
    parse_query,
    view_from_query,
)
from www.sites.mcp_context_cost.data import SERVERS

REPO_ROOT = Path(__file__).resolve().parents[1]
BEFORE_REVIEW = datetime(2026, 10, 14, tzinfo=UTC)


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app=create_app()) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def server():
    articles = visible_articles(load_articles().all)
    return create_mcp_server(
        article_summaries(articles), SearchIndex(articles), articles, article_markdown_index(articles)
    )


def test_measured_catalogs_match_the_retained_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    snapshot = json.loads((REPO_ROOT / "src/www/sites/mcp_context_cost/measurements.json").read_text())
    lock = REPO_ROOT / "scripts/mcp_context_cost/measurement-package-lock.json"
    assert sha256(lock.read_bytes()).hexdigest() == snapshot["package_lock_sha256"]
    github, *others = SERVERS
    assert (github.tools, github.tokens) == (snapshot["github"]["tools"], snapshot["github"]["input_schema_tokens"])
    assert [(item.id, item.tools, item.tokens) for item in others] == [
        (item["id"], item["tool_count"], item["input_schema_tokens"]) for item in snapshot["servers"]
    ]
    # The typed MCP argument advertises exactly the measured catalogs.
    assert tuple(server.id for server in SERVERS) == SERVER_IDS
    view = build_context_view(now=BEFORE_REVIEW)
    assert (view.tools, view.tokens_request, view.requests_per_day) == (93, 17368, 1000)


def test_hand_calculated_tokens_context_and_costs_for_selected_servers() -> None:
    view = build_context_view(("memory", "filesystem"), 200, now=BEFORE_REVIEW)
    assert [share.server.id for share in view.selected] == ["filesystem", "memory"]  # Largest first.
    assert view.selected[0].percent == pytest.approx(100 * 1681 / 2634)
    assert (view.tools, view.tokens_request, view.tokens_month) == (23, 2634, 2634 * 200 * 30)
    # Cheapest first; every row uses the hosting snapshot's standard input rate.
    assert [model.name for model in view.models] == [
        baseline.name for baseline in sorted(API_BASELINES, key=lambda row: row.input_per_million)
    ]
    haiku = view.models[0]
    assert haiku.name == "Claude Haiku 5.5"
    assert haiku.context_percent == pytest.approx(0.2634)
    assert haiku.per_thousand_requests_usd == pytest.approx(0.2634)
    assert haiku.month_usd == pytest.approx(1.5804)
    assert not any(model.needs_review for model in view.models)


def test_prices_follow_the_shared_snapshot_validity_and_review_dates() -> None:
    later = build_context_view(("memory",), 1, now=datetime(2027, 1, 2, tzinfo=UTC))
    gemini = next(model for model in later.models if model.name == "Gemini 3.8 Flash")
    # The announced January 2027 rate doubles; every dated price now needs review.
    assert gemini.input_per_million == 1.5
    assert gemini.month_usd == pytest.approx(953 * 30 * 1.5 / 1e6)
    assert all(model.needs_review for model in later.models)


def test_default_page_query_selects_every_server_and_ignores_tracking_keys() -> None:
    for query in ({}, {"utm_source": "newsletter"}, {"unknown": ["a", "b"]}):
        assert parse_query(query) == (SERVER_IDS, 1000, ())


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ({"requests": "5"}, "Select at least one MCP server"),
        ({"server": ["github", "unknown"]}, "Unknown MCP servers were ignored"),
        ({"server": "unknown", "requests": "5"}, "Unknown MCP servers were ignored; all servers were used"),
        ({"server": "github", "requests": "0"}, "Requests per day must be a whole number"),
        ({"server": "github", "requests": "1.5"}, "Requests per day must be a whole number"),
        ({"server": "github", "requests": "NaN"}, "Requests per day must be a whole number"),
        ({"server": "github", "requests": ""}, "Requests per day must be a whole number"),
        ({"server": "github", "requests": " 2"}, "Requests per day must be a whole number"),
        ({"server": "github", "requests": "٢"}, "Requests per day must be a whole number"),
        ({"server": "github", "requests": "10000001"}, "Requests per day must be a whole number"),
        ({"server": "github", "requests": "9" * 129}, "Requests per day must be a whole number"),
        ({"server": "github", "requests": ["2", "3"]}, "Requests per day must be a whole number"),
    ],
)
def test_invalid_page_inputs_show_messages_and_fall_back(query: dict[str, str | list[str]], message: str) -> None:
    servers, requests, errors = parse_query(query)
    assert any(error.startswith(message) for error in errors)
    assert servers
    if "requests" in query and message.startswith("Requests"):
        assert (servers, requests) == (("github",), 1000)


def test_shareable_url_round_trips_and_mcp_matches_the_page() -> None:
    view = build_context_view(("playwright", "github"), 4321)
    query = parse_qs(urlsplit(view.scenario_url).query)
    assert query == {"server": ["github", "playwright"], "requests": ["4321"]}
    restored = view_from_query(query)
    assert (restored.selected, restored.requests_per_day, restored.validation) == (view.selected, 4321, ())
    result = compare_context(["github", "playwright"], 4321)
    assert result.scenario_url == view.scenario_url
    assert result.tokens_per_request == 10989 + 3745
    assert result.tokens_per_month == (10989 + 3745) * 4321 * 30
    assert result.models == view.models


@pytest.mark.parametrize(
    ("servers", "requests"),
    [([], 1), (["github", "github"], 1), (["unknown"], 1), (None, 0), (None, 10_000_001)],
)
def test_mcp_adapter_fails_closed(servers: list[str] | None, requests: int) -> None:
    with pytest.raises(ValueError, match=r"^(servers|requests_per_day) must"):
        compare_context(servers, requests)


def test_page_metadata_validation_redirects_and_404(client: TestClient) -> None:
    response = client.get(PATH)
    assert response.status_code == 200
    assert "How much context do your MCP tools take?" in response.text
    assert "17,368 tokens of tool definitions on every request" in response.text
    assert f'<link rel="canonical" href="https://www.fmind.dev{PATH}"' in response.text
    assert '"@type":"WebApplication"' in response.text
    assert '<form id="calculator" method="get"' in response.text
    assert response.text.count('name="server"') == len(SERVERS)
    assert response.text.count(" checked/>") == len(SERVERS)
    # Every section stays open: no disclosure widgets.
    assert "<details" not in response.text
    assert client.head(PATH).status_code == 200
    assert not client.head(PATH).content
    redirect = client.get(PATH.rstrip("/") + "?requests=3", follow_redirects=False)
    assert redirect.headers["location"] == PATH + "?requests=3"
    for path in ("/sites/unknown/", PATH + "missing/"):
        assert client.get(path).status_code == 404
    invalid = client.get(PATH + "?requests=NaN&requests=2")
    assert invalid.status_code == 200
    assert "Some inputs need attention" in invalid.text
    assert "between 1 and 10,000,000" in invalid.text
    one = client.get(PATH + "?server=memory&requests=10")
    assert "953 tokens of tool definitions on every request" in one.text
    assert one.text.count(" checked/>") == 1
    assert one.text.count(">Package release</a>") == 3
    assert one.text.count(">Pinned measurement source</a>") == 1


@pytest.mark.parametrize(
    "slug", ["agents-md-speaks-unix", "mcp-2026-07-28-stateless-core-enterprise-authorization-and-sdk-betas"]
)
def test_existing_articles_do_not_gain_a_related_calculator_box(client: TestClient, slug: str) -> None:
    response = client.get(f"/articles/{slug}/")
    assert response.status_code == 200
    assert "Put the ideas into practice" not in response.text
    assert f'href="{PATH}"' not in response.text


def test_registry_discovery_and_packaged_agent_skill_include_both_sites(client: TestClient) -> None:
    for page in SITE_PAGES:
        for path in ("/sitemap.xml", "/llms.txt", "/llms-full.txt"):
            assert page.url in client.get(path).text
        assert urlsplit(page.url).path in client.get("/sites/").text
    profile = client.get("/api/profile").json()
    assert {row["slug"] for row in profile["site_pages"]} == {"llm-self-hosting", "mcp-context-cost"}
    card = client.get("/.well-known/mcp/server-card.json").json()
    assert "compare_mcp_context_cost" in {tool["name"] for tool in card["tools"]}
    assert "compare_mcp_context_cost" in client.get("/agents").text
    assert "compare_mcp_context_cost" in client.get("/.well-known/agent-skills/fmind-research/SKILL.md").text


@pytest.mark.anyio
async def test_mcp_result_matches_http_scenario_and_invalid_calls_fail(server, client: TestClient) -> None:
    arguments = {"servers": ["memory", "filesystem"], "requests_per_day": 200}
    result = await server.call_tool("compare_mcp_context_cost", arguments)
    assert isinstance(result, CallToolResult)
    expected = compare_context(["memory", "filesystem"], 200)
    assert result.structured_content == json.loads(expected.model_dump_json())
    assert result.structured_content is not None
    response = client.get(result.structured_content["scenario_url"])
    assert response.status_code == 200
    assert "2,634 tokens of tool definitions on every request" in response.text
    defaults = await server.call_tool("compare_mcp_context_cost", {})
    assert isinstance(defaults, CallToolResult)
    assert defaults.structured_content is not None
    assert defaults.structured_content["tokens_per_request"] == 17368
    for invalid in (
        {"servers": []},
        {"servers": ["unknown"]},
        {"servers": ["github", "github"]},
        {"servers": "github"},
        {"requests_per_day": 0},
        {"requests_per_day": 1.5},
        {"requests_per_day": True},
        {"requests_per_day": "1000"},
    ):
        with pytest.raises(ToolError):
            await server.call_tool("compare_mcp_context_cost", invalid)
