"""Contract tests for the manual Cloud Run deployment boundary."""

import os
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
VERIFY_PROMOTED_RELEASE = deploy.verify_promoted_release
SCOPE = (
    "www-fmind-dev",
    "--project",
    "www-fmind-dev",
    "--billing-project",
    "www-fmind-dev",
    "--region",
    "europe-west1",
)
# Removes only the manual tag of an unpromoted candidate; it never moves traffic.
CLEANUP = ("gcloud", "run", "services", "update-traffic", *SCOPE, "--remove-tags=manual-candidate", "--quiet")


@pytest.fixture(autouse=True)
def offline_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deploy, "verify_created_revision", lambda *_: None)
    monkeypatch.setattr(deploy, "verify_promoted_release", lambda *_: None)


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
        CLEANUP,
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
    assert captured.err.startswith("usage: mise run deploy <digest-ref> <commit-sha>")


def test_ci_workflow_delegates_gate_and_rollout_to_canonical_tasks() -> None:
    assert build_gate_commands(VALID_IMAGE) == GATES

    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "deploy.yml").read_text()
    assert "run: mise run all" in workflow
    assert 'run: mise run deploy "$IMAGE_REF" "$GITHUB_SHA"' in workflow
    assert "run: |" not in workflow
    assert "run: >-" not in workflow


