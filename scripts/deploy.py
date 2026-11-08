"""Fail-closed argument boundary for CI and manual Cloud Run rollouts."""

import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import FrameType

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_CONFIG_VALUE = re.compile(r"[a-z][a-z0-9-]*[a-z0-9]\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_CONFIG_NAMES = ("REGION", "PROJECT_ID", "REPOSITORY", "SERVICE_NAME")
# The CI deploy action labels revisions `commit-sha=<GITHUB_SHA>`; release
# verification reads the same label, so a manual rollout must restamp it.
COMMIT_LABEL = "commit-sha"
MANUAL_TAG = "manual-candidate"
# Cleared alongside MANUAL_TAG on promotion so no legacy CI candidate tag remains public.
CI_TAG = "candidate"
_USAGE = "usage: mise run deploy <digest-ref> <commit-sha> | python -m scripts.deploy --check-head\n"


class DeploymentUsageError(ValueError):
    """The manual deployment request does not match the digest-and-commit contract."""


@dataclass(frozen=True, slots=True)
class DeploymentTarget:
    """Repository-owned Cloud Run and Artifact Registry coordinates."""

    region: str
    project_id: str
    repository: str
    service_name: str

    def __post_init__(self) -> None:
        for name, value in zip(_CONFIG_NAMES, self.as_tuple(), strict=True):
            if not _CONFIG_VALUE.fullmatch(value):
                raise DeploymentUsageError(f"{name} is missing or invalid")

    def as_tuple(self) -> tuple[str, str, str, str]:
        return self.region, self.project_id, self.repository, self.service_name

    @property
    def image_repository(self) -> str:
        return f"{self.region}-docker.pkg.dev/{self.project_id}/{self.repository}/{self.service_name}"

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] = os.environ) -> DeploymentTarget:
        return cls(*(environment.get(name, "") for name in _CONFIG_NAMES))


type Runner = Callable[[Sequence[str]], int]
type Verifier = Callable[[DeploymentTarget, str, str, str], None]


def run_command(arguments: Sequence[str]) -> int:
    """Run validated mise or gcloud argv with inherited streams and signals."""
    return subprocess.run(tuple(arguments), check=False).returncode  # noqa: S603 - fixed, validated argv only.


def validate_image_reference(image_reference: str, target: DeploymentTarget) -> str:
    """Accept only an immutable digest in this service's repository."""
    repository, separator, digest = image_reference.rpartition("@")
    if separator != "@" or repository != target.image_repository or not _DIGEST.fullmatch(digest):
        raise DeploymentUsageError(f"image must match {target.image_repository}@sha256:<64 lowercase hex>")
    return image_reference


def validate_commit(commit: str) -> str:
    """Accept only a full lowercase Git commit SHA."""
    if not _COMMIT.fullmatch(commit):
        raise DeploymentUsageError("commit must be a full 40-character lowercase SHA")
    return commit


def build_gate_commands(image_reference: str) -> tuple[tuple[str, ...], ...]:
    """Return the digest gates CI runs before deployment: the Trivy scan, then the image smoke test.

    Reusing the mise tasks keeps one scanner policy and one smoke contract for CI and manual rollouts.
    """
    return (
        ("mise", "run", "check:image:digest", image_reference),
        ("mise", "run", "test:image", image_reference),
    )


