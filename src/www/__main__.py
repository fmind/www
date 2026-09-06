"""Run the production ASGI server."""

from __future__ import annotations

import sys
from typing import Any

from granian import Granian
from granian.constants import Interfaces
from granian.http import HTTP1Settings

from www.config import Config
from www.log import stdlib_logging_config

_HTTP1_HEADER_READ_TIMEOUT_MS = 5_000
_WORKER_KILL_TIMEOUT_SECONDS = 8


def build_server(config: Config, *, log_dictconfig: dict[str, Any] | None = None) -> Granian:
    """Construct the bounded Cloud Run server around validated settings."""
    return Granian(
        "www.app:app",
        address="0.0.0.0",  # noqa: S104 - Cloud Run requires a non-loopback listener.
        port=config.port,
        interface=Interfaces.ASGI,
        websockets=False,
        http1_settings=HTTP1Settings(header_read_timeout=_HTTP1_HEADER_READ_TIMEOUT_MS),
        # Cloud Run sends SIGKILL ten seconds after SIGTERM. Leave time for the
        # parent process itself to exit after a stuck worker is terminated.
        workers_kill_timeout=_WORKER_KILL_TIMEOUT_SECONDS,
        log_dictconfig=log_dictconfig,
    )


def main() -> None:
    """Validate configuration and serve the application."""
    try:
        config = Config.load()
    except ValueError as error:
        sys.stderr.write(f"load configuration: {error}\n")
        raise SystemExit(1) from error

    build_server(config, log_dictconfig=stdlib_logging_config(config)).serve()


if __name__ == "__main__":
    main()
