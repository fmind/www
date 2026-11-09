"""Development server binds loopback and reloads only on startup inputs."""

import shlex
import tomllib
from pathlib import Path

import pytest
from granian.cli import cli


def _server_arguments() -> list[str]:
    config = tomllib.loads(Path("mise.toml").read_text())
    command = shlex.split(config["tasks"]["watch:server"]["run"])
    return command[command.index("granian") + 1 :]


@pytest.mark.parametrize(("override", "host"), [(None, "127.0.0.1"), ("192.0.2.10", "192.0.2.10")])
def test_server_binds_loopback_unless_explicitly_overridden(
    monkeypatch: pytest.MonkeyPatch, override: str | None, host: str
) -> None:
    # Development serves drafts, so only an explicit GRANIAN_HOST may expose it beyond localhost.
    if override is None:
        monkeypatch.delenv("GRANIAN_HOST", raising=False)
    else:
        monkeypatch.setenv("GRANIAN_HOST", override)

    with cli.make_context("granian", _server_arguments(), auto_envvar_prefix="GRANIAN") as context:
        assert context.params["host"] == host


def test_server_reloads_only_startup_inputs() -> None:
    # Browser artifacts under tmp/ and test or build output must not restart workers.
    with cli.make_context("granian", _server_arguments()) as context:
        assert context.params["reload_paths"] == (Path("src"), Path("content"), Path("static"))
