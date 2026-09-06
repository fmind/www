"""Logging mode tests."""

from __future__ import annotations

import json
import logging
from io import StringIO

from www.config import Config, Environment
from www.log import CloudJSONFormatter, configure_logging, stdlib_logging_config


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

    logger.debug("server listening", port=8080)

    assert "server listening" in output.getvalue()
    assert "port=8080" in output.getvalue()


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
    assert config["loggers"]["granian.access"]["handlers"] == ["discard"]
    assert config["root"]["level"] == "WARNING"
