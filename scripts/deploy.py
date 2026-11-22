"""Fail-closed argument boundary for CI and manual Cloud Run rollouts."""

import argparse
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import FrameType

from scripts import verify_deployment
from scripts._cloud_run import (
    _COMMIT,
    _CONFIG_VALUE,
    DeploymentTarget,
    DeploymentUsageError,
    validate_commit,
    validate_image_reference,
)

_REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
# Release verification reads the revision's `commit-sha` label, so every rollout stamps it.
COMMIT_LABEL = "commit-sha"
# One hung gate or gcloud call must fail inside the 20-minute deploy job, leaving time to remove the candidate tag.
COMMAND_TIMEOUT_SECONDS: float = 600
TIMEOUT_EXIT = 124  # the exit status coreutils `timeout` uses
_USAGE = "usage: mise run deploy <digest-ref> <commit-sha> | python -m scripts.deploy --check-head\n"

type Runner = Callable[[Sequence[str]], int]
type Verifier = Callable[[DeploymentTarget, str, str, str], None]


def run_command(arguments: Sequence[str]) -> int:
    """Run validated mise or gcloud argv with closed stdin and signals, for at most COMMAND_TIMEOUT_SECONDS.

    A timeout returns TIMEOUT_EXIT like any failed step, so the caller still removes the candidate tag.
    """
    try:
        return subprocess.run(  # noqa: S603 - fixed, validated argv only.
            tuple(arguments),
            stdin=subprocess.DEVNULL,
            check=False,
            timeout=COMMAND_TIMEOUT_SECONDS,
        ).returncode
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            f"deploy: {' '.join(arguments[:4])} timed out after {COMMAND_TIMEOUT_SECONDS:g}s;"
            " inspect the Cloud Run service, then rerun the deployment\n"
        )
        return TIMEOUT_EXIT


def build_gate_commands(image_reference: str) -> tuple[tuple[str, ...], ...]:
    """Return the digest gates CI runs before deployment: the Trivy scan, then the image smoke test.

    Reusing the mise tasks keeps one scanner policy and one smoke contract for CI and manual rollouts.
    """
    return (
        ("mise", "run", "check:image:digest", image_reference),
        ("mise", "run", "test:image", image_reference),
    )


def candidate_tag_for_revision(revision_suffix: str) -> str:
    """Return the unique per-rollout Cloud Run traffic tag for a candidate revision."""
    return revision_suffix


def build_deploy_commands(
    arguments: Sequence[str], target: DeploymentTarget, *, revision_suffix: str
) -> tuple[tuple[str, ...], ...]:
    """Validate one digest and its commit, then return the fixed gcloud argv sequence.

    Create a uniquely named no-traffic candidate with its own per-rollout tag,
    then promote only that name. The caller must verify the candidate between
    these two commands, and run the third, which removes only this rollout's
    tag, when the candidate is not promoted.
    """
    if len(arguments) != 2:
        raise DeploymentUsageError("exactly one image reference and one commit SHA are required")

    image_reference = validate_image_reference(arguments[0], target)
    commit = validate_commit(arguments[1])
    revision = f"{target.service_name}-{revision_suffix}"
    if not _CONFIG_VALUE.fullmatch(revision_suffix) or len(revision) > 63:
        raise DeploymentUsageError("revision suffix must produce a valid revision name of at most 63 characters")
    candidate_tag = candidate_tag_for_revision(revision_suffix)
    scope = (
        target.service_name,
        "--project",
        target.project_id,
        "--billing-project",
        target.project_id,
        "--region",
        target.region,
    )
    return (
        (
            "gcloud",
            "run",
            "services",
            "update",
            *scope,
            "--image",
            image_reference,
            f"--update-labels={COMMIT_LABEL}={commit}",
            f"--revision-suffix={revision_suffix}",
            "--no-traffic",
            f"--tag={candidate_tag}",
            "--quiet",
        ),
        # Drop the candidate tag on promotion: a tagged revision stays publicly reachable after traffic moves on.
        (
            "gcloud",
            "run",
            "services",
            "update-traffic",
            *scope,
            f"--to-revisions={revision}=100",
            f"--remove-tags={candidate_tag}",
            "--quiet",
        ),
        # Remove only this rollout's tag so a failing rollout never strips a concurrent rollout's candidate.
        ("gcloud", "run", "services", "update-traffic", *scope, f"--remove-tags={candidate_tag}", "--quiet"),
    )


def verify_created_revision(target: DeploymentTarget, image: str, commit: str, expected_revision: str) -> None:
    """Verify the newly created no-traffic candidate revision and probe its tagged URL."""
    prefix = f"{target.service_name}-"
    if not expected_revision.startswith(prefix):
        raise DeploymentUsageError("candidate revision name does not match target service")
    candidate_tag = candidate_tag_for_revision(expected_revision.removeprefix(prefix))
    revision, url = verify_deployment.verify_candidate(
        verify_deployment.describe_service(target), image, commit, tag=candidate_tag, service_name=target.service_name
    )
    if revision != expected_revision:
        raise DeploymentUsageError("candidate revision was replaced by another deployment; traffic was not promoted")
    verify_deployment.probe(url, timeout=65)


def verify_promoted_release(target: DeploymentTarget, image: str, commit: str, expected_revision: str) -> None:
    """Run the `test:deployed` checks: the promoted revision owns all traffic and serves the public origin."""
    if verify_deployment.verify_service(verify_deployment.describe_service(target), image, commit) != expected_revision:
        raise DeploymentUsageError("another deployment replaced the manual release after promotion")
    verify_deployment.probe_public_origin()


