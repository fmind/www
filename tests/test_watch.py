"""Development reload scope excludes generated test and build output."""

from __future__ import annotations

import shlex
import tomllib
from contextlib import closing
from pathlib import Path

import pytest
from granian.cli import cli
from watchfiles import watch


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
    config = tomllib.loads(Path("mise.toml").read_text())
    command = shlex.split(config["tasks"]["watch:server"]["run"])
    for directory in ("src", "content", "static"):
        (tmp_path / directory).mkdir()
    changed = tmp_path / relative_path
    changed.parent.mkdir(parents=True, exist_ok=True)
    changed.write_text("before")
    monkeypatch.chdir(tmp_path)

    with cli.make_context("granian", command[command.index("granian") + 1 :]) as context:
        paths = context.params["reload_paths"] or (tmp_path,)
        with closing(watch(*paths, step=50, rust_timeout=500, yield_on_timeout=True)) as changes:
            # Prime the OS watcher before changing a file, without a timing-based sleep.
            assert next(changes) == set()
            changed.write_text("after")
            observed = {Path(path) for _, path in next(changes)}
            assert (changed in observed) is reloads
