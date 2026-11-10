"""HTTP boundary and privacy tests."""

from datetime import datetime
from typing import Any, cast

import pytest
from litestar import HttpMethod, Litestar, Request, route
from litestar.datastructures import Headers
from litestar.middleware import DefineMiddleware
from litestar.response import Response
from litestar.testing import TestClient
from litestar.types import ASGIApp, HTTPDisconnectEvent, Message, Receive, Scope, Send

from tests.conftest import RecordingLogger, asgi_scope
from www.config import Config, Environment
from www.middleware import (
    CLOUD_TRACE_LOG_KEY,
    SiteMiddleware,
    analytics_dimension,
    analytics_path,
    is_bot,
    log_path,
    referer_host,
    request_trace_id,
)
from www.ranges import etag_matches, strong_etag_matches

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"


async def _disconnected() -> HTTPDisconnectEvent:
    return {"type": "http.disconnect"}


async def _discard(_message: Message) -> None:
    return None


def client(
    environment: Environment = Environment.DEVELOPMENT, project: str = ""
) -> tuple[TestClient[Any], RecordingLogger]:
    logger = RecordingLogger()

    @route("/", http_method=[HttpMethod.GET, HttpMethod.HEAD], sync_to_thread=False)
    def home(request: Request[Any, Any, Any]) -> Response[str]:
        nonce = request.scope["state"]["csp_nonce"]
        return Response(f'<html><script nonce="{nonce}"></script></html>', media_type="text/html")

    @route("/form", http_method=[HttpMethod.POST], sync_to_thread=False)
    def form() -> str:
        return "posted"

    app = Litestar(
        route_handlers=[home, form],
        middleware=[
            DefineMiddleware(
                SiteMiddleware, config=Config(environment=environment, google_cloud_project=project), logger=logger
            )
        ],
        openapi_config=None,
    )
    base_url = "http://fmind.dev" if environment is Environment.PRODUCTION else "http://testserver.local"
    return TestClient(app, base_url=base_url), logger