def build_deploy_commands(
    arguments: Sequence[str], target: DeploymentTarget, *, revision_suffix: str
) -> tuple[tuple[str, ...], ...]:
    """Validate one digest and its commit, then return the fixed gcloud argv sequence.

    Create a uniquely named no-traffic candidate, then promote only that name.
    The caller must verify the candidate between these two commands, and run the
    third, which only removes the manual tag, when the candidate is not promoted.
    """
    if len(arguments) != 2:
        raise DeploymentUsageError("exactly one image reference and one commit SHA are required")

    image_reference = validate_image_reference(arguments[0], target)
    commit = validate_commit(arguments[1])
    revision = f"{target.service_name}-{revision_suffix}"
    if not _CONFIG_VALUE.fullmatch(revision_suffix) or len(revision) > 63:
        raise DeploymentUsageError("revision suffix must produce a valid revision name of at most 63 characters")
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
            f"--tag={MANUAL_TAG}",
            "--quiet",
        ),
        # Drop both candidate tags on promotion: a tagged revision stays publicly reachable after traffic moves on
        # (a 2026-10-12 build was still served on its manual-candidate URL on 2026-10-24). Clearing the CI tag
        # keeps a rolled-back or failed CI revision off its candidate URL. gcloud skips tags the service lacks.
        (
            "gcloud",
            "run",
            "services",
            "update-traffic",
            *scope,
            f"--to-revisions={revision}=100",
            f"--remove-tags={MANUAL_TAG},{CI_TAG}",
            "--quiet",
        ),
        # Like CI after a failed or cancelled candidate: an unpromoted revision loses its public tag URL now.
        ("gcloud", "run", "services", "update-traffic", *scope, f"--remove-tags={MANUAL_TAG}", "--quiet"),
    )


def verify_created_revision(target: DeploymentTarget, image: str, commit: str, expected_revision: str) -> None:
    """Reuse CI acceptance without a module-level cycle with its argument types."""
    from scripts.verify_deployment import describe_service, probe, verify_candidate

    revision, url = verify_candidate(
        describe_service(target), image, commit, tag=MANUAL_TAG, service_name=target.service_name
    )
    if revision != expected_revision:
        raise DeploymentUsageError("manual candidate was replaced by another deployment; traffic was not promoted")
    probe(url, timeout=65)


def verify_promoted_release(target: DeploymentTarget, image: str, commit: str, expected_revision: str) -> None:
    """Run the `test:deployed` checks: the promoted revision owns all traffic and serves the public origin."""
    from scripts.verify_deployment import PUBLIC_ORIGIN, describe_service, probe, probe_mcp, verify_service

    if verify_service(describe_service(target), image, commit) != expected_revision:
        raise DeploymentUsageError("another deployment replaced the manual release after promotion")
    # Promotion can route the first public request to a cold instance; allow the 60s startup budget.
    probe(PUBLIC_ORIGIN, timeout=65)
    probe_mcp(PUBLIC_ORIGIN, timeout=15)


def check_main_head(environment: Mapping[str, str] = os.environ) -> int:
    """Confirm the current workflow commit is still the head of main before deploying."""
    try:
        commit = validate_commit(environment.get("GITHUB_SHA") or environment.get("CURRENT_SHA", ""))
        repository = environment.get("GITHUB_REPOSITORY") or environment.get("REPOSITORY", "")
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
    release_arguments = tuple(sys.argv[1:] if arguments is None else arguments)
    if release_arguments == ("--check-head",):
        return check_main_head()
    try:
        deployment_target = target or DeploymentTarget.from_environment()
        suffix = f"manual-{secrets.token_hex(6)}"
        commands = build_deploy_commands(release_arguments, deployment_target, revision_suffix=suffix)
    except DeploymentUsageError as error:
        sys.stderr.write(f"{_USAGE}deploy: {error}\n")
        return 2

    execute = runner or run_command
    try:
        # Scan and smoke-test the digest before any Cloud Run change, as CI does:
        # the registry also holds digests that CI rejected.
        for gate in build_gate_commands(release_arguments[0]):
            if returncode := execute(gate):
                sys.stderr.write(f"image gate {gate[2]} failed; nothing was deployed\n")
                return returncode
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
                except Exception as error:
                    # Provider/HTTP diagnostics may contain private data. Fail closed
                    # and report the cause's type without reflecting its unsafe text.
                    sys.stderr.write(
                        f"candidate verification failed: {type(error).__name__}; traffic was not promoted\n"
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
                    f"removing the {MANUAL_TAG} tag failed; remove it by hand, since its tag URL stays public\n"
                )
            return returncode
        try:
            (post_verifier or verify_promoted_release)(*release)
        except Exception as error:
            sys.stderr.write(
                f"promoted release verification failed: {type(error).__name__}; traffic stays on the new revision,"
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
