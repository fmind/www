"""Contract tests for the manual Cloud Run deployment boundary."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence

import pytest

from www.deployment import DeploymentTarget, Runner, build_deploy_command, main

TARGET = DeploymentTarget(
    region="europe-west1",
    project_id="www-fmind-dev",
    repository="app",
    service_name="www-fmind-dev",
)
VALID_IMAGE = f"{TARGET.image_repository}@sha256:{'a' * 64}"


class RecordingRunner:
    """Record a command without invoking gcloud."""

    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.commands: list[tuple[str, ...]] = []

    def run(self, arguments: Sequence[str]) -> int:
        self.commands.append(tuple(arguments))
        return self.returncode


class MissingExecutableRunner:
    """Represent a host where gcloud is unavailable."""

    def run(self, arguments: Sequence[str]) -> int:
        del arguments
        raise FileNotFoundError("gcloud")


def test_valid_digest_builds_one_fixed_gcloud_command() -> None:
    assert build_deploy_command((VALID_IMAGE,), TARGET) == (
        "gcloud",
        "run",
        "services",
        "update",
        "www-fmind-dev",
        "--project",
        "www-fmind-dev",
        "--billing-project",
        "www-fmind-dev",
        "--region",
        "europe-west1",
        "--image",
        VALID_IMAGE,
        "--quiet",
    )


@pytest.mark.parametrize(
    "arguments",
    [
        (),
        (VALID_IMAGE, "--region=elsewhere"),
        (f"{TARGET.image_repository}:latest",),
        (f"{TARGET.image_repository}@sha256:{'A' * 64}",),
        (f"europe-west1-docker.pkg.dev/www-fmind-dev/other/www-fmind-dev@sha256:{'a' * 64}",),
    ],
    ids=("missing", "extra", "tag", "uppercase-digest", "wrong-repository"),
)
def test_invalid_arguments_exit_with_usage_without_invoking_gcloud(
    arguments: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    runner = RecordingRunner()

    assert main(arguments, target=TARGET, runner=runner) == 2

    assert runner.commands == []
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("usage: mise run deploy <digest-ref>\n")


def test_gcloud_exit_status_is_preserved() -> None:
    runner = RecordingRunner(returncode=9)

    assert main((VALID_IMAGE,), target=TARGET, runner=runner) == 9
    assert len(runner.commands) == 1


def test_missing_gcloud_is_a_safe_nonzero_failure(capsys: pytest.CaptureFixture[str]) -> None:
    runner: Runner = MissingExecutableRunner()

    assert main((VALID_IMAGE,), target=TARGET, runner=runner) == 127

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
        (sys.executable, "-m", "www.deployment"),
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("usage: mise run deploy <digest-ref>\n")
