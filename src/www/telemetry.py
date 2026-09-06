"""Optional OTLP tracing configured only when a collector is present."""

from __future__ import annotations

import logging
import os
from threading import Event, Thread
from typing import Protocol

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SERVICE = "www"
TELEMETRY_SHUTDOWN_TIMEOUT_SECONDS = 2.0
logger = logging.getLogger(__name__)


class TelemetryProvider(Protocol):
    """The provider lifecycle surface used during process shutdown."""

    def force_flush(self, timeout_millis: int = 30_000) -> bool: ...

    def shutdown(self) -> None: ...


def configure_telemetry(environ: dict[str, str] | None = None) -> TracerProvider | None:
    """Install an OTLP provider when the standard endpoint variables opt in."""
    values = os.environ if environ is None else environ
    if not (values.get("OTEL_EXPORTER_OTLP_ENDPOINT") or values.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")):
        return None

    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: SERVICE}), shutdown_on_exit=False)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    return provider


def shutdown_telemetry(
    provider: TelemetryProvider,
    *,
    timeout_seconds: float = TELEMETRY_SHUTDOWN_TIMEOUT_SECONDS,
) -> bool:
    """Flush and close tracing without consuming Cloud Run's termination window."""
    finished = Event()
    succeeded = Event()

    def close() -> None:
        successful = True
        try:
            if not provider.force_flush(timeout_millis=max(1, round(timeout_seconds * 1_000))):
                successful = False
        except Exception:
            successful = False
            logger.exception("telemetry force flush failed")

        try:
            provider.shutdown()
        except Exception:
            successful = False
            logger.exception("telemetry provider shutdown failed")
        finally:
            if successful:
                succeeded.set()
            finished.set()

    # The SDK's batch force-flush does not reliably honor its timeout. A daemon
    # wrapper gives process shutdown a real upper bound even if an exporter stalls.
    Thread(target=close, name="otel-shutdown", daemon=True).start()
    return finished.wait(timeout_seconds) and succeeded.is_set()
