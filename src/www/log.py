"""Structured process logging with stable fields for Cloud Logging."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, TextIO

import structlog
from structlog.stdlib import BoundLogger
from structlog.types import EventDict, WrappedLogger

from www.config import Config, Environment


class CloudJSONFormatter(logging.Formatter):
    """Render standard-library records as one Cloud Logging JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        """Preserve the useful process fields without serializing internals."""
        timestamp = (
            datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )
        payload = {
            "time": timestamp,
            "severity": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


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
            # SiteMiddleware owns one canonical access record per request.
            "discard": {"class": "logging.NullHandler"},
        },
        "loggers": {
            "_granian": {"handlers": ["process"], "level": "INFO", "propagate": False},
            "granian.access": {"handlers": ["discard"], "level": "CRITICAL", "propagate": False},
            # Keep protocol failures while dropping per-process lifecycle chatter.
            "mcp": {"handlers": ["process"], "level": "WARNING", "propagate": False},
        },
        "root": {"handlers": ["process"], "level": "WARNING"},
    }


def _cloud_severity(_: WrappedLogger, __: str, event: EventDict) -> EventDict:
    """Promote structlog's level to Cloud Logging's recognized severity field."""
    level = event.pop("level", "info")
    event["severity"] = str(level).upper()
    return event


def configure_logging(config: Config, stream: TextIO = sys.stderr) -> BoundLogger:
    """Configure one environment-appropriate structured logger."""
    renderer: structlog.types.Processor
    platform_processors: tuple[structlog.types.Processor, ...]
    if config.environment is Environment.PRODUCTION:
        renderer = structlog.processors.JSONRenderer()
        # `msg` is the deployed BigQuery sink contract. `severity` is a
        # Cloud Logging special field, so ERROR records reach the alert policy.
        platform_processors = (
            _cloud_severity,
            structlog.processors.EventRenamer("msg"),
        )
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=stream.isatty())
        platform_processors = ()

    structlog.configure(
        processors=(
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="time"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            *platform_processors,
            renderer,
        ),
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=stream),
        cache_logger_on_first_use=False,
    )
    return structlog.get_logger("www")