def test_security_headers_authorize_the_request_nonce() -> None:
    with client()[0] as test_client:
        response = test_client.get("/")

    nonce = response.text.split('nonce="', 1)[1].split('"', 1)[0]
    assert f"script-src 'self' 'nonce-{nonce}'" in response.headers["content-security-policy"]
    assert "style-src 'self';" in response.headers["content-security-policy"]
    # Google Analytics after consent: its script, beacon and pixel hosts only; frames and the default stay self.
    policy = dict(item.strip().split(" ", 1) for item in response.headers["content-security-policy"].split(";") if item)
    # Literal values: comparing against the middleware's own builder would be a tautology.
    assert policy == {
        "default-src": "'self'",
        "base-uri": "'none'",
        "object-src": "'none'",
        "frame-ancestors": "'none'",
        "form-action": "'self'",
        "script-src": f"'self' 'nonce-{nonce}' 'strict-dynamic' https://*.googletagmanager.com",
        "style-src": "'self'",
        "img-src": "'self' data: https://*.google-analytics.com https://*.googletagmanager.com",
        "font-src": "'self'",
        "connect-src": (
            "'self' https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com"
        ),
    }
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cross-origin-opener-policy"] == "same-origin-allow-popups"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    assert response.headers["x-permitted-cross-domain-policies"] == "none"
    assert response.headers["x-xss-protection"] == "0"
    assert response.headers["permissions-policy"] == (
        "accelerometer=(), autoplay=(self), camera=(), display-capture=(), encrypted-media=(), fullscreen=(), "
        "geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), sync-xhr=(), usb=()"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["vary"] == "Accept-Encoding"
    assert "strict-transport-security" not in response.headers


def test_production_apex_redirect_keeps_query_and_security_headers() -> None:
    test_client, logger = client(Environment.PRODUCTION)
    with test_client:
        response = test_client.get(
            "/?q=agents",
            follow_redirects=False,
        )

    assert response.status_code == 301
    assert response.headers["location"] == "https://www.fmind.dev/?q=agents"
    assert response.headers["strict-transport-security"] == "max-age=63072000; includeSubDomains; preload"
    assert response.headers["vary"] == "Accept-Encoding"
    assert logger.records == []


def test_production_apex_redirect_keeps_the_method_for_posts() -> None:
    test_client, _ = client(Environment.PRODUCTION)
    with test_client:
        response = test_client.post("/form?step=1", content=b"{}", follow_redirects=False)

    assert response.status_code == 308
    assert response.headers["location"] == "https://www.fmind.dev/form?step=1"


def test_head_requests_are_not_pageviews() -> None:
    test_client, logger = client()
    with test_client:
        assert test_client.head("/").status_code == 200

    assert [event for event, _ in logger.records] == ["http request processed"]


def test_pageview_log_keeps_only_bounded_dimensions() -> None:
    test_client, logger = client()
    with test_client:
        response = test_client.get(
            "/?utm_source=newsletter&utm_medium=bad%20value&utm_campaign=" + "x" * 129,
            headers={
                "referer": "https://EXAMPLE.com/path?private=yes",
                "user-agent": "ExampleBot/1.0",
                "x-client-geo": " fr ",
            },
        )

    assert response.status_code == 200
    pageview = next(values for event, values in logger.records if event == "analytics_pageview")
    assert pageview == {
        "timestamp": pageview["timestamp"],
        "path": "/",
        "status": 200,
        "referer": "example.com",
        "utm_source": "newsletter",
        "utm_medium": "",
        "utm_campaign": "",
        # Public Cloud Run requests may supply arbitrary X-Client-* headers.
        # Keep the schema stable without treating either value as geography.
        "country": "",
        "bot": True,
    }
    assert isinstance(pageview["timestamp"], str)
    assert datetime.fromisoformat(pageview["timestamp"])
    assert "trace_id" not in pageview
    assert "span_id" not in pageview


def test_privacy_helpers_reject_unbounded_or_invalid_values() -> None:
    assert analytics_path("/private-id", 404) == "/404"
    assert analytics_path("/private-id", 500) == "/500"
    assert analytics_dimension("agent_campaign-1") == "agent_campaign-1"
    assert analytics_dimension("contains spaces") == ""
    assert referer_host("https://EXAMPLE.com:8443/private") == "example.com"
    assert referer_host("https://EXAMPLE.com./private") == "example.com"
    assert referer_host("https://xn--bcher-kva.example/x") == "xn--bcher-kva.example"
    assert referer_host("android-app://com.linkedin.android/") == "com.linkedin.android"
    for invalid_referer in (
        "not a URL",
        "javascript://alert.example/1",
        "data://text.example/plain",
        "http://127.0.0.1:8080/private",
        "http://[::1]/private",
        "http://localhost:8080/",
        "https://arbitrary private text!/path",
        f"https://{'a' * 64}.example/",
        f"https://example.com/{'x' * 2048}",
    ):
        assert referer_host(invalid_referer) == "", invalid_referer
    assert log_path("/clean/path") == "/clean/path"
    assert log_path("/bad\npath\r\x1b[31m\x00") == "/bad%0Apath%0D%1B[31m%00"
    assert len(log_path("/" + "a" * 700)) == 512
    assert is_bot("Mozilla compatible; LinkedInBot")
    assert not is_bot("Mozilla/5.0 Firefox")
    for automated in (
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot",
        "Mozilla/5.0 (compatible; Claude-Web/1.0; +https://support.anthropic.com)",
        "Mozilla/5.0 (compatible; MistralAI-User/1.0; +https://docs.mistral.ai/robots)",
        "Mozilla/5.0 (compatible; GoogleOther)",
        "Mozilla/5.0 (compatible; Google-InspectionTool/1.0)",
        "GoogleStackdriverMonitoring-UptimeChecks(https://cloud.google.com/monitoring)",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/140.0 Safari/537.36",
        "curl/8.9.1",
        "python-requests/2.32.3",
        "Python-urllib/3.14",
        "Python/3.14 aiohttp/3.11.0",
        "Go-http-client/2.0",
        "okhttp/4.12.0",
        "undici",
        "WhatsApp/2.24.1 A",
        "",
    ):
        assert is_bot(automated), automated
    assert not is_bot("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Safari")


def test_etag_matching_accepts_weak_and_list_validators() -> None:
    assert etag_matches('"old", W/"abc123"', '"abc123"')
    assert etag_matches("*", '"abc123"')
    assert not etag_matches('"other"', '"abc123"')
    assert strong_etag_matches('"old", "abc123"', '"abc123"')
    assert strong_etag_matches("*", '"abc123"')
    assert not strong_etag_matches('W/"abc123"', '"abc123"')
    assert not strong_etag_matches('*, "abc123"', '"abc123"')


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"traceparent": f"00-{TRACE_ID}-00f067aa0ba902b7-01"}, TRACE_ID),
        ({"x-cloud-trace-context": f"{TRACE_ID}/12345678901234567890;o=1"}, TRACE_ID),
        ({"x-cloud-trace-context": f"{TRACE_ID}/1"}, TRACE_ID),
        # traceparent wins; a malformed one falls back to Cloud Run's header.
        ({"traceparent": f"00-{'a' * 32}-00f067aa0ba902b7-01", "x-cloud-trace-context": f"{TRACE_ID}/1"}, "a" * 32),
        ({"traceparent": "00-bogus-00f067aa0ba902b7-01", "x-cloud-trace-context": f"{TRACE_ID}/1"}, TRACE_ID),
        ({}, ""),
        ({"traceparent": f"00-{'0' * 32}-00f067aa0ba902b7-01"}, ""),
        ({"traceparent": f"00-{TRACE_ID.upper()}-00f067aa0ba902b7-01"}, ""),
        ({"traceparent": f"01-{TRACE_ID}-00f067aa0ba902b7-01"}, ""),
        ({"traceparent": f"00-{TRACE_ID}-00f067aa0ba902b7-01-extra"}, ""),
        ({"x-cloud-trace-context": f"{TRACE_ID}/1/../../projects/other"}, ""),
        ({"x-cloud-trace-context": f"{TRACE_ID[:-1]}/1"}, ""),
    ],
)
def test_request_trace_id_accepts_only_well_formed_headers(headers: dict[str, str], expected: str) -> None:
    assert request_trace_id(Headers(headers)) == expected


