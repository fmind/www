"""Contract tests for the manual Cloud Run deployment boundary."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts import deploy, verify_deployment
from scripts.deploy import DeploymentTarget, Runner, build_deploy_commands, build_gate_commands, main

TARGET = DeploymentTarget(
    region="europe-west1",
    project_id="www-fmind-dev",
    repository="app",
    service_name="www-fmind-dev",
)
VALID_IMAGE = f"{TARGET.image_repository}@sha256:{'a' * 64}"
VALID_COMMIT = "0123456789abcdef0123456789abcdef01234567"
GATES = (
    ("mise", "run", "check:image:digest", VALID_IMAGE),
    ("mise", "run", "test:image", VALID_IMAGE),
)
VERIFY_CREATED_REVISION = deploy.verify_created_revision
SCOPE = (
    "www-fmind-dev",
    "--project",
    "www-fmind-dev",
    "--billing-project",
    "www-fmind-dev",
    "--region",
    "europe-west1",
)


@pytest.fixture(autouse=True)
def offline_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deploy, "verify_created_revision", lambda *_: None)


class RecordingRunner:
    """Record commands without invoking mise or gcloud, returning scripted exit codes."""

    def __init__(self, *returncodes: int) -> None:
        self.returncodes = list(returncodes)
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, arguments: Sequence[str]) -> int:
        self.commands.append(tuple(arguments))
        return self.returncodes.pop(0) if self.returncodes else 0

    @property
    def gcloud_steps(self) -> list[str]:
        return [command[3] for command in self.commands if command[0] == "gcloud"]


class MissingExecutableRunner:
    """Represent a host where one executable is unavailable, as subprocess reports it."""

    def __init__(self, missing: str) -> None:
        self.missing = missing

    def __call__(self, arguments: Sequence[str]) -> int:
        if arguments[0] == self.missing:
            raise FileNotFoundError(2, "No such file or directory", self.missing)
        return 0


def test_valid_release_restamps_commit_and_routes_traffic_to_the_new_revision() -> None:
    assert build_deploy_commands((VALID_IMAGE, VALID_COMMIT), TARGET, revision_suffix="manual-test") == (
        (
            "gcloud",
            "run",
            "services",
            "update",
            *SCOPE,
            "--image",
            VALID_IMAGE,
            f"--update-labels=commit-sha={VALID_COMMIT}",
            "--revision-suffix=manual-test",
            "--no-traffic",
            "--tag=manual-candidate",
            "--quiet",
        ),
        (
            "gcloud",
            "run",
            "services",
            "update-traffic",
            *SCOPE,
            "--to-revisions=www-fmind-dev-manual-test=100",
            "--remove-tags=manual-candidate,candidate",
            "--quiet",
        ),
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


def test_ci_promotion_drops_the_candidate_tag_that_manual_rollouts_also_clear() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "deploy.yml").read_text()

    # A tag left on a promoted revision keeps it publicly served after a later rollback.
    assert re.search(rf"^  CANDIDATE_TAG: {deploy.CI_TAG}$", workflow, re.MULTILINE)
    promotion = workflow.split("- name: Promote the verified revision", 1)[1].split("- name:", 1)[0]
    assert '--to-revisions "$REVISION=100" --remove-tags "$CANDIDATE_TAG"' in promotion
    # An unpromoted candidate (failed or cancelled after deployment) loses its public tag URL
    # instead of keeping it until the next deploy.
    cleanup = workflow.split("- name: Remove the candidate tag after a failed or cancelled rollout", 1)[1].split(
        "- name:", 1
    )[0]
    condition = "(failure() || cancelled()) && steps.deploy.outcome != 'skipped' && steps.promote.outcome != 'success'"
    assert f"if: {condition}" in cleanup
    assert (
        "id: deploy" in workflow.split("- name: Deploy candidate revision without traffic", 1)[1].split("- name:", 1)[0]
    )
    assert "id: promote" in promotion
    assert '--remove-tags "$CANDIDATE_TAG"' in cleanup
    assert "--to-revisions" not in cleanup


def test_gates_reuse_the_ci_scan_and_smoke_tasks_for_the_exact_digest() -> None:
    assert build_gate_commands(VALID_IMAGE) == GATES

    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "deploy.yml").read_text()
    assert 'mise run check:image:digest "$IMAGE_REF"' in workflow
    assert 'mise run test:image "$IMAGE_REF"' in workflow


def test_successful_rollout_gates_the_digest_before_any_cloud_run_change() -> None:
    runner = RecordingRunner()

    assert main((VALID_IMAGE, VALID_COMMIT), target=TARGET, runner=runner) == 0
    assert tuple(runner.commands[:2]) == GATES
    assert runner.gcloud_steps == ["update", "update-traffic"]


@pytest.mark.parametrize(("returncodes", "gate"), [((5,), "check:image:digest"), ((0, 6), "test:image")])
def test_failed_image_gate_preserves_exit_status_and_never_calls_gcloud(
    returncodes: tuple[int, ...], gate: str, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = RecordingRunner(*returncodes)

    assert main((VALID_IMAGE, VALID_COMMIT), target=TARGET, runner=runner) == returncodes[-1]
    assert tuple(runner.commands) == GATES[: len(returncodes)]
    assert capsys.readouterr().err == f"image gate {gate} failed; nothing was deployed\n"


def test_failed_update_preserves_exit_status_and_never_moves_traffic() -> None:
    runner = RecordingRunner(0, 0, 9)

    assert main((VALID_IMAGE, VALID_COMMIT), target=TARGET, runner=runner) == 9
    assert runner.gcloud_steps == ["update"]


def test_failed_traffic_promotion_is_reported() -> None:
    runner = RecordingRunner(0, 0, 0, 7)

    assert main((VALID_IMAGE, VALID_COMMIT), target=TARGET, runner=runner) == 7
    assert runner.gcloud_steps == ["update", "update-traffic"]


def test_concurrent_revision_after_verification_never_receives_manual_traffic() -> None:
    runner = RecordingRunner()
    checked: list[str] = []

    def verify(target: DeploymentTarget, image: str, commit: str, revision: str) -> None:
        assert (target, image, commit) == (TARGET, VALID_IMAGE, VALID_COMMIT)
        assert runner.gcloud_steps == ["update"]
        checked.append(revision)
        # A concurrent deploy can now become latest; promotion must use the
        # already verified name without another lookup of mutable service state.

    assert main((VALID_IMAGE, VALID_COMMIT), target=TARGET, runner=runner, verifier=verify) == 0
    assert f"--to-revisions={checked[0]}=100" in runner.commands[-1]
    assert "--to-latest" not in runner.commands[-1]


@pytest.mark.parametrize("replaced", [False, True])
def test_manual_verifier_checks_expected_revision_before_probing(
    monkeypatch: pytest.MonkeyPatch, replaced: bool
) -> None:
    expected = "www-fmind-dev-manual-test"
    actual = "www-fmind-dev-concurrent" if replaced else expected
    url = "https://manual-candidate---www-fmind-dev-example.run.app"
    monkeypatch.setattr(verify_deployment, "describe_service", lambda _: {})
    monkeypatch.setattr(verify_deployment, "verify_candidate", lambda *_args, **_kwargs: (actual, url))
    probes: list[str] = []
    monkeypatch.setattr(verify_deployment, "probe", lambda origin, **_: probes.append(origin))
    if replaced:
        with pytest.raises(ValueError, match="replaced"):
            VERIFY_CREATED_REVISION(TARGET, VALID_IMAGE, VALID_COMMIT, expected)
        assert not probes
    else:
        VERIFY_CREATED_REVISION(TARGET, VALID_IMAGE, VALID_COMMIT, expected)
        assert probes == [url]


def test_failed_candidate_verification_never_promotes_or_exposes_diagnostics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = RecordingRunner()

    def fail(*_args: object) -> None:
        raise ValueError("private provider diagnostics")

    assert main((VALID_IMAGE, VALID_COMMIT), target=TARGET, runner=runner, verifier=fail) == 1
    assert runner.gcloud_steps == ["update"]
    assert capsys.readouterr().err == "candidate verification failed: ValueError; traffic was not promoted\n"


@pytest.mark.parametrize("suffix", ["bad,value", "UPPER", "a" * 64])
def test_invalid_revision_suffix_fails_before_deployment(suffix: str) -> None:
    with pytest.raises(ValueError, match="revision suffix"):
        build_deploy_commands((VALID_IMAGE, VALID_COMMIT), TARGET, revision_suffix=suffix)


@pytest.mark.parametrize("missing", ["mise", "gcloud"])
def test_missing_executable_is_a_safe_nonzero_failure(missing: str, capsys: pytest.CaptureFixture[str]) -> None:
    runner: Runner = MissingExecutableRunner(missing)

    assert main((VALID_IMAGE, VALID_COMMIT), target=TARGET, runner=runner) == 127

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"deployment failed: {missing} is not installed or executable\n"


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
