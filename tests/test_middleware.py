"""HTTP boundary and privacy tests."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

import pytest
from litestar import HttpMethod, Litestar, Request, route
from litestar.datastructures import Headers
from litestar.middleware import DefineMiddleware
from litestar.response import Response
from litestar.testing import TestClient
from litestar.types import ASGIApp, HTTPDisconnectEvent, Message, Receive, Scope, Send

from www.config import Config, Environment
from www.middleware import (
    CLOUD_TRACE_LOG_KEY,
    SiteMiddleware,
    analytics_dimension,
    analytics_path,
    is_bot,
    referer_host,
    request_trace_id,
)
from www.ranges import etag_matches, strong_etag_matches

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"


@dataclass
class RecordingLogger:
    records: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def info(self, event: str, **values: Any) -> None:
        self.records.append((event, values))

    def error(self, event: str, **values: Any) -> None:
        self.records.append((event, values))


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
    assert referer_host("not a URL") == ""
    assert is_bot("Mozilla compatible; LinkedInBot")
    assert not is_bot("Mozilla/5.0 Firefox")
    for automated in (
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/140.0 Safari/537.36",
        "curl/8.9.1",
        "python-requests/2.32.3",
        "Python-urllib/3.14",
        "Go-http-client/2.0",
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
    scope = cast(
        Scope,
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/boom",
            "raw_path": b"/boom",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver.local", 443),
            "state": {},
        },
    )

    async def receive() -> HTTPDisconnectEvent:
        return {"type": "http.disconnect"}

    async def send(_message: Message) -> None:
        return None

    with pytest.raises(RuntimeError, match="request failed"):
        await middleware(scope, receive, send)

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
    scope = cast(
        Scope,
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/logo.png",
            "raw_path": b"/logo.png",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver.local", 443),
            "state": {},
            "extensions": {"http.response.pathsend": {}},
        },
    )

    async def receive() -> HTTPDisconnectEvent:
        return {"type": "http.disconnect"}

    async def send(_message: Message) -> None:
        return None

    await middleware(scope, receive, send)

    assert sent == ["1 records"]
    assert [event for event, _ in logger.records] == ["http request processed"]
    assert logger.records[0][1]["size_bytes"] == 2048
