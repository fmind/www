"""Agent discovery, representation negotiation, and end-to-end tool contracts."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from hashlib import sha256
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest
from litestar.testing import TestClient
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult
from pydantic import TypeAdapter

from www.agent_discovery import AGENT_SKILL_PATH, prefers_markdown
from www.app import create_app
from www.content import article_summaries, load_articles, visible_articles
from www.mcp import create_mcp_server
from www.publications import article_markdown_index
from www.search import SearchIndex
from www.sites.agent import compare_hosting
from www.sites.calculator import build_llm_self_hosting_view
from www.sites.models import HostingEstimate, HostingInputs


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient[Any]]:
    with TestClient(create_app()) as instance:
        yield instance


@pytest.mark.parametrize(
    ("accept", "markdown"),
    [
        ("", False),
        ("*/*", False),
        ("text/*", False),
        ("application/json", False),
        ("text/markdown", True),
        ("text/html, text/markdown", False),
        ("text/markdown, text/html", False),
        ("text/html;q=0.5, text/markdown;q=0.8", True),
        ("text/markdown;q=0.2, text/html", False),
        ("text/markdown;q=0, */*;q=1", False),
        ("text/html;q=0, text/markdown;q=0", False),
        ("text/html;q=0, text/*;q=0.5", True),
        ("text/markdown;q=0.5, text/*;q=0.8", False),
        ("text/markdown;q=bogus", False),
        ("text/markdown;q=2", False),
        ("text/markdown;q=NaN", False),
        ("text/markdown;q=-1", False),
        ("text/markdown;q=0.9999", False),
        ("text/markdown;q=1;q=0", False),
        ("TEXT/MARKDOWN; charset=utf-8", True),
        ("text/markdown;variant=unknown", False),
        ('text/markdown; charset = "utf-8"', True),
        ("text/markdown;charset=utf-8;q=0, text/markdown;q=1", False),
        ("text/html;charset=utf-8;q=0, text/html;q=1, text/markdown;q=0.5", True),
        ("text/markdown;q=0, text/*;charset=utf-8;q=1", False),
    ],
)
def test_negotiation_respects_quality_exclusions_specificity_and_browser_default(accept: str, markdown: bool) -> None:
    assert prefers_markdown(accept) is markdown


@pytest.mark.parametrize("path", ["/", "/articles/the-affordable-ai-agents/"])
def test_negotiated_get_and_head_preserve_html_and_cache_variants(client: TestClient[Any], path: str) -> None:
    for accept, content_type in (
        ("text/markdown", "text/markdown"),
        ("*/*", "text/html"),
        ("text/markdown;q=0, text/html", "text/html"),
    ):
        response = client.get(path, headers={"accept": accept, "accept-encoding": "gzip"})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(content_type)
        assert {v.strip().lower() for v in response.headers["vary"].split(",")} == {"accept", "accept-encoding"}
        head = client.head(path, headers={"accept": accept})
        assert head.status_code == 200
        assert head.content == b""
        assert head.headers["content-type"].startswith(content_type)
        assert "accept" in head.headers["vary"].lower()
        if content_type == "text/markdown":
            assert response.text.startswith("# ")
            assert "<html" not in response.text
            assert response.headers["access-control-allow-origin"] == "*"
        else:
            assert response.text.startswith("<!DOCTYPE html>")
    if path != "/":
        assert (
            client.get(path, headers={"accept": "text/markdown"}).content
            == client.get(path.rstrip("/") + ".md").content
        )


def test_home_markdown_has_public_profile_and_discovery(client: TestClient[Any]) -> None:
    body = client.get("/", headers={"accept": "text/markdown"}).text
    profile = client.get("/api/profile").json()
    assert profile["metadata"]["name"] in body
    assert all(entry["title"] in body for entry in profile["articles"])
    assert all(entry["title"] in body for entry in profile["open_source"])
    assert all(paragraph in body for paragraph in profile["biography"])
    assert "/agents" in body
    for accept in ("text/html", "text/markdown"):
        assert 'rel="api-catalog"' in client.get("/", headers={"accept": accept}).headers["link"]


def test_catalog_links_and_skill_digest_are_resolvable(client: TestClient[Any]) -> None:
    response = client.get("/.well-known/api-catalog")
    assert response.headers["content-type"].startswith("application/linkset+json")
    assert 'profile="https://www.rfc-editor.org/info/rfc9727"' in response.headers["content-type"]
    assert response.headers["access-control-allow-origin"] == "*"
    assert {urlsplit(link["href"]).path for link in response.json()["linkset"][0]["item"]} == {
        "/api/profile",
        "/mcp",
    }
    assert 'rel="api-catalog"' in client.head("/.well-known/api-catalog").headers["link"]
    for entry in response.json()["linkset"]:
        for relation, links in entry.items():
            if relation in {"anchor", "item"}:
                continue
            for link in links:
                target = client.get(urlsplit(link["href"]).path)
                assert target.status_code == 200
                assert target.headers["content-type"].startswith(link["type"])
    index = client.get("/.well-known/agent-skills/index.json")
    skill = index.json()["skills"][0]
    artifact = client.get(urlsplit(skill["url"]).path)
    assert artifact.status_code == 200
    assert artifact.headers["content-type"].startswith("text/markdown")
    assert skill["digest"] == "sha256:" + sha256(artifact.content).hexdigest()
    assert f"name: {skill['name']}" in artifact.text
    assert f"description: {skill['description']}" in artifact.text
    assert index.json()["$schema"] == "https://schemas.agentskills.io/discovery/0.2.0/schema.json"
    for path in ("/.well-known/api-catalog", "/.well-known/agent-skills/index.json", AGENT_SKILL_PATH):
        head = client.head(path)
        assert head.status_code == 200
        assert not head.content
        assert head.headers["access-control-allow-origin"] == "*"


def test_guide_is_discoverable_and_deferred_features_remain_absent(client: TestClient[Any]) -> None:
    response = client.get("/agents")
    assert response.status_code == 200
    assert "<h1>For AI agents</h1>" in response.text
    card = client.get("/.well-known/mcp/server-card.json").json()
    for primitive in (*card["tools"], *card["prompts"]):
        assert f"<code>{primitive['name']}</code>" in response.text
    assert 'href="/agents"' in client.get("/").text
    assert "/agents" in client.get("/sitemap.xml").text
    assert "/agents" in client.get("/llms.txt").text
    assert client.get("/agents/", follow_redirects=False).headers["location"] == "/agents"
    for path in (
        "/.well-known/oauth-protected-resource",
        "/.well-known/openid-configuration",
        "/auth.md",
        "/.well-known/ai-catalog.json",
        "/.well-known/ard.json",
    ):
        assert client.get(path).status_code == 404


def call_tool(client: TestClient[Any], name: str, arguments: dict[str, object]) -> dict[str, Any]:
    response = client.post(
        "/mcp",
        headers={"accept": "application/json, text/event-stream"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    assert response.status_code == 200
    return response.json()["result"]


def test_mcp_search_read_cite_workflow_over_http(client: TestClient[Any]) -> None:
    search = call_tool(client, "search_articles", {"query": "agents", "limit": 1})["structuredContent"]
    article = call_tool(client, "get_article", {"slug": search["articles"][0]["slug"]})
    assert not article.get("isError", False)
    body = article["structuredContent"]
    metadata = body["article"]
    raw = client.get(f"/articles/{metadata['slug']}.md")
    assert body["markdown"] == raw.text
    assert metadata["date"]
    assert metadata["updated"]
    assert body["canonical_url"] == metadata.get("canonical", metadata["url"])
    assert body["sections"]
    html = client.get(urlsplit(metadata["url"]).path).text
    for section in body["sections"]:
        assert section["title"]
        assert f'id="{urlsplit(section["url"]).fragment}"' in html
    assert call_tool(client, "get_article", {"slug": "unknown-article"})["isError"]
    assert call_tool(client, "get_article", {"slug": "../privacy"})["isError"]


@pytest.mark.anyio
async def test_mcp_article_reader_never_exposes_drafts() -> None:
    public = visible_articles(load_articles().all)
    draft = replace(public[0], slug="private-draft", draft=True, markdown="private text")
    server = create_mcp_server(
        article_summaries(public), SearchIndex(public), (*public, draft), article_markdown_index(public)
    )
    with pytest.raises(ToolError, match="Article not found"):
        await server.call_tool("get_article", {"slug": draft.slug})
    result = await server.call_tool("get_article", {"slug": public[0].slug})
    assert isinstance(result, CallToolResult)
    assert not result.is_error


@pytest.mark.parametrize(
    "parameters",
    [
        {},
        {"requests": "1000", "replicas": "2"},
        {"node": "a4", "billing": "cud-3y", "duty": "25", "api-mode": "batch"},
        {"api-mode": "cached", "cache-prefix": "1024", "input-tokens": "2000"},
        {"tokens": "1000000", "input-tokens": "1000000"},
        {"quality": "on", "quality-0-acceptance": "0"},
    ],
)
def test_calculator_matches_web_arithmetic_and_round_trips(parameters: dict[str, str]) -> None:
    result = compare_hosting(parameters)
    view = build_llm_self_hosting_view(parameters)
    assert result.estimate == view.estimate
    assert result.apis == view.apis
    assert result.inputs == view.inputs
    assert result.comparison_ready == view.comparison_ready
    assert result.validation == view.validation
    assert result.units["currency"] == "USD"
    assert result.units["month"] == "730 hours"
    assert result.sources["models"] == view.model_source_url
    assert result.snapshot_date == view.snapshot_date
    assert bool(result.tasks) == view.inputs.quality_enabled
    shared_query = dict(parse_qsl(urlsplit(result.scenario_url).query))
    assert build_llm_self_hosting_view(shared_query).inputs == view.inputs


@pytest.mark.parametrize(
    "parameters",
    [
        {"unknown": "100"},
        {"requests": "NaN"},
        {"requests": "0"},
        {"replicas": "1.5"},
        {"replicas": "9"},
        {"throughput": "inf"},
        {"node": "imaginary"},
        {"model": "imaginary"},
        {"quant": "imaginary"},
        {"node": "a4", "billing": "on-demand"},
        {"api-mode": "imaginary"},
        {"requests": ""},
        {"requests": " 100"},
        {"preset": "imaginary"},
        {"measured-first": "20", "measured-complete": "10"},
        {"measured-first": "1", "pilot": "old-configuration"},
    ],
)
def test_calculator_rejects_invalid_inputs(parameters: dict[str, str]) -> None:
    with pytest.raises(ValueError, match=r"[Cc]alculator parameter"):
        compare_hosting(parameters)


def test_calculator_schema_and_structured_results_over_http(client: TestClient[Any]) -> None:
    result = call_tool(client, "compare_llm_hosting", {"parameters": {"requests": "1000"}})
    assert not result.get("isError", False)
    body = result["structuredContent"]
    view = build_llm_self_hosting_view({"requests": "1000"})
    assert body["estimate"] == TypeAdapter(HostingEstimate).dump_python(view.estimate, mode="json")
    assert body["inputs"] == TypeAdapter(HostingInputs).dump_python(view.inputs, mode="json")
    assert body["models"]
    assert body["node_pools"]
    assert body["quantizations"]
    assert body["limitations"]
    assert body["latency"]
    assert body["sources"]
    for parameters in ({"requests": 1000}, {"requests": "0"}, {"requests": "x" * 129}, {"unknown": "1"}):
        assert call_tool(client, "compare_llm_hosting", {"parameters": parameters})["isError"]
    assert call_tool(client, "compare_llm_hosting", {})["isError"]
