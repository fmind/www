"""Structured process logging with stable fields for Cloud Logging (stdlib-only)."""

import json
import logging
import sys
import traceback
from datetime import UTC, datetime
from typing import Any, TextIO

from www.config import Config, Environment
from www.models import utc_stamp


def _utc_millis(timestamp: float | None = None) -> str:
    instant = datetime.now(UTC) if timestamp is None else datetime.fromtimestamp(timestamp, UTC)
    return instant.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class CloudJSONFormatter(logging.Formatter):
    """Render standard-library records as one Cloud Logging JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        """Preserve the useful process fields without serializing internals."""
        payload: dict[str, Any] = {
            "time": _utc_millis(record.created),
            "severity": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class StructuredLogger:
    """Lightweight structured logger emitting Cloud Logging JSON or dev key-value lines."""

    __slots__ = ("_json_mode", "_stream")

    def __init__(self, *, json_mode: bool, stream: TextIO) -> None:
        self._json_mode = json_mode
        self._stream = stream

    def debug(self, event: str, **values: Any) -> None:
        self._emit("DEBUG", event, values)

    def info(self, event: str, **values: Any) -> None:
        self._emit("INFO", event, values)

    def warning(self, event: str, **values: Any) -> None:
        self._emit("WARNING", event, values)

    def error(self, event: str, **values: Any) -> None:
        self._emit("ERROR", event, values)

    def _emit(self, severity: str, event: str, values: dict[str, Any]) -> None:
        exc_info = values.pop("exc_info", None)
        exception_text = _format_exc(exc_info) if exc_info else ""
        if self._json_mode:
            payload: dict[str, Any] = {
                "time": utc_stamp(datetime.now(UTC)),
                "severity": severity,
                "msg": event,
                **values,
            }
            if exception_text:
                payload["exception"] = exception_text
            line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        else:
            fields = " ".join(f"{key}={value}" for key, value in values.items())
            suffix = f" {fields}" if fields else ""
            line = f"[{severity.lower():<8}] {event}{suffix} time={_utc_millis()}"
            if exception_text:
                line = f"{line}\n{exception_text}"
        self._stream.write(f"{line}\n")
        self._stream.flush()


def _format_exc(exc_info: object) -> str:
    if isinstance(exc_info, BaseException):
        return "".join(traceback.format_exception(type(exc_info), exc_info, exc_info.__traceback__)).rstrip()
    if exc_info is True:
        return traceback.format_exc().rstrip()
    return str(exc_info)


def stdlib_logging_config(
    config: Config,
    stream: TextIO | str = "ext://sys.stderr",
) -> dict[str, Any]:
    """Build Granian's process-wide logging config for the selected mode."""
    formatter: dict[str, str]
    if config.environment is Environment.PRODUCTION:
        formatter = {"()": "www.log.CloudJSONFormatter"}
    else:
        formatter = {
            "()": "logging.Formatter",
            "format": "[%(levelname)s] %(name)s: %(message)s",
        }

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"process": formatter},
        "handlers": {
            "process": {
                "class": "logging.StreamHandler",
                "formatter": "process",
                "stream": stream,
            },
            # Cloud Run and SiteMiddleware own request logging.
            "discard": {"class": "logging.NullHandler"},
        },
        "loggers": {
            "_granian": {"handlers": ["process"], "level": "INFO", "propagate": False},
            "granian.access": {"handlers": ["discard"], "level": "CRITICAL", "propagate": False},
            # Keep protocol failures while dropping per-process lifecycle chatter and
            # raw untrusted Host/Origin scanner headers logged by TransportSecurityMiddleware.
            "mcp": {"handlers": ["process"], "level": "WARNING", "propagate": False},
            "mcp.server.transport_security": {"handlers": ["discard"], "level": "ERROR", "propagate": False},
        },
        "root": {"handlers": ["process"], "level": "WARNING"},
    }


def configure_logging(config: Config, stream: TextIO | None = None) -> StructuredLogger:
    """Configure one environment-appropriate structured logger."""
    output = sys.stderr if stream is None else stream
    return StructuredLogger(json_mode=config.environment is Environment.PRODUCTION, stream=output)
