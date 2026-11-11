"""Release metadata stays synchronized across every published surface."""

import json
import re
import tomllib
from pathlib import Path
from typing import Any


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def test_release_versions_are_synchronized() -> None:
    from importlib.metadata import version

    repository = Path(__file__).resolve().parents[1]
    project = _load_toml(repository / "pyproject.toml")
    server = json.loads((repository / "server.json").read_text(encoding="utf-8"))

    # uv.lock needs no assertion here: every `uv run --locked` fails when it trails pyproject.toml.
    assert server["version"] == project["project"]["version"] == version("www")
    assert server["icons"] == [
        {
            "src": "https://www.fmind.dev/static/img/favicons/icon-192.png",
            "mimeType": "image/png",
            "sizes": ["192x192"],
        }
    ]


def test_python_runtime_pins_are_consistent() -> None:
    repository = Path(__file__).resolve().parents[1]
    mise = _load_toml(repository / "mise.toml")
    version = mise["tools"]["python"]
    assert (repository / ".python-version").read_text().strip() == version
    dockerfile = (repository / "Dockerfile").read_text()
    # One pinned base stage feeds both the build and the runtime stage.
    assert re.findall(r"^FROM python:([^@]+)@sha256:[0-9a-f]{64} AS (\w+)$", dockerfile, re.MULTILINE) == [
        (f"{version}-slim", "base")
    ]
    assert re.findall(r"^FROM (\S+) AS (?:build|runner)$", dockerfile, re.MULTILINE) == ["base", "base"]


def test_image_build_tool_pins_match_mise() -> None:
    repository = Path(__file__).resolve().parents[1]
    tools = _load_toml(repository / "mise.toml")["tools"]
    dockerfile = (repository / "Dockerfile").read_text()
    build_system = _load_toml(repository / "pyproject.toml")["build-system"]

    # The image builds CSS and the locked Python environment with its own copies of these tools.
    uv_version = tools["aqua:astral-sh/uv"]
    assert re.findall(r"ghcr\.io/astral-sh/uv:([^@]+)@sha256:", dockerfile) == [uv_version]
    assert build_system["requires"] == [f"uv_build=={uv_version}"]
    tailwind_version = tools["github:dobicinaitis/tailwind-cli-extra"]
    assert re.findall(r"tailwind-cli-extra/releases/download/v([^/]+)/", dockerfile) == [tailwind_version] * 2


def test_image_builders_pin_one_buildkit_digest() -> None:
    repository = Path(__file__).resolve().parents[1]
    workflow = (repository / ".github" / "workflows" / "deploy.yml").read_text()
    dockerfile = (repository / "Dockerfile").read_text()

    # Dependabot does not bump driver-opts, so the verify and deploy builders can drift apart.
    setup_steps = re.findall(r"uses: docker/setup-buildx-action@", workflow)
    builders = re.findall(r"driver-opts: image=(moby/buildkit:v[0-9.]+@sha256:[0-9a-f]{64})$", workflow, re.MULTILINE)
    assert len(setup_steps) == 2
    assert len(builders) == len(setup_steps)
    assert len(set(builders)) == 1
    # `sbom: true` would run the mutable buildkit-syft-scanner:stable-1 image inside the deploy build.
    sbom_inputs = re.findall(r"^\s+sbom: (.+)$", workflow, re.MULTILINE)
    assert sbom_inputs
    assert all(
        re.fullmatch(r"generator=docker/buildkit-syft-scanner:[0-9.]+@sha256:[0-9a-f]{64}", value)
        for value in sbom_inputs
    )
    # The pinned builder's built-in frontend parses the Dockerfile; a `# syntax=` tag would pull a floating one.
    assert not re.search(r"^#\s*syntax=", dockerfile, re.MULTILINE | re.IGNORECASE)


def test_lighthouse_and_gcloud_pins_stay_synchronized() -> None:
    repository = Path(__file__).resolve().parents[1]
    tools = _load_toml(repository / "mise.toml")["tools"]
    lighthouse_script = (repository / "scripts" / "lighthouse.mjs").read_text(encoding="utf-8")
    assert re.findall(r'^const LIGHTHOUSE_VERSION = "([^"]+)";$', lighthouse_script, re.MULTILINE) == [
        tools["npm:lighthouse"]
    ]

    workflows = sorted((repository / ".github" / "workflows").glob("*.yml"))
    gcloud_versions: list[str] = []
    for workflow in workflows:
        text = workflow.read_text(encoding="utf-8")
        gcloud_steps = re.findall(r"uses: google-github-actions/setup-gcloud@", text)
        versions = re.findall(
            r"uses: google-github-actions/setup-gcloud@[^\n]+\n\s+with:\n\s+version:\s*([0-9.]+)",
            text,
        )
        assert len(versions) == len(gcloud_steps), workflow.name
        gcloud_versions.extend(versions)
    assert gcloud_versions
    assert len(set(gcloud_versions)) == 1
