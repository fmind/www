"""Logging mode tests."""

import json
import logging
from io import StringIO

from www.config import Config, Environment
from www.log import (
    CLOUD_TRACE_LOG_KEY,
    CURRENT_CLOUD_TRACE,
    CloudJSONFormatter,
    configure_logging,
    stdlib_logging_config,
)


def test_production_logging_is_cloud_parseable_json() -> None:
    output = StringIO()
    logger = configure_logging(Config(environment=Environment.PRODUCTION), output)

    logger.info("analytics_pageview", path="/", status=200)

    record = json.loads(output.getvalue())
    assert record["msg"] == "analytics_pageview"
    assert record["path"] == "/"
    assert record["status"] == 200
    assert record["severity"] == "INFO"
    assert record["time"].endswith("Z")
    assert "event" not in record
    assert "level" not in record


def test_development_logging_is_human_readable() -> None:
    output = StringIO()
    logger = configure_logging(Config(), output)

    logger.info("server listening", port=8080)
    logger.error("boom", exc_info=RuntimeError("failed"))

    rendered = output.getvalue()
    assert "server listening" in rendered
    assert "port=8080" in rendered
    assert "RuntimeError: failed" in rendered


def test_standard_library_production_logs_are_cloud_parseable() -> None:
    record = logging.LogRecord(
        name="_granian",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="worker %s stopped",
        args=(1,),
        exc_info=None,
    )

    payload = json.loads(CloudJSONFormatter().format(record))

    assert payload == {
        "time": payload["time"],
        "severity": "WARNING",
        "msg": "worker 1 stopped",
        "logger": "_granian",
    }
    assert payload["time"].endswith("Z")

    trace = "projects/www-fmind-dev/traces/0123456789abcdef0123456789abcdef"
    token = CURRENT_CLOUD_TRACE.set(trace)
    try:
        correlated = json.loads(CloudJSONFormatter().format(record))
    finally:
        CURRENT_CLOUD_TRACE.reset(token)
    assert correlated[CLOUD_TRACE_LOG_KEY] == trace
    assert CLOUD_TRACE_LOG_KEY not in json.loads(CloudJSONFormatter().format(record))


def test_granian_logging_config_uses_one_process_sink() -> None:
    output = StringIO()
    config = stdlib_logging_config(Config(environment=Environment.PRODUCTION), output)

    assert config["handlers"]["process"]["stream"] is output
    assert config["loggers"]["_granian"] == {
        "handlers": ["process"],
        "level": "INFO",
        "propagate": False,
    }
    assert config["loggers"]["mcp"]["level"] == "WARNING"
    assert config["loggers"]["mcp.server.transport_security"] == {
        "handlers": ["discard"],
        "level": "ERROR",
        "propagate": False,
    }
    assert config["loggers"]["granian.access"]["handlers"] == ["discard"]
    assert config["root"]["level"] == "WARNING"