def test_request_logs_carry_the_cloud_trace_only_when_a_project_is_configured() -> None:
    headers = {"x-cloud-trace-context": f"{TRACE_ID}/1;o=1", "user-agent": "Mozilla/5.0 Firefox/140.0"}
    test_client, logger = client(project="example-project")
    with test_client:
        assert test_client.get("/", headers=headers).status_code == 200
        assert test_client.get("/", headers={"x-cloud-trace-context": "forged/1"}).status_code == 200

    request_logs = [values for event, values in logger.records if event == "http request processed"]
    assert request_logs[0][CLOUD_TRACE_LOG_KEY] == f"projects/example-project/traces/{TRACE_ID}"
    assert CLOUD_TRACE_LOG_KEY not in request_logs[1]
    # Analytics stay free of request identifiers.
    pageviews = [values for event, values in logger.records if event == "analytics_pageview"]
    assert len(pageviews) == 2
    assert all(CLOUD_TRACE_LOG_KEY not in values for values in pageviews)

    local_client, local_logger = client()
    with local_client:
        assert local_client.get("/", headers=headers).status_code == 200
    assert all(CLOUD_TRACE_LOG_KEY not in values for _, values in local_logger.records)


@pytest.mark.anyio
async def test_escaping_exception_is_finalized_as_a_server_error() -> None:
    logger = RecordingLogger()

    async def failing_app(_scope: Scope, _receive: Receive, _send: Send) -> None:
        raise RuntimeError("request failed")

    middleware = SiteMiddleware(
        cast(ASGIApp, failing_app),
        Config(environment=Environment.DEVELOPMENT),
        logger,
    )
    with pytest.raises(RuntimeError, match="request failed"):
        await middleware(asgi_scope(raw_path=b"/boom"), _disconnected, _discard)

    assert len(logger.records) == 1
    event, values = logger.records[0]
    assert event == "http request processed"
    assert values["path"] == "/boom"
    assert values["status"] == 500
    assert values["size_bytes"] == 0


