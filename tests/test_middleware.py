"""HTTP boundary and privacy tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

import pytest
from litestar import Litestar, Request, get
from litestar.middleware import DefineMiddleware
from litestar.response import Response
from litestar.testing import TestClient
from litestar.types import ASGIApp, HTTPDisconnectEvent, Message, Receive, Scope, Send

from www.config import Config, Environment
from www.middleware import (
    SiteMiddleware,
    analytics_dimension,
    analytics_path,
    etag_matches,
    is_bot,
    referer_host,
    strong_etag_matches,
)


@dataclass
class RecordingLogger:
    records: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def info(self, event: str, **values: Any) -> None:
        self.records.append((event, values))

    def error(self, event: str, **values: Any) -> None:
        self.records.append((event, values))


def client(environment: Environment = Environment.DEVELOPMENT) -> tuple[TestClient[Any], RecordingLogger]:
    logger = RecordingLogger()

    @get("/", sync_to_thread=False)
    def home(request: Request[Any, Any, Any]) -> Response[str]:
        nonce = request.scope["state"]["csp_nonce"]
        return Response(f'<html><script nonce="{nonce}"></script></html>', media_type="text/html")

    app = Litestar(
        route_handlers=[home],
        middleware=[DefineMiddleware(SiteMiddleware, config=Config(environment=environment), logger=logger)],
        openapi_config=None,
    )
    base_url = "http://fmind.dev" if environment is Environment.PRODUCTION else "http://testserver.local"
    return TestClient(app, base_url=base_url), logger


def test_security_headers_authorize_the_request_nonce() -> None:
    with client()[0] as test_client:
        response = test_client.get("/")

    nonce = response.text.split('nonce="', 1)[1].split('"', 1)[0]
    assert f"script-src 'self' 'nonce-{nonce}'" in response.headers["content-security-policy"]
    assert f"style-src 'self' 'nonce-{nonce}'" in response.headers["content-security-policy"]
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
    assert response.headers["strict-transport-security"].startswith("max-age=63072000")
    assert response.headers["vary"] == "Accept-Encoding"
    assert logger.records == []


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


def test_etag_matching_accepts_weak_and_list_validators() -> None:
    assert etag_matches('"old", W/"abc123"', '"abc123"')
    assert etag_matches("*", '"abc123"')
    assert not etag_matches('"other"', '"abc123"')
    assert strong_etag_matches('"old", "abc123"', '"abc123"')
    assert strong_etag_matches("*", '"abc123"')
    assert not strong_etag_matches('W/"abc123"', '"abc123"')
    assert not strong_etag_matches('*, "abc123"', '"abc123"')


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
