"""Docker-free contract tests for the production image smoke harness."""

from __future__ import annotations

import json
import signal
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from scripts.image_smoke import (
    CommandResult,
    HTTPResponse,
    SmokeError,
    TerminationRequestedError,
    _assert_http_contracts,
    _probe_modern_mcp,
    _request,
    assert_runtime_read_only,
    container_guard,
    exporter_environment_names,
    main,
    parse_configured_user,
    parse_loaded_reference,
    parse_published_port,
    resolve_image_id,
    validate_image_reference,
    wait_for_health,
)

_MCP_PROTOCOL_VERSION = "2026-07-28"
_MCP_PROTOCOL_VERSION_META_KEY = "io.modelcontextprotocol/protocolVersion"
_MCP_CLIENT_INFO_META_KEY = "io.modelcontextprotocol/clientInfo"
_MCP_CLIENT_CAPABILITIES_META_KEY = "io.modelcontextprotocol/clientCapabilities"


def _mcp_result(request_id: int, result: dict[str, object]) -> bytes:
    result = {"cacheScope": "public", "ttlMs": 3600000, "resultType": "complete", **result}
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
        assert headers is not None
        for name, value in expected_headers.items():
            assert headers[name].replace(" ", "") == value.replace(" ", "")
        return HTTPResponse(
            200, {"content-type": "application/json"}, _mcp_result(payload["id"], mcp_results[mcp_method])
        )

    monkeypatch.setattr("scripts.image_smoke._request", request)

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
    def request(
        port: int, method: str, path: str, *, body: bytes | None = None, headers: dict[str, str] | None = None
    ) -> HTTPResponse:
        del port, method, path, headers
        assert body is not None
        payload = json.loads(body)
        result = rejected_result if payload["method"] == rejected_method else _mcp_results()[payload["method"]]
        return HTTPResponse(200, {"content-type": "application/json"}, _mcp_result(payload["id"], result))

    monkeypatch.setattr("scripts.image_smoke._request", request)

    with pytest.raises(SmokeError, match="MCP qualification failed") as caught:
        _probe_modern_mcp(49152)
    # The SDK may reject incompatible discovery before application checks run.
    if rejected_method != "server/discover" or "supportedVersions" not in rejected_result:
        assert message in "".join(traceback.format_exception(caught.value))


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

        monkeypatch.setattr("scripts.image_smoke._request", request)
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


def test_validate_image_reference_accepts_valid_refs() -> None:
    valid_digest_ref = f"europe-west1-docker.pkg.dev/www-fmind-dev/app/www-fmind-dev@sha256:{'a' * 64}"
    validate_image_reference(valid_digest_ref)
    validate_image_reference("www:local")
    validate_image_reference("ghcr.io/owner/repo:v1.0.0")


@pytest.mark.parametrize(
    ("invalid_ref", "error_match"),
    [
        ("", "invalid image reference"),
        ("   ", "invalid image reference"),
        ("image with spaces", "invalid image reference"),
        ("image;rm-rf", "invalid characters"),
        ("image$bad", "invalid characters"),
        ("repo@sha256:123", "invalid image digest"),
        ("repo@sha256:" + ("g" * 64), "invalid image digest"),
        ("repo@md5:123", "invalid image digest"),
    ],
)
def test_validate_image_reference_rejects_malformed_refs(invalid_ref: str, error_match: str) -> None:
    with pytest.raises(SmokeError, match=error_match):
        validate_image_reference(invalid_ref)


def test_resolve_image_id_loads_existing_archive(tmp_path: Path) -> None:
    archive = tmp_path / "test-image.tar"
    archive.write_bytes(b"dummy archive")
    digest = "sha256:" + ("b" * 64)

    runner = RecordingRunner(
        [
            CommandResult(returncode=0, output="Loaded image: www:test\n"),
            CommandResult(returncode=0, output=f"{digest}\n"),
        ]
    )

    image_id = resolve_image_id(runner, archive)
    assert image_id == digest
    assert runner.commands == [
        ("docker", "image", "load", "--input", str(archive)),
        ("docker", "image", "inspect", "--format", "{{.Id}}", "www:test"),
    ]


