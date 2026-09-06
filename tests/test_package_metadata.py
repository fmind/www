"""Release metadata stays synchronized across every published surface."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def test_release_versions_are_synchronized() -> None:
    repository = Path(__file__).resolve().parents[1]
    project = _load_toml(repository / "pyproject.toml")
    lock = _load_toml(repository / "uv.lock")
    server = json.loads((repository / "server.json").read_text(encoding="utf-8"))

    project_version = project["project"]["version"]
    locked_project = [package for package in lock["package"] if package["name"] == "www"]

    assert len(locked_project) == 1
    assert locked_project[0]["version"] == project_version
    assert server["version"] == project_version
