"""Contract tests for the manual Cloud Run deployment boundary."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence

import pytest

from scripts.deploy import DeploymentTarget, Runner, build_deploy_commands, main

TARGET = DeploymentTarget(
    region="europe-west1",
    project_id="www-fmind-dev",
    repository="app",
    service_name="www-fmind-dev",
)
VALID_IMAGE = f"{TARGET.image_repository}@sha256:{'a' * 64}"
VALID_COMMIT = "0123456789abcdef0123456789abcdef01234567"
SCOPE = (
    "www-fmind-dev",
    "--project",
    "www-fmind-dev",
    "--billing-project",
    "www-fmind-dev",
    "--region",
    "europe-west1",
)


class RecordingRunner:
    """Record commands without invoking gcloud, returning scripted exit codes."""

    def __init__(self, *returncodes: int) -> None:
        self.returncodes = list(returncodes)
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, arguments: Sequence[str]) -> int:
        self.commands.append(tuple(arguments))
        return self.returncodes.pop(0) if self.returncodes else 0


class MissingExecutableRunner:
    """Represent a host where gcloud is unavailable."""

    def __call__(self, arguments: Sequence[str]) -> int:
        del arguments
        raise FileNotFoundError("gcloud")


def test_valid_release_restamps_commit_and_routes_traffic_to_the_new_revision() -> None:
    assert build_deploy_commands((VALID_IMAGE, VALID_COMMIT), TARGET) == (
        (
            "gcloud",
            "run",
            "services",
            "update",
            *SCOPE,
            "--image",
            VALID_IMAGE,
            f"--update-labels=commit-sha={VALID_COMMIT}",
            "--quiet",
        ),
        ("gcloud", "run", "services", "update-traffic", *SCOPE, "--to-latest", "--quiet"),
    )


@pytest.mark.parametrize(
    "arguments",
    [
        (),
        (VALID_IMAGE,),
        (VALID_IMAGE, VALID_COMMIT, "--region=elsewhere"),
        (f"{TARGET.image_repository}:latest", VALID_COMMIT),
        (f"{TARGET.image_repository}@sha256:{'A' * 64}", VALID_COMMIT),
        (f"europe-west1-docker.pkg.dev/www-fmind-dev/other/www-fmind-dev@sha256:{'a' * 64}", VALID_COMMIT),
        (VALID_IMAGE, VALID_COMMIT[:12]),
        (VALID_IMAGE, VALID_COMMIT.upper()),
        (VALID_IMAGE, f"{VALID_COMMIT[:-1]}g"),
        (VALID_IMAGE, f"{VALID_COMMIT},managed-by=manual"),
        (VALID_COMMIT, VALID_IMAGE),
    ],
    ids=(
        "missing",
        "missing-commit",
        "extra",
        "tag",
        "uppercase-digest",
        "wrong-repository",
        "short-commit",
        "uppercase-commit",
        "non-hex-commit",
        "label-injection",
        "swapped",
    ),
)
def test_invalid_arguments_exit_with_usage_without_invoking_gcloud(
    arguments: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    runner = RecordingRunner()

    assert main(arguments, target=TARGET, runner=runner) == 2

    assert runner.commands == []
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("usage: mise run deploy <digest-ref> <commit-sha>\n")


def test_successful_update_is_followed_by_traffic_promotion() -> None:
    runner = RecordingRunner()

    assert main((VALID_IMAGE, VALID_COMMIT), target=TARGET, runner=runner) == 0
    assert [command[3] for command in runner.commands] == ["update", "update-traffic"]


def test_failed_update_preserves_exit_status_and_never_moves_traffic() -> None:
    runner = RecordingRunner(9)

    assert main((VALID_IMAGE, VALID_COMMIT), target=TARGET, runner=runner) == 9
    assert [command[3] for command in runner.commands] == ["update"]


def test_failed_traffic_promotion_is_reported() -> None:
    runner = RecordingRunner(0, 7)

    assert main((VALID_IMAGE, VALID_COMMIT), target=TARGET, runner=runner) == 7
    assert [command[3] for command in runner.commands] == ["update", "update-traffic"]


def test_missing_gcloud_is_a_safe_nonzero_failure(capsys: pytest.CaptureFixture[str]) -> None:
    runner: Runner = MissingExecutableRunner()

    assert main((VALID_IMAGE, VALID_COMMIT), target=TARGET, runner=runner) == 127

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "deployment failed: gcloud is not installed or executable\n"


def test_module_invocation_rejects_missing_digest_without_gcloud() -> None:
    environment = os.environ.copy()
    environment.update(
        REGION=TARGET.region,
        PROJECT_ID=TARGET.project_id,
        REPOSITORY=TARGET.repository,
        SERVICE_NAME=TARGET.service_name,
    )

    result = subprocess.run(
        (sys.executable, "-m", "scripts.deploy"),
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("usage: mise run deploy <digest-ref> <commit-sha>\n")