def check_main_head(environment: Mapping[str, str] = os.environ) -> int:
    """Confirm the current workflow commit is still the head of main before deploying."""
    try:
        commit = validate_commit(environment.get("GITHUB_SHA", ""))
        repository = environment.get("GITHUB_REPOSITORY", "")
        if not _REPOSITORY.fullmatch(repository):
            raise DeploymentUsageError("GITHUB_REPOSITORY must be set to <owner>/<repo>")
        executable = shutil.which("gh", path=environment.get("PATH"))
        if executable is None:
            raise DeploymentUsageError("gh is not installed")
        result = subprocess.run(  # noqa: S603 - fixed read-only gh argv.
            (executable, "api", f"repos/{repository}/commits/main", "--jq", ".sha"),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            env=dict(environment),
        )
        head_sha = result.stdout.strip()
        if result.returncode != 0 or not _COMMIT.fullmatch(head_sha):
            raise DeploymentUsageError("could not resolve the current head of main")
        is_head = head_sha == commit
        if output := environment.get("GITHUB_OUTPUT"):
            with Path(output).open("a", encoding="utf-8") as stream:
                stream.write(f"head={'true' if is_head else 'false'}\n")
        if not is_head:
            sys.stdout.write(f"::notice::Superseded by {head_sha} on main; skipping the deployment of {commit}\n")
        return 0
    except (DeploymentUsageError, OSError, subprocess.SubprocessError) as error:
        detail = str(error) if isinstance(error, DeploymentUsageError) else type(error).__name__
        sys.stderr.write(f"deploy: {detail}\n")
        return 1


def _raise_interrupt(_signum: int, _frame: FrameType | None) -> None:
    raise KeyboardInterrupt


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.deploy",
        description="Gate, deploy, and verify one immutable Artifact Registry digest on Cloud Run.",
        allow_abbrev=False,
        suggest_on_error=True,
    )
    parser.add_argument("--check-head", action="store_true", help="check whether GITHUB_SHA is still main HEAD")
    parser.add_argument("args", nargs="*", metavar="ARG", help="<digest-ref> <commit-sha>")
    return parser


def main(
    arguments: Sequence[str] | None = None,
    *,
    target: DeploymentTarget | None = None,
    runner: Runner | None = None,
    verifier: Verifier | None = None,
    post_verifier: Verifier | None = None,
) -> int:
    """Validate, gate the digest, then run each gcloud step, stopping at the first failure.

    An unpromoted candidate loses its manual tag; a promoted one gets the `test:deployed` checks.
    """
    raw_args = tuple(sys.argv[1:] if arguments is None else arguments)
    if any(arg in ("-h", "--help") for arg in raw_args):
        _build_parser().print_help()
        return 0
    if raw_args == ("--check-head",):
        return check_main_head()
    release_arguments = raw_args
    try:
        deployment_target = target or DeploymentTarget.from_environment()
        suffix = f"manual-{secrets.token_hex(6)}"
        commands = build_deploy_commands(release_arguments, deployment_target, revision_suffix=suffix)
    except DeploymentUsageError as error:
        sys.stderr.write(f"{_USAGE}deploy: {error}\n")
        return 2

    execute = runner or run_command
    try:
        # Scan and smoke-test the digest before any Cloud Run change:
        # the registry also holds digests that earlier runs rejected.
        for gate in build_gate_commands(release_arguments[0]):
            if returncode := execute(gate):
                sys.stderr.write(f"image gate {gate[2]} failed; nothing was deployed\n")
                return returncode
        candidate_tag = candidate_tag_for_revision(suffix)
        release = (deployment_target, *release_arguments, f"{deployment_target.service_name}-{suffix}")
        promoted = False
        in_main_thread = threading.current_thread() is threading.main_thread()
        previous_sigterm = signal.getsignal(signal.SIGTERM) if in_main_thread else None
        if in_main_thread:
            signal.signal(signal.SIGTERM, _raise_interrupt)
        try:
            if not (returncode := execute(commands[0])):
                try:
                    (verifier or verify_created_revision)(*release)
                except Exception as error:  # noqa: BLE001 - fail closed without leaking provider diagnostics
                    sys.stderr.write(
                        f"candidate verification failed: {verify_deployment.safe_detail(error)}; traffic was not promoted\n"
                    )
                    returncode = 1
                else:
                    returncode = execute(commands[1])
                    promoted = returncode == 0
        except KeyboardInterrupt:
            sys.stderr.write("deployment interrupted; traffic was not promoted\n")
            returncode = 130
        finally:
            if in_main_thread and previous_sigterm is not None:
                signal.signal(signal.SIGTERM, previous_sigterm)
        if not promoted:
            if execute(commands[2]):
                sys.stderr.write(
                    f"removing the {candidate_tag} tag failed; remove it by hand, since its tag URL stays public\n"
                )
            return returncode
        try:
            (post_verifier or verify_promoted_release)(*release)
        except Exception as error:  # noqa: BLE001 - fail closed without leaking provider diagnostics
            sys.stderr.write(
                f"promoted release verification failed: {verify_deployment.safe_detail(error)}; traffic stays on the new revision,"
                " so inspect it or redeploy the preceding qualified digest\n"
            )
            return 1
        return 0
    except FileNotFoundError as error:
        sys.stderr.write(
            f"deployment failed: {error.filename or 'a required command'} is not installed or executable\n"
        )
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
