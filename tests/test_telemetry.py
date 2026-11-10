"""Tracing stays explicitly opt-in and bounded during shutdown."""

import logging
import os
import subprocess
import sys
from pathlib import Path
from threading import Event

import pytest

from www.telemetry import configure_telemetry, shutdown_telemetry


class RecordingProvider:
    def __init__(
        self,
        *,
        release: Event | None = None,
        flush_result: bool = True,
        flush_error: Exception | None = None,
        shutdown_error: Exception | None = None,
    ) -> None:
        self.flush_timeout_millis: int | None = None
        self.release = release
        self.flush_result = flush_result
        self.flush_error = flush_error
        self.shutdown_error = shutdown_error
        self.shutdown_called = Event()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        self.flush_timeout_millis = timeout_millis
        if self.release is not None:
            self.release.wait()
        if self.flush_error is not None:
            raise self.flush_error
        return self.flush_result

    def shutdown(self) -> None:
        self.shutdown_called.set()
        if self.shutdown_error is not None:
            raise self.shutdown_error


def test_telemetry_is_noop_without_endpoint() -> None:
    assert configure_telemetry({}) is None
    assert configure_telemetry({"OTEL_EXPORTER_OTLP_ENDPOINT": "   "}) is None
    assert (
        configure_telemetry(
            {
                "OTEL_SDK_DISABLED": "true",
                "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://127.0.0.1:4318/v1/traces",
            }
        )
        is None
    )


def test_telemetry_installs_an_otlp_provider_when_an_endpoint_opts_in(monkeypatch: pytest.MonkeyPatch) -> None:
    installed: list[object] = []
    endpoints: list[str | None] = []
    # Record instead of installing: the process-wide tracer provider can be set only once.
    monkeypatch.setattr("opentelemetry.trace.set_tracer_provider", installed.append)
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as RealExporter

    def recording_exporter(*, endpoint: str | None = None) -> RealExporter:
        endpoints.append(endpoint)
        return RealExporter(endpoint=endpoint)

    monkeypatch.setattr("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter", recording_exporter)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://ambient.invalid:4318/v1/traces")

    provider = configure_telemetry({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318/"})

    assert provider is not None
    try:
        assert installed == [provider]
        assert endpoints == ["http://127.0.0.1:4318/v1/traces"]
        assert provider.resource.attributes["service.name"] == "www"
    finally:
        assert shutdown_telemetry(provider)


def test_untraced_startup_skips_the_sdk_and_exporter_imports() -> None:
    # A fresh interpreter: other tests in this process import the SDK themselves.
    probe = (
        "import sys, www.app; "
        "print(sorted(m for m in sys.modules if m.startswith(('opentelemetry.sdk', 'opentelemetry.exporter'))))"
    )
    environment = {name: value for name, value in os.environ.items() if not name.startswith("OTEL_")}
    result = subprocess.run(  # noqa: S603 - fixed interpreter and probe
        [sys.executable, "-c", probe],
        cwd=Path(__file__).parents[1],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.stdout.splitlines()[-1] == "[]"


def test_telemetry_flushes_and_shuts_down_inside_the_deadline() -> None:
    provider = RecordingProvider()

    assert shutdown_telemetry(provider, timeout_seconds=0.1)
    assert provider.flush_timeout_millis == 100
    assert provider.shutdown_called.is_set()


def test_telemetry_shutdown_returns_when_the_exporter_stalls() -> None:
    release = Event()
    provider = RecordingProvider(release=release)

    try:
        assert not shutdown_telemetry(provider, timeout_seconds=0.01)
        assert provider.flush_timeout_millis == 10
        assert not provider.shutdown_called.is_set()
    finally:
        release.set()
        assert provider.shutdown_called.wait(0.5)


def test_telemetry_shutdown_reports_an_unsuccessful_flush() -> None:
    provider = RecordingProvider(flush_result=False)

    assert not shutdown_telemetry(provider, timeout_seconds=0.1)
    assert provider.shutdown_called.is_set()


@pytest.mark.parametrize(
    ("provider", "message"),
    [
        (RecordingProvider(flush_error=RuntimeError("flush failed")), "telemetry force flush failed"),
        (RecordingProvider(shutdown_error=RuntimeError("shutdown failed")), "telemetry provider shutdown failed"),
    ],
)
def test_telemetry_shutdown_contains_and_logs_provider_failures(
    caplog: pytest.LogCaptureFixture,
    provider: RecordingProvider,
    message: str,
) -> None:
    with caplog.at_level(logging.ERROR, logger="www.telemetry"):
        assert not shutdown_telemetry(provider, timeout_seconds=0.1)

    # A loaded runner may consume the deliberately tiny caller deadline before
    # the daemon gets scheduled; it must still continue the shutdown attempt.
    assert provider.shutdown_called.wait(0.5)
    assert message in caplog.messages
