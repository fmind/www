"""Docker-free contract tests for the production image smoke harness."""

from __future__ import annotations

import json
import signal
from collections.abc import Sequence
from typing import Any

import pytest

from www.image_runtime import (
    CommandResult,
    HTTPResponse,
    MCPProbeRequest,
    SmokeError,
    TerminationRequestedError,
    _assert_http_contracts,
    _probe_modern_mcp,
    assert_runtime_read_only,
    container_guard,
    exporter_environment_names,
    parse_configured_user,
    parse_loaded_reference,
    parse_published_port,
    wait_for_health,
)

_MCP_PROTOCOL_VERSION = "2026-07-28"
_MCP_PROTOCOL_VERSION_META_KEY = "io.modelcontextprotocol/protocolVersion"
_MCP_CLIENT_INFO_META_KEY = "io.modelcontextprotocol/clientInfo"
_MCP_CLIENT_CAPABILITIES_META_KEY = "io.modelcontextprotocol/clientCapabilities"


def _mcp_result(request_id: int, result: dict[str, object]) -> bytes:
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}).encode()


def _mcp_results() -> dict[str, dict[str, object]]:
    return {
        "server/discover": {
            "supportedVersions": [_MCP_PROTOCOL_VERSION],
            "capabilities": {
                "prompts": {"listChanged": True},
                "resources": {"listChanged": True, "subscribe": True},
                "tools": {"listChanged": True},
            },
            "_meta": {
                "io.modelcontextprotocol/serverInfo": {
                    "name": "www",
                    "version": "v1.3.1",
                },
            },
        },
        "tools/list": {
            "tools": [
                {"name": "get_profile", "inputSchema": {"type": "object"}},
                {"name": "search_articles", "inputSchema": {"type": "object"}},
            ],
        },
        "resources/list": {
            "resources": [{"name": "profile", "uri": "portfolio://profile.json"}],
        },
        "prompts/list": {
            "prompts": [{"name": "assess_fit"}, {"name": "brief_me"}],
        },
        "tools/call": {
            "content": [{"type": "text", "text": "Found one article."}],
            "structuredContent": {
                "query": "kubeflow",
                "articles": [{"slug": "how-to-install-kubeflow-on-apple-silicon"}],
                "total": 3,
            },
            "isError": False,
            "resultType": "complete",
        },
        "resources/read": {
            "contents": [
                {
                    "uri": "portfolio://profile.json",
                    "mimeType": "application/json",
                    "text": json.dumps({"metadata": {"alternate_name": "Fmind"}}),
                }
            ],
            "resultType": "complete",
        },
        "prompts/get": {
            "description": "A structured, evidence-based fit assessment using the portfolio tools.",
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": "Assess this brief against Fmind's portfolio: Secure an enterprise agent platform",
                    },
                }
            ],
            "resultType": "complete",
        },
    }


class RecordingRunner:
    """Record commands without requiring a Docker daemon."""

    def __init__(self, results: Sequence[CommandResult] = ()) -> None:
        self.results = list(results)
        self.commands: list[tuple[str, ...]] = []

    def run(self, arguments: Sequence[str], *, timeout: float, check: bool = True) -> CommandResult:
        del timeout, check
        self.commands.append(tuple(arguments))
        return self.results.pop(0) if self.results else CommandResult(returncode=0, output="")


def test_parses_one_loaded_image_reference() -> None:
    assert parse_loaded_reference("Loaded image: www:local\n") == "www:local"
    digest = "sha256:" + ("a" * 64)
    assert parse_loaded_reference(f"Loaded image ID: {digest}\n") == digest

    with pytest.raises(SmokeError, match="did not report"):
        parse_loaded_reference("loading complete\n")
    with pytest.raises(SmokeError, match="multiple image references"):
        parse_loaded_reference("Loaded image: one:local\nLoaded image: two:local\n")


@pytest.mark.parametrize("value", ["0.0.0.0:49152", "127.0.0.1:0", "127.0.0.1:65536", "not-a-port"])
def test_published_port_must_be_one_loopback_tcp_port(value: str) -> None:
    with pytest.raises(SmokeError, match="published port"):
        parse_published_port(value)


def test_parses_loopback_port_and_exact_numeric_runtime_user() -> None:
    assert parse_published_port("127.0.0.1:49152\n") == 49152
    assert parse_configured_user(json.dumps("10001:10001")) == (10001, 10001)

    for value in ("", "root", "0:0", "10000:10001", "10001:root"):
        with pytest.raises(SmokeError, match="10001:10001"):
            parse_configured_user(json.dumps(value))


