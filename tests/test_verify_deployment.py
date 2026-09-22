"""Release acceptance rejects stale, partial, and unexpectedly costly rollouts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
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


TAG = "candidate"
CANDIDATE_URL = "https://candidate---www-fmind-dev-ba55y5pbla-ew.a.run.app"
PREVIOUS = "www-fmind-dev-00000-old"


@pytest.fixture
def candidate(service: dict[str, Any]) -> dict[str, Any]:
    service["metadata"]["name"] = "www-fmind-dev"
    service["status"]["traffic"] = [
        {"revisionName": PREVIOUS, "percent": 100},
        {"revisionName": REVISION, "tag": TAG, "url": CANDIDATE_URL},
    ]
    return service


def verify(candidate: dict[str, Any]) -> tuple[str, str]:
    return verify_deployment.verify_candidate(candidate, IMAGE, COMMIT, tag=TAG, service_name="www-fmind-dev")


def test_candidate_without_traffic_is_verified_on_its_tagged_url(candidate: dict[str, Any]) -> None:
    assert verify(candidate) == (REVISION, CANDIDATE_URL)
    with pytest.raises(ValueError, match="all traffic"):
        verify_service(candidate, IMAGE, COMMIT)


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ({"revisionName": PREVIOUS, "tag": TAG, "url": CANDIDATE_URL}, "does not address"),
        ({"revisionName": REVISION, "tag": "other", "url": CANDIDATE_URL}, "does not address"),
        ({"revisionName": REVISION, "tag": TAG}, "no run.app URL"),
        ({"revisionName": REVISION, "tag": TAG, "url": "https://candidate---www-fmind-dev.example.com"}, "run.app"),
        ({"revisionName": REVISION, "tag": TAG, "url": "https://candidate---other-ba55y5pbla-ew.a.run.app"}, "run.app"),
    ],
    ids=("stale-tag", "missing-tag", "missing-url", "foreign-host", "foreign-service"),
)
def test_candidate_tag_must_address_this_service_revision(
    candidate: dict[str, Any], entry: dict[str, str], message: str
) -> None:
    candidate["status"]["traffic"][1] = entry
    with pytest.raises(ValueError, match=message):
        verify(candidate)


def test_candidate_with_stale_commit_label_fails(candidate: dict[str, Any]) -> None:
    candidate["spec"]["template"]["metadata"]["labels"]["commit-sha"] = "c" * 40
    with pytest.raises(ValueError, match="commit differs"):
        verify(candidate)


def test_candidate_revision_must_belong_to_service(candidate: dict[str, Any]) -> None:
    for field in ("latestReadyRevisionName", "latestCreatedRevisionName"):
        candidate["status"][field] = "other-00001-abc"
    candidate["status"]["traffic"][1]["revisionName"] = "other-00001-abc"
    with pytest.raises(ValueError, match="does not belong"):
        verify(candidate)


@pytest.mark.parametrize("healthy", [True, False])
def test_candidate_command_probes_tagged_url_and_records_revision(
    candidate: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    healthy: bool,
) -> None:
    output = tmp_path / "github-output"
    for key, value in {
        "REGION": "europe-west1",
        "PROJECT_ID": "www-fmind-dev",
        "REPOSITORY": "app",
        "SERVICE_NAME": "www-fmind-dev",
        "IMAGE_REF": IMAGE,
        "GITHUB_SHA": COMMIT,
        "CANDIDATE_TAG": TAG,
        "GITHUB_OUTPUT": str(output),
    }.items():
        monkeypatch.setenv(key, value)

    def describe(command: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, json.dumps(candidate), "")

    monkeypatch.setattr(verify_deployment.shutil, "which", lambda _: "/usr/bin/gcloud")
    monkeypatch.setattr(verify_deployment.subprocess, "run", describe)
    hosts: set[str] = set()

    def respond(request: httpx2.Request) -> httpx2.Response:
        hosts.add(request.url.host)
        return httpx2.Response(200 if healthy else 503, json={"status": "ok"})

    client = httpx2.Client(transport=httpx2.MockTransport(respond))
    monkeypatch.setattr(verify_deployment.httpx2, "Client", lambda **_kwargs: client)

    assert verify_deployment.main(("candidate",)) == (0 if healthy else 1)
    assert hosts == {"candidate---www-fmind-dev-ba55y5pbla-ew.a.run.app"}
    if healthy:
        assert output.read_text(encoding="utf-8") == f"revision={REVISION}\n"
        assert "Verified candidate" in capsys.readouterr().out
    else:
        assert not output.exists()
        assert "HTTPStatusError" in capsys.readouterr().err


def test_invalid_candidate_tag_fails_before_gcloud(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for key, value in {
        "REGION": "europe-west1",
        "PROJECT_ID": "www-fmind-dev",
        "REPOSITORY": "app",
        "SERVICE_NAME": "www-fmind-dev",
        "IMAGE_REF": IMAGE,
        "GITHUB_SHA": COMMIT,
        "CANDIDATE_TAG": "Bad\nrevision=x",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(verify_deployment.shutil, "which", pytest.fail)
    assert verify_deployment.main(("candidate",)) == 1
    assert "CANDIDATE_TAG is invalid" in capsys.readouterr().err


@pytest.mark.parametrize("commit", ["B" * 40, "b" * 39])
def test_invalid_expected_commit_fails_with_safe_reason(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], commit: str
) -> None:
    for key, value in {
        "REGION": "europe-west1",
        "PROJECT_ID": "www-fmind-dev",
        "REPOSITORY": "app",
        "SERVICE_NAME": "www-fmind-dev",
        "IMAGE_REF": IMAGE,
        "GITHUB_SHA": commit,
    }.items():
        monkeypatch.setenv(key, value)
    assert verify_deployment.main() == 1
    assert "40-character lowercase SHA" in capsys.readouterr().err


def test_unknown_mode_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert verify_deployment.main(("promote",)) == 2
    assert capsys.readouterr().err.startswith("usage:")
