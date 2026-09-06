"""Application routing, delivery, and lifecycle integration tests."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from litestar.plugins.opentelemetry import OpenTelemetryPlugin
from litestar.testing import TestClient
from opentelemetry.sdk.trace import TracerProvider

import www.app as app_module
from www.app import app, create_app
from www.assets import ApplicationAssets, load_application_assets
from www.config import Config, Environment
from www.content import ArticleCollection, article_summaries, load_articles, visible_articles
from www.data import METADATA, OPEN_SOURCE, SITE_PAGES
from www.rendering import Renderer

type AppClient = TestClient[Any]

FONT_PATHS = (
    "/static/fonts/Inter-Variable.woff2",
    "/static/fonts/Outfit-Variable.woff2",
)


@dataclass
class RecordingLogger:
    records: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def info(self, event: str, **values: Any) -> None:
        self.records.append((event, values))

    def error(self, event: str, **values: Any) -> None:
        self.records.append((event, values))


@pytest.fixture(scope="module")
def client() -> Iterator[AppClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def snapshots() -> tuple[ApplicationAssets, ArticleCollection]:
    return load_application_assets(), load_articles()


def test_human_pages_render_complete_no_cache_documents(client: AppClient) -> None:
    cases = {
        "/": ("Médéric Hurier", 200),
        "/articles/": ("Articles", 200),
        "/articles/the-affordable-ai-agents/": ("The Affordable AI Agents", 200),
        "/sites/": ("LLM self-hosting on GKE", 200),
        "/sites/llm-self-hosting/?requests=234&replicas=2": ("2 nodes · 2 GPUs", 200),
        "/healthz": ("Page not found", 404),
        "/does-not-exist": ("Page not found", 404),
        "/articles/the-affordable-ai-agents/extra/": ("Page not found", 404),
    }

    for path, (marker, status) in cases.items():
        response = client.get(path)
        assert response.status_code == status, path
        assert response.headers["content-type"].startswith("text/html")
        assert response.headers["cache-control"] == "no-cache"
        assert response.text.startswith("<!DOCTYPE html>")
        assert marker in response.text
        assert "</html>" in response.text
        if status == 404:
            assert 'content="noindex, follow"' in response.text


def test_canonical_redirects_preserve_only_the_established_queries(client: AppClient) -> None:
    cases = {
        "/articles?tag=Agent": "/articles/?tag=Agent",
        "/articles/the-affordable-ai-agents?q=agent%20cost": ("/articles/the-affordable-ai-agents/?q=agent%20cost"),
        "/sites?requests=234": "/sites/",
        "/sites/llm-self-hosting?requests=234&replicas=2": ("/sites/llm-self-hosting/?requests=234&replicas=2"),
    }

    for path, location in cases.items():
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 301, path
        assert response.headers["location"] == location


def test_machine_surfaces_keep_content_cache_and_cors_contracts(client: AppClient) -> None:
    cases = (
        ("/health", "application/json; charset=utf-8", None, None, b'{"status":"ok"}'),
        ("/robots.txt", "text/plain; charset=utf-8", "public, max-age=86400, must-revalidate", None, b"User-agent"),
        ("/llms.txt", "text/plain; charset=utf-8", "public, max-age=3600, must-revalidate", None, b"## Articles"),
        (
            "/llms-full.txt",
            "text/plain; charset=utf-8",
            "public, max-age=3600, must-revalidate",
            None,
            b"## Full articles",
        ),
        ("/sitemap.xml", "application/xml; charset=utf-8", "public, max-age=3600, must-revalidate", None, b"<urlset"),
        (
            "/articles/feed.xml",
            "application/atom+xml; charset=utf-8",
            "public, max-age=3600, must-revalidate",
            None,
            b"<feed",
        ),
        ("/api/profile", "application/json; charset=utf-8", "public, max-age=3600", "*", b'"metadata"'),
        (
            "/mcp/server-card",
            "application/mcp-server-card+json; charset=utf-8",
            "public, max-age=3600, must-revalidate",
            "*",
            b'"protocolVersion": "2026-07-28"',
        ),
        (
            "/.well-known/mcp/server-card.json",
            "application/mcp-server-card+json; charset=utf-8",
            "public, max-age=3600, must-revalidate",
            "*",
            b'"name": "get_profile"',
        ),
    )

    for path, content_type, cache_control, cors, marker in cases:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["content-type"] == content_type
        assert response.headers.get("cache-control") == cache_control
        assert response.headers.get("access-control-allow-origin") == cors
        assert marker in response.content


def test_profile_json_matches_the_go_omission_and_time_contract(
    client: AppClient,
    snapshots: tuple[ApplicationAssets, ArticleCollection],
) -> None:
    response = client.get("/api/profile")
    payload = response.json()
    summaries = article_summaries(visible_articles(snapshots[1].all))

    assert response.content.endswith(b"\n")
    assert len(payload["articles"]) == len(summaries)
    for encoded, article in zip(payload["articles"], summaries, strict=True):
        assert article.updated is not None
        expected: dict[str, object] = {
            "date": article.date.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "updated": article.updated.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "title": article.title,
            "description": article.description,
            "slug": article.slug,
            "url": article.url,
            "image_url": article.image_url,
            "image_alt": article.image_alt,
            "tags": list(article.tags),
            "reading_minutes": article.reading_minutes,
        }
        if article.canonical:
            expected["canonical"] = article.canonical
        if article.syndicated:
            expected["syndicated"] = article.syndicated
        assert encoded == expected

    assert payload["site_pages"] == [
        {
            "slug": page.slug,
            "title": page.title,
            "description": page.description,
            "audience": page.audience,
            "url": page.url,
        }
        for page in SITE_PAGES
    ]
    assert payload["open_source"] == [
        {
            "title": project.title,
            "href": project.href,
            **({"repo": project.repo} if project.repo else {}),
            "description": project.description,
        }
        for project in OPEN_SOURCE
    ]
    assert all("article_slugs" not in page for page in payload["site_pages"])


def test_article_markdown_is_public_and_unknown_sources_are_noindex(client: AppClient) -> None:
    response = client.get("/articles/the-affordable-ai-agents.md")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.headers["cache-control"] == "public, max-age=3600, must-revalidate"
    assert response.text.startswith("# The Affordable AI Agents\n")
    assert "](/static/" not in response.text

    missing = client.get("/articles/not-an-article.md")
    assert missing.status_code == 404
    assert missing.headers["cache-control"] == "no-cache"
    assert 'content="noindex, follow"' in missing.text


def test_security_policy_has_a_live_rfc3339_expiry(client: AppClient) -> None:
    for path in ("/security.txt", "/.well-known/security.txt"):
        response = client.get(path)
        expiry = next(
            line.removeprefix("Expires: ") for line in response.text.splitlines() if line.startswith("Expires: ")
        )
        assert response.status_code == 200
        assert datetime.fromisoformat(expiry) > datetime.now(UTC)
        assert f"Contact: mailto:{METADATA.email}" in response.text
        assert response.headers["cache-control"] == "public, max-age=86400, must-revalidate"


def test_static_assets_have_content_hash_revalidation_without_download_headers(
    client: AppClient,
    snapshots: tuple[ApplicationAssets, ArticleCollection],
) -> None:
    path = "/static/img/avatar-192.webp"
    response = client.get(path, headers={"accept-encoding": "gzip"})
    etag = f'"{snapshots[0].hashes[path]}"'

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "public, max-age=86400, must-revalidate"
    assert response.headers["etag"] == etag
    assert "content-disposition" not in response.headers
    assert "content-encoding" not in response.headers

    revalidated = client.get(path, headers={"if-none-match": f'"old", W/{etag}'})
    assert revalidated.status_code == 304
    assert revalidated.content == b""
    assert revalidated.headers["etag"] == etag

    digest = snapshots[0].hashes[path]
    cache_cases = {
        f"{path}?v={digest}": "public, max-age=31536000, immutable",
        f"{path}?v=wrong": "public, max-age=86400, must-revalidate",
        f"{path}?v=": "public, max-age=86400, must-revalidate",
        f"{path}?v={digest}&v={digest}": "public, max-age=86400, must-revalidate",
    }
    for request_path, cache_control in cache_cases.items():
        assert client.get(request_path).headers["cache-control"] == cache_control, request_path

    ordinary_query = client.get(path + "?xv=1")
    assert ordinary_query.headers["cache-control"] == "public, max-age=86400, must-revalidate"

    root = client.get("/static/", follow_redirects=False)
    assert root.status_code == 404
    assert root.headers["x-content-type-options"] == "nosniff"

    stylesheet = client.get("/static/dist/styles.css", headers={"accept-encoding": "identity"})
    static_text = client.get("/static/robots.txt", headers={"accept-encoding": "identity"})
    assert stylesheet.headers["content-type"] == "text/css; charset=utf-8"
    assert static_text.headers["content-type"] == "text/plain; charset=utf-8"


def test_static_if_match_is_strong_and_precedes_cache_and_range_conditions(
    client: AppClient,
    snapshots: tuple[ApplicationAssets, ArticleCollection],
) -> None:
    path = "/static/img/avatar-192.webp"
    etag = f'"{snapshots[0].hashes[path]}"'

    exact = client.get(path, headers={"if-match": etag})
    wildcard = client.head(path, headers={"if-match": "*"})
    matching_range = client.get(path, headers={"if-match": etag, "range": "bytes=0-9"})
    matching_list = client.get(
        path,
        headers={"if-match": f'"stale", W/{etag}, {etag}', "range": "bytes=1-2"},
    )
    stale = client.get(path, headers={"if-match": '"stale"'})
    weak = client.head(path, headers={"if-match": f"W/{etag}"})
    stale_list = client.get(path, headers={"if-match": '"stale", "other"'})
    stale_range = client.get(
        path,
        headers={"if-match": '"stale"', "if-none-match": etag, "range": "bytes=0-9"},
    )

    assert exact.status_code == 200
    assert wildcard.status_code == 200
    assert matching_range.status_code == 206
    assert matching_range.content == exact.content[:10]
    assert matching_list.status_code == 206
    assert matching_list.content == exact.content[1:3]
    for response in (stale, weak, stale_list, stale_range):
        assert response.status_code == 412
        assert response.content == b""
        assert response.headers["etag"] == etag
        assert "content-range" not in response.headers


@pytest.mark.parametrize("encoding", ["identity", "gzip", "br"])
def test_static_validators_and_ranges_identify_the_same_bytes(client: AppClient, encoding: str) -> None:
    path = "/static/dist/styles.css"
    headers = {"accept-encoding": encoding}
    full = client.get(path, headers=headers)
    partial = client.get(path, headers={**headers, "range": "bytes=0-999", "if-range": full.headers["etag"]})
    head = client.head(path, headers=headers)

    assert full.status_code == head.status_code == 200
    assert partial.status_code == 206
    assert partial.content == full.content[:1000]
    assert partial.headers["content-range"] == f"bytes 0-999/{len(full.content)}"
    for response in (full, partial, head):
        assert "content-encoding" not in response.headers
        assert response.headers["etag"] == full.headers["etag"]
    assert head.headers["content-length"] == str(len(full.content))


@pytest.mark.parametrize(
    "path",
    [
        "/static/%00",
        "/static/fonts/%2e/Inter-Variable.woff2",
        "/static/fonts/%2e%2e/robots.txt",
        "/static/%2e%2e/pyproject.toml",
        "/static/missing.css",
    ],
)
def test_static_unknown_and_noncanonical_paths_are_not_found(client: AppClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_font_preloads_share_the_unversioned_font_face_cache_keys(client: AppClient) -> None:
    response = client.get("/")

    for path in FONT_PATHS:
        assert f'<link rel="preload" href="{path}"' in response.text
        assert f'href="{path}?v=' not in response.text


@pytest.mark.parametrize("path", FONT_PATHS)
def test_required_fonts_have_woff2_content_type_and_revalidate(
    client: AppClient,
    snapshots: tuple[ApplicationAssets, ArticleCollection],
    path: str,
) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"] == "font/woff2"
    assert response.headers["cache-control"] == "public, max-age=86400, must-revalidate"
    assert response.headers["etag"] == f'"{snapshots[0].hashes[path]}"'
    assert response.content.startswith(b"wOF2")


def test_static_assets_support_bounded_byte_ranges(client: AppClient) -> None:
    path = "/static/img/articles/how-to-configure-vs-code-for-ai-ml-and-mlops-development-in-python/04.mp4"
    full = client.get(path)
    partial = client.get(path, headers={"range": "bytes=10-19"})
    head = client.head(path, headers={"range": "bytes=-10"})

    assert full.status_code == 200
    assert full.headers["accept-ranges"] == "bytes"
    assert "content-disposition" not in full.headers

    assert partial.status_code == 206
    assert partial.content == full.content[10:20]
    assert partial.headers["content-range"] == f"bytes 10-19/{len(full.content)}"
    assert partial.headers["etag"] == full.headers["etag"]
    assert partial.headers["content-length"] == "10"

    assert head.status_code == 206
    assert head.content == b""
    assert (
        head.headers["content-range"] == f"bytes {len(full.content) - 10}-{len(full.content) - 1}/{len(full.content)}"
    )
    assert head.headers["content-length"] == "10"


def test_every_response_has_security_headers_and_text_can_compress(client: AppClient) -> None:
    response = client.get("/llms.txt", headers={"accept-encoding": "gzip"})

    assert response.headers["content-encoding"] == "gzip"
    assert response.headers["vary"] == "Accept-Encoding"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert "strict-transport-security" not in response.headers

    for path in ("/health", "/llms.txt", "/static/img/avatar-192.webp", "/does-not-exist"):
        identity = client.get(path, headers={"accept-encoding": "identity"})
        assert identity.headers["vary"] == "Accept-Encoding", path


def test_dynamic_rendering_and_search_run_outside_the_asgi_loop(
    monkeypatch: pytest.MonkeyPatch,
    snapshots: tuple[ApplicationAssets, ArticleCollection],
) -> None:
    observed_running_loops: list[bool] = []
    original_render = Renderer.render

    def recording_render(self: Renderer, *args: Any, **kwargs: Any) -> str:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            observed_running_loops.append(False)
        else:
            observed_running_loops.append(True)
        return original_render(self, *args, **kwargs)

    monkeypatch.setattr(Renderer, "render", recording_render)
    threaded_app = create_app(assets=snapshots[0], collection=snapshots[1], logger=RecordingLogger())

    with TestClient(threaded_app) as test_client:
        for path in ("/", "/articles/?q=agents", "/sites/llm-self-hosting/?requests=234", "/missing"):
            assert test_client.get(path).status_code in {200, 404}

    assert observed_running_loops == [False, False, False, False]


def test_http_boundary_preserves_head_and_unsupported_method_contract(
    snapshots: tuple[ApplicationAssets, ArticleCollection],
) -> None:
    logger = RecordingLogger()
    production = create_app(
        config=Config(environment=Environment.PRODUCTION),
        assets=snapshots[0],
        collection=snapshots[1],
        logger=logger,
    )

    with TestClient(production, base_url="https://www.fmind.dev") as test_client:
        head = test_client.head("/")
        unsupported = test_client.post("/")

    assert head.status_code == 200
    assert head.content == b""
    assert int(head.headers["content-length"]) > 0
    assert head.headers["strict-transport-security"].startswith("max-age=63072000")
    assert "default-src 'self'" in head.headers["content-security-policy"]

    assert unsupported.status_code == 404
    assert unsupported.headers["content-type"].startswith("text/html")
    assert unsupported.headers["strict-transport-security"].startswith("max-age=63072000")
    assert "Page not found" in unsupported.text
    assert any(
        event == "http request processed" and values["method"] == "POST" and values["status"] == 404
        for event, values in logger.records
    )


def test_unexpected_failures_are_logged_and_return_a_non_leaking_500(
    monkeypatch: pytest.MonkeyPatch,
    snapshots: tuple[ApplicationAssets, ArticleCollection],
) -> None:
    def fail_render(*_: object, **__: object) -> str:
        msg = "private render failure"
        raise RuntimeError(msg)

    monkeypatch.setattr(app_module.Renderer, "render", fail_render)
    logger = RecordingLogger()
    failing_app = create_app(assets=snapshots[0], collection=snapshots[1], logger=logger)

    with TestClient(failing_app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/")

    assert response.status_code == 500
    assert response.content == b"Internal Server Error\n"
    assert "private render failure" not in response.text
    error = next(values for event, values in logger.records if event == "unhandled request failure")
    assert error["path"] == "/"
    assert error["method"] == "GET"
    assert error["error_type"] == "RuntimeError"
    assert isinstance(error["exc_info"], RuntimeError)


def test_unexpected_failure_log_carries_the_active_trace_context(
    monkeypatch: pytest.MonkeyPatch,
    snapshots: tuple[ApplicationAssets, ArticleCollection],
) -> None:
    def fail_render(*_: object, **__: object) -> str:
        raise RuntimeError("traced render failure")

    provider = TracerProvider(shutdown_on_exit=False)
    monkeypatch.setattr(app_module, "configure_telemetry", lambda: provider)
    monkeypatch.setattr(app_module, "shutdown_telemetry", lambda _: True)
    monkeypatch.setattr(app_module.Renderer, "render", fail_render)
    logger = RecordingLogger()
    failing_app = create_app(assets=snapshots[0], collection=snapshots[1], logger=logger)

    with TestClient(failing_app, raise_server_exceptions=False) as test_client:
        assert test_client.get("/").status_code == 500

    error = next(values for event, values in logger.records if event == "unhandled request failure")
    assert len(error["trace_id"]) == 32
    assert len(error["span_id"]) == 16


def test_mcp_mount_is_stateless_bounded_and_origin_protected(
    client: AppClient,
    snapshots: tuple[ApplicationAssets, ArticleCollection],
) -> None:
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        },
    }
    headers = {"accept": "application/json, text/event-stream"}

    for path in ("/mcp", "/mcp/"):
        response = client.post(path, json=initialize, headers={**headers, "accept-encoding": "gzip"})
        assert response.status_code == 200
        assert response.json()["result"]["serverInfo"]["name"] == "www"
        assert response.json()["result"]["capabilities"] == {
            "prompts": {"listChanged": True},
            "resources": {"listChanged": True},
            "tools": {"listChanged": True},
        }
        assert response.headers["cache-control"] == "no-cache, no-transform"
        assert response.headers["vary"] == "Accept-Encoding"
        assert "content-encoding" not in response.headers

    rejected = client.post(
        "/mcp",
        json=initialize,
        headers={**headers, "origin": "https://evil.example"},
    )
    assert rejected.status_code == 403

    for fetch_site in ("cross-site", "same-site"):
        rejected = client.post(
            "/mcp",
            json=initialize,
            headers={**headers, "sec-fetch-site": fetch_site},
        )
        assert rejected.status_code == 403
        assert rejected.text == "cross-origin request detected from Sec-Fetch-Site header\n"

    allowed = client.post(
        "/mcp",
        json=initialize,
        headers={**headers, "sec-fetch-site": "same-origin"},
    )
    assert allowed.status_code == 200

    oversized = client.post(
        "/mcp",
        content=b"x" * ((1 << 20) + 1),
        headers={**headers, "content-type": "application/json"},
    )
    assert oversized.status_code == 413

    logger = RecordingLogger()
    logged_app = create_app(assets=snapshots[0], collection=snapshots[1], logger=logger)
    with TestClient(logged_app) as test_client:
        assert test_client.post("/mcp", json=initialize, headers=headers).status_code == 200
    request_log = next(values for event, values in logger.records if event == "http request processed")
    assert request_log["path"] == "/mcp"


def test_opentelemetry_is_opt_in_and_correlates_request_logs(
    monkeypatch: pytest.MonkeyPatch,
    snapshots: tuple[ApplicationAssets, ArticleCollection],
) -> None:
    assets, collection = snapshots
    monkeypatch.setattr(app_module, "configure_telemetry", lambda: None)
    uninstrumented = create_app(assets=assets, collection=collection, logger=RecordingLogger())
    assert not any(isinstance(plugin, OpenTelemetryPlugin) for plugin in uninstrumented.plugins)

    provider = TracerProvider(shutdown_on_exit=False)
    logger = RecordingLogger()
    monkeypatch.setattr(app_module, "configure_telemetry", lambda: provider)
    instrumented = create_app(
        config=Config(),
        assets=assets,
        collection=collection,
        logger=logger,
    )
    assert any(isinstance(plugin, OpenTelemetryPlugin) for plugin in instrumented.plugins)

    with TestClient(instrumented) as test_client:
        assert test_client.get("/health").status_code == 200
        assert test_client.get("/articles/").status_code == 200

    request_log = next(values for event, values in logger.records if event == "http request processed")
    assert len(request_log["trace_id"]) == 32
    assert len(request_log["span_id"]) == 16
    analytics = next(values for event, values in logger.records if event == "analytics_pageview")
    assert "trace_id" not in analytics
    assert "span_id" not in analytics


def test_incomplete_telemetry_shutdown_is_reported(
    monkeypatch: pytest.MonkeyPatch,
    snapshots: tuple[ApplicationAssets, ArticleCollection],
) -> None:
    provider = TracerProvider(shutdown_on_exit=False)
    monkeypatch.setattr(app_module, "configure_telemetry", lambda: provider)
    monkeypatch.setattr(app_module, "shutdown_telemetry", lambda _: False)
    logger = RecordingLogger()
    instrumented = create_app(assets=snapshots[0], collection=snapshots[1], logger=logger)

    with TestClient(instrumented):
        pass

    assert (
        "telemetry shutdown incomplete",
        {"timeout_seconds": app_module.TELEMETRY_SHUTDOWN_TIMEOUT_SECONDS},
    ) in logger.records