def test_clears_every_exporter_variable_declared_by_the_image() -> None:
    image_environment = json.dumps(
        [
            "PATH=/app/.venv/bin:/usr/bin",
            "OTEL_EXPORTER_OTLP_ENDPOINT=https://collector.example",
            "OTEL_EXPORTER_OTLP_HEADERS=authorization=secret",
        ]
    )

    assert exporter_environment_names(image_environment) == (
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    )


def test_http_contract_probe_uses_modern_mcp_discovery_and_lists_primitives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp_results = _mcp_results()
    mcp_methods: list[str] = []
    expected_parameters = {
        "server/discover": {},
        "tools/list": {},
        "resources/list": {},
        "prompts/list": {},
        "tools/call": {"name": "search_articles", "arguments": {"query": "kubeflow", "limit": 1}},
        "resources/read": {"uri": "portfolio://profile.json"},
        "prompts/get": {
            "name": "assess_fit",
            "arguments": {"brief": "Secure an enterprise agent platform"},
        },
    }
    expected_names = {
        "tools/call": "search_articles",
        "resources/read": "portfolio://profile.json",
        "prompts/get": "assess_fit",
    }

    def request(
        port: int,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> HTTPResponse:
        assert port == 49152
        if path == "/":
            assert method == "GET"
            return HTTPResponse(
                200,
                {"content-type": "text/html; charset=utf-8"},
                "<title>Médéric Hurier (Fmind)".encode(),
            )
        if path == "/static/dist/styles.css":
            assert method == "GET"
            return HTTPResponse(200, {"content-type": "text/css; charset=utf-8"}, b"/*! tailwindcss v4")

        assert path == "/mcp"
        assert method == "POST"
        assert body is not None
        payload = json.loads(body)
        mcp_method = payload["method"]
        mcp_methods.append(mcp_method)
        assert payload["jsonrpc"] == "2.0"
        assert payload["id"] == len(mcp_methods)
        assert payload["params"]["_meta"] == {
            _MCP_PROTOCOL_VERSION_META_KEY: _MCP_PROTOCOL_VERSION,
            _MCP_CLIENT_INFO_META_KEY: {"name": "image-smoke", "version": "1.0"},
            _MCP_CLIENT_CAPABILITIES_META_KEY: {},
        }
        request_parameters = dict(payload["params"])
        del request_parameters["_meta"]
        assert request_parameters == expected_parameters[mcp_method]
        expected_headers = {
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
            "mcp-method": mcp_method,
            "mcp-protocol-version": _MCP_PROTOCOL_VERSION,
        }
        if name := expected_names.get(mcp_method):
            expected_headers["mcp-name"] = name
        assert headers == expected_headers
        return HTTPResponse(
            200, {"content-type": "application/json"}, _mcp_result(payload["id"], mcp_results[mcp_method])
        )

    monkeypatch.setattr("www.image_runtime._request", request)

    _assert_http_contracts(49152)

    assert mcp_methods == [
        "server/discover",
        "tools/list",
        "resources/list",
        "prompts/list",
        "tools/call",
        "resources/read",
        "prompts/get",
    ]


@pytest.mark.parametrize(
    ("rejected_method", "rejected_result", "message"),
    [
        (
            "server/discover",
            {
                **_mcp_results()["server/discover"],
                "supportedVersions": ["2025-11-25"],
            },
            "did not advertise 2026-07-28",
        ),
        (
            "server/discover",
            {
                **_mcp_results()["server/discover"],
                "capabilities": {"resources": {}, "tools": {}},
            },
            "did not advertise tools, resources, and prompts",
        ),
        (
            "tools/list",
            {"tools": [{"name": "get_profile", "inputSchema": {"type": "object"}}]},
            "omitted representative portfolio tools",
        ),
        (
            "resources/list",
            {"resources": []},
            "omitted the portfolio resource",
        ),
        (
            "prompts/list",
            {"prompts": [{"name": "assess_fit"}]},
            "omitted representative portfolio prompts",
        ),
        (
            "tools/call",
            {
                **_mcp_results()["tools/call"],
                "structuredContent": {"query": "different", "articles": [], "total": 0},
            },
            "did not return the normalized query",
        ),
        (
            "resources/read",
            {"contents": [], "resultType": "complete"},
            "did not return the portfolio profile",
        ),
        (
            "prompts/get",
            {"description": "Ungrounded", "messages": [], "resultType": "complete"},
            "did not return a grounded fit assessment",
        ),
    ],
)
def test_modern_mcp_probe_fails_closed_on_incomplete_results(
    monkeypatch: pytest.MonkeyPatch,
    rejected_method: str,
    rejected_result: dict[str, object],
    message: str,
) -> None:
    def send_request(port: int, request: MCPProbeRequest, request_id: int) -> dict[str, Any]:
        del port, request_id
        if request.method == rejected_method:
            return rejected_result
        return _mcp_results()[request.method]

    monkeypatch.setattr("www.image_runtime._send_modern_mcp_request", send_request)

    with pytest.raises(SmokeError, match=message):
        _probe_modern_mcp(49152)


def test_http_contract_probe_matches_the_real_application_wire(monkeypatch: pytest.MonkeyPatch) -> None:
    from litestar.testing import TestClient

    from www.app import create_app

    # The MCP SDK deliberately makes each transport manager single-use. Build
    # an isolated application just as a fresh server process does.
    with TestClient(create_app()) as client:

        def request(
            port: int,
            method: str,
            path: str,
            *,
            body: bytes | None = None,
            headers: dict[str, str] | None = None,
        ) -> HTTPResponse:
            del port
            response = client.request(method, path, content=body, headers=headers)
            return HTTPResponse(response.status_code, dict(response.headers), response.content)

        monkeypatch.setattr("www.image_runtime._request", request)
        _assert_http_contracts(49152)


def test_readiness_timeout_is_bounded_without_sleeping() -> None:
    current_time = 0.0
    attempts = 0

    def clock() -> float:
        return current_time

    def sleep(duration: float) -> None:
        nonlocal current_time
        current_time += duration

    def unavailable() -> None:
        nonlocal attempts
        attempts += 1
        raise OSError("connection refused")

    with pytest.raises(SmokeError, match="did not become healthy within 2 seconds"):
        wait_for_health(
            unavailable,
            lambda: True,
            timeout_seconds=2,
            interval_seconds=0.5,
            monotonic=clock,
            sleep=sleep,
        )

    assert attempts == 5


def test_readiness_fails_early_when_container_exits() -> None:
    with pytest.raises(SmokeError, match="exited before becoming healthy"):
        wait_for_health(
            lambda: (_ for _ in ()).throw(OSError("connection refused")),
            lambda: False,
            timeout_seconds=120,
            interval_seconds=1,
            monotonic=lambda: 0,
            sleep=lambda _: None,
        )


def test_container_cleanup_runs_after_success_failure_and_signal() -> None:
    removal = ("docker", "container", "rm", "--force", "--volumes", "www-image-smoke-test")

    success_runner = RecordingRunner()
    with container_guard(success_runner, "www-image-smoke-test"):
        pass
    assert success_runner.commands == [removal]

    failure_runner = RecordingRunner()
    with pytest.raises(RuntimeError, match="probe failed"), container_guard(failure_runner, "www-image-smoke-test"):
        raise RuntimeError("probe failed")
    assert failure_runner.commands == [removal]

    signal_runner = RecordingRunner()
    with pytest.raises(TerminationRequestedError), container_guard(signal_runner, "www-image-smoke-test"):
        raise TerminationRequestedError(signal.SIGTERM)
    assert signal_runner.commands == [removal]


def test_cleanup_failure_fails_an_otherwise_successful_gate() -> None:
    runner = RecordingRunner([CommandResult(returncode=1, output="daemon unavailable")])

    with (
        pytest.raises(SmokeError, match="could not remove smoke container"),
        container_guard(runner, "www-image-smoke-test"),
    ):
        pass


def test_runtime_write_probe_uses_fixed_docker_arguments_and_fails_closed() -> None:
    success_runner = RecordingRunner([CommandResult(returncode=0, output="")])

    assert_runtime_read_only(success_runner, "www-image-smoke-test")

    arguments = success_runner.commands[0]
    assert arguments[:6] == (
        "docker",
        "container",
        "exec",
        "www-image-smoke-test",
        "python",
        "-c",
    )
    assert "/app/.venv/lib/python3.14/site-packages/www/app.py" in arguments[6]
    assert "/app/content/articles" in arguments[6]
    assert "/app/static/dist/styles.css" in arguments[6]

    writable_runner = RecordingRunner([CommandResult(returncode=3, output="")])
    with pytest.raises(SmokeError, match="runtime user can write"):
        assert_runtime_read_only(writable_runner, "www-image-smoke-test")

    invalid_runner = RecordingRunner([CommandResult(returncode=2, output="")])
    with pytest.raises(SmokeError, match="write-protection probe failed"):
        assert_runtime_read_only(invalid_runner, "www-image-smoke-test")

    privileged_runner = RecordingRunner([CommandResult(returncode=4, output="")])
    with pytest.raises(SmokeError, match="setuid or setgid"):
        assert_runtime_read_only(privileged_runner, "www-image-smoke-test")