def test_interrupted_rollout_cleans_up_the_candidate_tag_without_moving_traffic(
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = RecordingRunner()

    def interrupt(*_args: object) -> None:
        raise KeyboardInterrupt

    assert main((VALID_IMAGE, VALID_COMMIT), target=TARGET, runner=runner, verifier=interrupt) == 130
    assert runner.commands[-1] == CLEANUP
    assert not any(argument.startswith("--to-revisions") for command in runner.commands for argument in command)
    assert capsys.readouterr().err == "deployment interrupted; traffic was not promoted\n"


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
    # A failed update may still leave a tagged revision; the cleanup removes the tag without routing traffic.
    assert runner.commands[-1] == CLEANUP
    assert runner.gcloud_steps == ["update", "update-traffic"]


def test_failed_traffic_promotion_is_reported_and_drops_the_manual_tag() -> None:
    runner = RecordingRunner(0, 0, 0, 7)

    assert main((VALID_IMAGE, VALID_COMMIT), target=TARGET, runner=runner) == 7
    assert runner.gcloud_steps == ["update", "update-traffic", "update-traffic"]
    assert runner.commands[-1] == CLEANUP


def test_failed_tag_cleanup_is_reported_without_masking_the_failure(capsys: pytest.CaptureFixture[str]) -> None:
    runner = RecordingRunner(0, 0, 9, 4)

    assert main((VALID_IMAGE, VALID_COMMIT), target=TARGET, runner=runner) == 9
    assert (
        capsys.readouterr().err
        == "removing the manual-candidate tag failed; remove it by hand, since its tag URL stays public\n"
    )


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


# Our own invariant messages reach the log; any other failure shows only its type, never provider text.
VERIFICATION_FAILURES = pytest.mark.parametrize(
    ("error", "detail"),
    [
        (ValueError("private provider diagnostics"), "ValueError"),
        (subprocess.CalledProcessError(1, "gcloud", stderr="private provider diagnostics"), "CalledProcessError"),
        (verify_deployment.VerificationError("service is not ready"), "service is not ready"),
        (deploy.DeploymentUsageError("manual candidate was replaced"), "manual candidate was replaced"),
    ],
    ids=("value-error", "provider-error", "verification-error", "usage-error"),
)


@VERIFICATION_FAILURES
def test_failed_candidate_verification_never_promotes_or_exposes_diagnostics(
    capsys: pytest.CaptureFixture[str], error: Exception, detail: str
) -> None:
    runner = RecordingRunner()

    def fail(*_args: object) -> None:
        raise error

    assert main((VALID_IMAGE, VALID_COMMIT), target=TARGET, runner=runner, verifier=fail) == 1
    # The failed candidate loses its public tag URL now, as in CI, instead of at the next manual rollout.
    assert runner.commands[-1] == CLEANUP
    assert not any(argument.startswith("--to-revisions") for command in runner.commands for argument in command)
    assert capsys.readouterr().err == f"candidate verification failed: {detail}; traffic was not promoted\n"


@VERIFICATION_FAILURES
def test_promoted_release_is_verified_without_exposing_diagnostics(
    capsys: pytest.CaptureFixture[str], error: Exception, detail: str
) -> None:
    runner = RecordingRunner()
    checked: list[tuple[object, ...]] = []

    def fail(*arguments: object) -> None:
        checked.append(arguments)
        assert runner.gcloud_steps == ["update", "update-traffic"]
        raise error

    assert main((VALID_IMAGE, VALID_COMMIT), target=TARGET, runner=runner, post_verifier=fail) == 1
    assert checked[0][:3] == (TARGET, VALID_IMAGE, VALID_COMMIT)
    assert f"--to-revisions={checked[0][3]}=100" in runner.commands[-1]
    assert capsys.readouterr().err == (
        f"promoted release verification failed: {detail}; traffic stays on the new revision,"
        " so inspect it or redeploy the preceding qualified digest\n"
    )


@pytest.mark.parametrize("replaced", [False, True])
def test_promoted_release_check_reuses_test_deployed(monkeypatch: pytest.MonkeyPatch, replaced: bool) -> None:
    expected = "www-fmind-dev-manual-test"
    monkeypatch.setattr(verify_deployment, "describe_service", lambda _: {})
    serving = "www-fmind-dev-concurrent" if replaced else expected
    monkeypatch.setattr(verify_deployment, "verify_service", lambda *_args: serving)
    probes: list[tuple[str, str]] = []
    monkeypatch.setattr(verify_deployment, "probe", lambda origin, **_: probes.append(("probe", origin)))
    monkeypatch.setattr(verify_deployment, "probe_mcp", lambda origin, **_: probes.append(("mcp", origin)))
    if replaced:
        with pytest.raises(ValueError, match="replaced"):
            VERIFY_PROMOTED_RELEASE(TARGET, VALID_IMAGE, VALID_COMMIT, expected)
        assert not probes
    else:
        VERIFY_PROMOTED_RELEASE(TARGET, VALID_IMAGE, VALID_COMMIT, expected)
        assert probes == [("probe", "https://www.fmind.dev"), ("mcp", "https://www.fmind.dev")]


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
    assert result.stderr.startswith("usage: mise run deploy <digest-ref> <commit-sha>")


@pytest.mark.parametrize(
    ("head", "repository", "fails", "expected"),
    [
        (VALID_COMMIT, "fmind/www", False, "head=true\n"),
        ("f" * 40, "fmind/www", False, "head=false\n"),
        (VALID_COMMIT, "fmind/www", True, ""),
        ("not-a-sha", "fmind/www", False, ""),
        (VALID_COMMIT, "../bad", False, ""),
    ],
    ids=["head-of-main", "superseded", "api-failure", "malformed-sha", "invalid-repository"],
)
def test_ci_deploys_only_the_current_head_of_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    head: str,
    repository: str,
    fails: bool,
    expected: str,
) -> None:
    # A rerun of an older main run must never promote its image over a newer one.
    fake_gh = tmp_path / "gh"
    fake_gh.write_text(f"#!/bin/sh\n{'exit 1' if fails else f'echo {head}'}\n")
    fake_gh.chmod(0o755)
    output = tmp_path / "output"
    output.touch()
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    monkeypatch.setenv("GITHUB_SHA", VALID_COMMIT)
    monkeypatch.setenv("GITHUB_REPOSITORY", repository)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    returncode = main(("--check-head",))
    captured = capsys.readouterr()

    assert (returncode == 0) is bool(expected)
    assert output.read_text() == expected
    assert ("Superseded by" in captured.out) is (expected == "head=false\n")

    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "deploy.yml").read_text()
    assert "run: uv run --locked python -m scripts.deploy --check-head" in workflow
    deploy_job = workflow.split("\n  deploy:\n", 1)[1]
    assert deploy_job.startswith("    needs: verify\n    if: needs.verify.outputs.head == 'true'\n")


def test_timed_out_candidate_update_drops_the_manual_tag_without_moving_traffic(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(arguments: tuple[str, ...], **options: float) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        if arguments[:4] == ("gcloud", "run", "services", "update"):
            raise subprocess.TimeoutExpired(arguments, options["timeout"])
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(deploy.subprocess, "run", fake_run)

    assert main((VALID_IMAGE, VALID_COMMIT), target=TARGET) == deploy.TIMEOUT_EXIT
    assert calls[-1] == CLEANUP
    assert not any(argument.startswith("--to-revisions") for command in calls for argument in command)
    assert capsys.readouterr().err == (
        "deploy: gcloud run services update timed out after 600s;"
        " inspect the Cloud Run service, then rerun the deployment\n"
    )