@pytest.mark.anyio
async def test_pathsend_response_logs_the_file_size_before_returning() -> None:
    logger = RecordingLogger()
    sent: list[str] = []

    async def file_app(_scope: Scope, _receive: Receive, send: Send) -> None:
        headers = [(b"content-type", b"image/png"), (b"content-length", b"2048")]
        await send({"type": "http.response.start", "status": 200, "headers": headers})
        await send(cast(Message, {"type": "http.response.pathsend", "path": "/app/static/logo.png"}))
        # Logged while the request span is still current, not in teardown.
        sent.append(f"{len(logger.records)} records")

    middleware = SiteMiddleware(cast(ASGIApp, file_app), Config(environment=Environment.DEVELOPMENT), logger)
    scope = asgi_scope(raw_path=b"/logo.png", extensions={"http.response.pathsend": {}})
    await middleware(scope, _disconnected, _discard)

    assert sent == ["1 records"]
    assert [event for event, _ in logger.records] == ["http request processed"]
    assert logger.records[0][1]["size_bytes"] == 2048


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("raw_path", "path", "query", "host", "expected"),
    [
        (None, "/privacy", b"", b"fmind.dev.", b"https://www.fmind.dev/privacy"),
        (b"", "/privacy", b"", b"fmind.dev", b"https://www.fmind.dev/privacy"),
        (b"//evil.example/path", "//evil.example/path", b"", b"fmind.dev", b"https://www.fmind.dev/evil.example/path"),
        (b"@evil.example", "@evil.example", b"", b"fmind.dev", b"https://www.fmind.dev/"),
        (b"*", "*", b"", b"fmind.dev", b"https://www.fmind.dev/"),
        (b"/a b\r\nc", "/a b\r\nc", b"q=1\r\n2", b"fmind.dev", b"https://www.fmind.dev/a%20b%0D%0Ac?q=1%0D%0A2"),
    ],
)
async def test_production_apex_redirect_neutralizes_non_origin_paths_and_control_bytes(
    raw_path: bytes | None,
    path: str,
    query: bytes,
    host: bytes,
    expected: bytes,
) -> None:
    messages: list[Message] = []
    middleware = SiteMiddleware(
        cast(ASGIApp, _discard),
        Config(environment=Environment.PRODUCTION),
        RecordingLogger(),
    )
    scope = asgi_scope(headers=[(b"host", host)])
    cast(dict[str, object], scope)["raw_path"] = raw_path
    scope["path"] = path
    scope["query_string"] = query

    async def record(message: Message) -> None:
        messages.append(message)

    await middleware(scope, _disconnected, record)

    start = next(message for message in messages if message["type"] == "http.response.start")
    headers = dict(start["headers"])
    assert start["status"] == 301
    assert headers[b"location"] == expected
    assert headers[b"cross-origin-resource-policy"] == b"same-origin"


@pytest.mark.anyio
async def test_mcp_fetch_metadata_normalizes_case_and_request_logs_escape_controls() -> None:
    logger = RecordingLogger()
    called: list[str] = []

    async def ok_app(scope: Scope, _receive: Receive, send: Send) -> None:
        called.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b"{}", "more_body": False})

    middleware = SiteMiddleware(cast(ASGIApp, ok_app), Config(environment=Environment.DEVELOPMENT), logger)
    allowed = asgi_scope(method="POST", raw_path=b"/mcp", headers=[(b"sec-fetch-site", b" Same-Origin ")])
    await middleware(allowed, _disconnected, _discard)
    assert called == ["/mcp"]

    blocked_messages: list[Message] = []

    async def record_blocked(message: Message) -> None:
        blocked_messages.append(message)

    blocked = asgi_scope(method="POST", raw_path=b"/mcp", headers=[(b"sec-fetch-site", b"Cross-Site")])
    await middleware(blocked, _disconnected, record_blocked)
    blocked_start = next(message for message in blocked_messages if message["type"] == "http.response.start")
    assert blocked_start["status"] == 403

    control_scope = asgi_scope(raw_path=b"/probe")
    control_scope["path"] = "/probe\nforged"
    await middleware(control_scope, _disconnected, _discard)
    assert logger.records[-1][1]["path"] == "/probe%0Aforged"
