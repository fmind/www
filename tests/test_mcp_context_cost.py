"""MCP context arithmetic, boundary validation and shared HTTP/MCP discovery."""

from __future__ import annotations

import json
from collections.abc import Iterator
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
from www.sites.mcp_context_cost.calculator import (
    FIELDS,
    PATH,
    build_context_view,
    compare_context,
    parse_inputs,
    scenario_url,
)
from www.sites.mcp_context_cost.data import MODELS, SERVERS


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


def test_measured_catalogs_match_the_retained_snapshot() -> None:
    snapshot = json.loads(Path("src/www/sites/mcp_context_cost/measurements.json").read_text())
    github, *others = SERVERS
    assert (github.tools, github.tokens) == (snapshot["github"]["tools"], snapshot["github"]["input_schema_tokens"])
    assert [(item.id, item.tools, item.tokens) for item in others] == [
        (item["id"], item["tool_count"], item["input_schema_tokens"]) for item in snapshot["servers"]
    ]
    rows = build_context_view({}).strategies
    assert rows[0].tokens_request == rows[1].tokens_request == 17368


def test_hand_calculated_filtering_and_discovery_exclude_disabled_servers() -> None:
    view = build_context_view(
        {
            "github": "0",
            "filesystem": "0",
            "playwright": "0",
            "memory": "3",
            "loaded": "50",
            "discovery-tokens": "100",
            "context": "10000",
        }
    )
    baseline, filtered, search, _ = view.strategies
    assert baseline.tokens_request == 953
    assert filtered.tokens_request == 318  # ceil(953 * 3/9)
    assert search.tokens_request == 259  # 100 + 318 * 0.5
    assert filtered.context_percent == pytest.approx(3.18)
    assert filtered.saved_month_usd == pytest.approx((953 - 318) * 20 * 10 * 22 * 0.75 / 1e6)


def test_hand_calculated_cache_hits_cold_start_write_premium_and_monthly_cost() -> None:
    view = build_context_view(
        {
            "requests": "5",
            "sessions": "3",
            "days": "20",
            "input-price": "2",
            "cache-price": "0.5",
            "write-multiplier": "1.25",
            "cache-hits": "50",
            "cache-minimum": "1000",
            "skill-tokens": "300",
            "help-tokens": "700",
            "mitigation": "cli",
        }
    )
    row = view.selected
    # 1,000 tokens; 2 hits and 3 cold/write requests, including first request.
    assert row.session_usd == pytest.approx(0.01)
    assert row.request_usd == pytest.approx(0.002)
    assert row.cached_average_request_usd == pytest.approx(0.0017)
    assert row.cached_session_usd == pytest.approx(0.0085)
    assert row.day_usd == pytest.approx(0.03)
    assert row.cached_day_usd == pytest.approx(0.0255)
    assert row.month_usd == pytest.approx(0.6)
    assert row.cached_month_usd == pytest.approx(0.51)
    assert row.cached_saved_month_usd == pytest.approx(view.strategies[0].cached_month_usd - 0.51)


def test_cache_eligibility_uses_other_prefix_without_billing_it() -> None:
    query = {"mitigation": "cli", "cache-minimum": "1024", "cache-hits": "100"}
    below = build_context_view(query).selected
    eligible = build_context_view({**query, "other-prefix": "24"}).selected
    assert not below.cache_eligible
    assert below.cached_session_usd == below.session_usd
    assert eligible.cache_eligible
    assert eligible.context_percent == below.context_percent
    assert eligible.session_usd == below.session_usd
    assert eligible.cached_session_usd == pytest.approx((0.75 + 19 * 0.075) * 1000 / 1e6)


def test_single_request_has_no_cache_hit_and_premium_can_cost_more() -> None:
    row = build_context_view({"requests": "1", "cache-hits": "100", "write-multiplier": "1.25"}).selected
    assert row.cached_session_usd == row.session_usd * 1.25
    unchanged = build_context_view({"cache-hits": "0"}).selected
    assert unchanged.cached_month_usd == unchanged.month_usd


def test_empty_catalog_and_excess_context_are_not_presented_as_savings_or_fit() -> None:
    view = build_context_view(
        {**dict.fromkeys((server.id for server in SERVERS), "0"), "context": "500", "mitigation": "cli"}
    )
    baseline, filtered, search, cli = view.strategies
    assert baseline.month_usd == filtered.month_usd == 0
    assert search.saved_month_usd < 0
    assert cli.saved_month_usd < 0
    assert cli.context_percent == 200
    assert not cli.fits
    assert build_context_view({"context": "1000", "mitigation": "cli"}).selected.fits


