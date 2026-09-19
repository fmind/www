"""Release acceptance rejects stale, partial, and unexpectedly costly rollouts."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import httpx2
import pytest

from scripts import verify_deployment
from scripts.verify_deployment import verify_service

IMAGE = "europe-west1-docker.pkg.dev/www-fmind-dev/app/www-fmind-dev@sha256:" + "a" * 64
COMMIT = "b" * 40
REVISION = "www-fmind-dev-00001-abc"


@pytest.fixture
def service() -> dict[str, Any]:
    return {
        "metadata": {"generation": 1, "annotations": {"run.googleapis.com/maxScale": "5"}},
        "spec": {
            "template": {
                "metadata": {
                    "labels": {"commit-sha": COMMIT},
                    "annotations": {
                        "autoscaling.knative.dev/maxScale": "5",
                        "autoscaling.knative.dev/minScale": "0",
                        "run.googleapis.com/cpu-throttling": "true",
                    },
                },
                "spec": {"containers": [{"image": IMAGE}]},
            },
        },
        "status": {
            "observedGeneration": 1,
            "conditions": [{"type": "Ready", "status": "True"}],
            "latestReadyRevisionName": REVISION,
            "latestCreatedRevisionName": REVISION,
            "traffic": [{"revisionName": REVISION, "percent": 100}],
        },
    }


def test_ready_release_accepts_zero_traffic_tags(service: dict[str, Any]) -> None:
    service["status"]["traffic"].append({"revisionName": "old-tag", "percent": 0})
    assert verify_service(service, IMAGE, COMMIT) == REVISION


@pytest.mark.parametrize("field", ["latestCreatedRevisionName", "latestReadyRevisionName"])
def test_pending_revision_fails(service: dict[str, Any], field: str) -> None:
    service["status"][field] = "pending-revision"
    with pytest.raises(ValueError, match="not ready"):
        verify_service(service, IMAGE, COMMIT)


def test_unready_service_fails(service: dict[str, Any]) -> None:
    service["status"]["conditions"][0]["status"] = "False"
    with pytest.raises(ValueError, match="not ready"):
        verify_service(service, IMAGE, COMMIT)


@pytest.mark.parametrize("old_percent", [0, 10])
def test_incomplete_or_split_traffic_fails(service: dict[str, Any], old_percent: int) -> None:
    service["status"]["traffic"] = [
        {"revisionName": REVISION, "percent": 90},
        {"revisionName": "old", "percent": old_percent},
    ]
    with pytest.raises(ValueError, match="all traffic"):
        verify_service(service, IMAGE, COMMIT)


@pytest.mark.parametrize(("image", "commit"), [(IMAGE + "f", COMMIT), (IMAGE, "c" * 40)])
def test_wrong_release_fails(service: dict[str, Any], image: str, commit: str) -> None:
    with pytest.raises(ValueError, match="differs"):
        verify_service(service, image, commit)


@pytest.mark.parametrize(
    ("scope", "key", "value"),
    [
        ("service", "run.googleapis.com/minScale", "1"),
        ("service", "run.googleapis.com/maxScale", "6"),
        ("revision", "autoscaling.knative.dev/minScale", "1"),
        ("revision", "autoscaling.knative.dev/maxScale", "6"),
        ("revision", "run.googleapis.com/cpu-throttling", "false"),
    ],
)
def test_capacity_drift_fails(service: dict[str, Any], scope: str, key: str, value: str) -> None:
    metadata = service["metadata"] if scope == "service" else service["spec"]["template"]["metadata"]
    metadata["annotations"][key] = value
    with pytest.raises(ValueError, match="scaling or CPU"):
        verify_service(service, IMAGE, COMMIT)


def test_stale_status_fails(service: dict[str, Any]) -> None:
    service["metadata"]["generation"] = 2
    with pytest.raises(ValueError, match="not been observed"):
        verify_service(service, IMAGE, COMMIT)


@pytest.mark.parametrize(("http_status", "health"), [(200, "ok"), (503, "error"), (200, "error")])
def test_release_command_checks_public_health(
    service: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    http_status: int,
    health: str,
) -> None:
    for key, value in {
        "REGION": "europe-west1",
        "PROJECT_ID": "www-fmind-dev",
        "REPOSITORY": "app",
        "SERVICE_NAME": "www-fmind-dev",
        "IMAGE_REF": IMAGE,
        "GITHUB_SHA": COMMIT,
    }.items():
        monkeypatch.setenv(key, value)
    commands: list[tuple[str, ...]] = []

    def describe(command: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, json.dumps(service), "")

    monkeypatch.setattr(verify_deployment.shutil, "which", lambda _: "/usr/bin/gcloud")
    monkeypatch.setattr(verify_deployment.subprocess, "run", describe)
    paths: list[str] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        paths.append(request.url.path)
        return httpx2.Response(http_status, json={"status": health})

    client = httpx2.Client(transport=httpx2.MockTransport(respond))
    monkeypatch.setattr(verify_deployment.httpx2, "Client", lambda **_kwargs: client)
    healthy = http_status == 200 and health == "ok"
    assert verify_deployment.main() == (0 if healthy else 1)
    assert len(commands) == 1
    assert commands[0][1:4] == ("run", "services", "describe")
    output = capsys.readouterr()
    if healthy:
        assert paths == ["/health", "/api/profile", "/.well-known/mcp/server-card.json"]
        assert "100% traffic" in output.out
        assert not output.err
    else:
        assert paths == ["/health"]
        assert ("HTTPStatusError" if http_status != 200 else "not healthy") in output.err
        assert not output.out


def test_missing_release_environment_fails_safely(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("IMAGE_REF", raising=False)
    assert verify_deployment.main() == 1
    assert "deployment verification failed" in capsys.readouterr().err