def test_resolve_image_id_fails_when_archive_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing.tar"
    runner = RecordingRunner()
    with pytest.raises(SmokeError, match="is missing"):
        resolve_image_id(runner, missing)


def test_resolve_image_id_pulls_and_inspects_remote_reference() -> None:
    target = f"europe-west1-docker.pkg.dev/www-fmind-dev/app/www-fmind-dev@sha256:{'c' * 64}"
    digest = "sha256:" + ("c" * 64)

    runner = RecordingRunner(
        [
            CommandResult(returncode=0, output="pulled\n"),
            CommandResult(returncode=0, output=f"{digest}\n"),
        ]
    )

    image_id = resolve_image_id(runner, target)
    assert image_id == digest
    assert runner.commands == [
        ("docker", "pull", "--platform", "linux/amd64", target),
        ("docker", "image", "inspect", "--format", "{{.Id}}", target),
    ]


def test_main_rejects_extra_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["one", "two"])
    assert exit_code == 2
    assert "usage:" in capsys.readouterr().err


def test_main_passes_target_and_handles_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recorded_targets: list[str | None] = []

    def fake_smoke(target: str | None = None, *, runner: Any = None) -> None:
        del runner
        recorded_targets.append(target)

    monkeypatch.setattr("scripts.image_smoke.smoke_image", fake_smoke)

    assert main([]) == 0
    assert recorded_targets == [None]

    assert main(["my-image:latest"]) == 0
    assert recorded_targets == [None, "my-image:latest"]

    def failing_smoke(target: str | None = None, *, runner: Any = None) -> None:
        del target, runner
        raise SmokeError("broken image")

    monkeypatch.setattr("scripts.image_smoke.smoke_image", failing_smoke)
    assert main([]) == 1
    assert "image smoke failed: broken image" in capsys.readouterr().err


@pytest.mark.parametrize("failure", ["oversized", "timeout"])
def test_http_boundary_caps_reads_sanitizes_errors_and_closes_connection(
    failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    class FakeResponse:
        def read(self, amount: int) -> bytes:
            assert amount == 2 * 1024 * 1024 + 1
            return b"x" * amount

    class FakeConnection:
        def __init__(self, host: str, port: int, *, timeout: float) -> None:
            assert (host, port, timeout) == ("127.0.0.1", 49152, 5)

        def request(self, method: str, path: str, *, body: bytes | None, headers: dict[str, str]) -> None:
            del method, path, body, headers

        def getresponse(self) -> FakeResponse:
            if failure == "timeout":
                raise TimeoutError("untrusted diagnostic payload")
            return FakeResponse()

        def close(self) -> None:
            events.append("closed")

    monkeypatch.setattr("scripts.image_smoke.http.client.HTTPConnection", FakeConnection)
    expected = "response exceeded 2097152 bytes" if failure == "oversized" else r"request failed \(TimeoutError\)"
    with pytest.raises(SmokeError, match=expected) as caught:
        _request(49152, "POST", "/mcp")
    assert "untrusted diagnostic" not in str(caught.value)
    assert events == ["closed"]


def test_mcp_deadline_returns_before_a_stalled_http_read_finishes(monkeypatch: pytest.MonkeyPatch) -> None:
    from threading import Event

    import anyio

    entered = Event()
    release = Event()
    finished = Event()
    deadline = anyio.fail_after

    def stalled_request(*_arguments: object, **_keywords: object) -> HTTPResponse:
        entered.set()
        try:
            release.wait(timeout=3)
            raise TimeoutError("stalled peer")
        finally:
            finished.set()

    monkeypatch.setattr("scripts.image_smoke._request", stalled_request)
    monkeypatch.setattr(anyio, "fail_after", lambda _seconds: deadline(0.5))
    try:
        with pytest.raises(SmokeError, match="MCP qualification failed"):
            _probe_modern_mcp(49152)
        assert entered.is_set()
        # Container cleanup must be able to run while the peer is still stalled.
        assert not finished.is_set()
    finally:
        release.set()
        assert finished.wait(timeout=3)