@pytest.mark.parametrize(
    "query",
    [
        {"context": "NaN"},
        {"input-price": "Infinity"},
        {"cache-price": "-1"},
        {"requests": "1.5"},
        {"requests": "1e2"},
        {"sessions": "0"},
        {"days": "32"},
        {"cache-hits": "101"},
        {"loaded": "-1"},
        {"write-multiplier": "0.5"},
        {"github": "46"},
        {"memory": "-1"},
        {"model": "unknown"},
        {"mitigation": "unknown"},
        {"unknown": "1"},
        {"requests": ""},
        {"requests": " 2"},
        {"requests": "٢"},
        {"input-price": "1_000"},
        {"input-price": "1e999"},
        {"context": "9" * 129},
    ],
)
def test_invalid_parameters_show_page_messages_and_fail_mcp_adapter(query: dict[str, str]) -> None:
    view = build_context_view(query)
    assert view.validation
    with pytest.raises(ValueError, match="Invalid calculator parameters"):
        compare_context(query)


def test_duplicate_values_are_rejected_and_single_value_sequences_are_supported() -> None:
    inputs, errors = parse_inputs({"requests": ["2", "3"]})
    assert inputs.values["requests"] == 20
    assert errors == ("requests must occur once; the default was used",)
    assert parse_inputs({"requests": ["2"]})[0].values["requests"] == 2
    assert parse_inputs({"requests": []})[1]


def test_shareable_url_round_trip_preserves_float_precision_and_bounds() -> None:
    query = {field.key: str(int(field.maximum)) if field.whole else str(field.maximum) for field in FIELDS}
    query["input-price"] = "0.12345678901234567"
    view = build_context_view(query)
    restored, errors = parse_inputs(parse_qs(urlsplit(scenario_url(view.inputs)).query))
    assert not errors
    assert restored == view.inputs
    assert compare_context(view.parameters).strategies == view.strategies


def test_model_defaults_overrides_and_preset_links_preserve_workload() -> None:
    view = build_context_view({"model": "gpt-4.1", "input-price": "7", "requests": "3", "github": "4"})
    assert view.inputs.values["context"] == 1047576
    assert view.inputs.values["input-price"] == 7
    for (_, url), model in zip(view.model_urls, MODELS, strict=True):
        chosen = build_context_view(parse_qs(urlsplit(url).query))
        assert not chosen.validation
        assert chosen.inputs.values["input-price"] == model.input_price
        assert chosen.inputs.values["context"] == model.context_tokens
        assert chosen.inputs.values["requests"] == 3
        assert chosen.inputs.enabled[0] == 4


def test_page_metadata_validation_redirects_and_404(client: TestClient) -> None:
    response = client.get(PATH)
    assert response.status_code == 200
    assert "What do your MCP tools cost in context?" in response.text
    assert f'<link rel="canonical" href="https://www.fmind.dev{PATH}"' in response.text
    assert '"@type":"WebApplication"' in response.text
    assert '<form id="calculator" method="get"' in response.text
    assert client.head(PATH).status_code == 200
    assert not client.head(PATH).content
    redirect = client.get(PATH.rstrip("/") + "?requests=3", follow_redirects=False)
    assert redirect.headers["location"] == PATH + "?requests=3"
    for path in ("/sites/unknown/", PATH + "missing/"):
        assert client.get(path).status_code == 404
    invalid = client.get(PATH + "?requests=NaN&requests=2&context=0&mitigation=cli")
    assert invalid.status_code == 200
    assert "must occur once" in invalid.text
    assert "Some inputs need attention" in invalid.text
    overflow = client.get(PATH + "?context=100&mitigation=cli")
    assert "This tool block alone exceeds the context window" in overflow.text


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
    query = {"requests": "3", "github": "5", "mitigation": "filter"}
    result = await server.call_tool("compare_mcp_context_cost", {"parameters": query})
    assert isinstance(result, CallToolResult)
    assert result.structured_content == json.loads(compare_context(query).model_dump_json())
    assert result.structured_content is not None
    response = client.get(result.structured_content["scenario_url"])
    assert response.status_code == 200
    assert "Tool filtering" in response.text
    for invalid in (
        {"requests": "0"},
        {"input-price": "NaN"},
        {"model": "unknown"},
        {"extra": "1"},
        {"requests": ""},
        {"requests": 3},
    ):
        with pytest.raises(ToolError):
            await server.call_tool("compare_mcp_context_cost", {"parameters": invalid})
