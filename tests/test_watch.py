"""Development reload scope excludes generated test and build output."""

import shlex
import tomllib
from contextlib import closing
from pathlib import Path

import pytest
from granian.cli import cli
from watchfiles import watch


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


@pytest.mark.parametrize(
    ("relative_path", "reloads"),
    [
        ("src/www/app.py", True),
        ("src/www/templates/pages/home.html", True),
        ("content/articles/example.md", True),
        ("static/dist/styles.css", True),
        ("static/img/example.webp", True),
        ("tmp/browser-results/.playwright-artifacts-0/traces/example.trace", False),
        ("tmp/browser-results/.playwright-artifacts-0/traces/screencast/page.jpeg", False),
        ("dist/www.whl", False),
        ("tests/example.py", False),
    ],
)
def test_server_reload_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative_path: str, reloads: bool
) -> None:
    arguments = _server_arguments()
    for directory in ("src", "content", "static"):
        (tmp_path / directory).mkdir()
    changed = tmp_path / relative_path
    changed.parent.mkdir(parents=True, exist_ok=True)
    changed.write_text("before")
    monkeypatch.chdir(tmp_path)

    with cli.make_context("granian", arguments) as context:
        paths = context.params["reload_paths"] or (tmp_path,)
        with closing(watch(*paths, step=10, rust_timeout=100, yield_on_timeout=True)) as changes:
            # Prime the OS watcher before changing a file, without a timing-based sleep.
            assert next(changes) == set()
            changed.write_text("after")
            observed = {Path(path) for _, path in next(changes)}
            assert (changed in observed) is reloads
