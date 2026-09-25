"""Fail-closed argument boundary for manual Cloud Run rollouts."""

from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_CONFIG_VALUE = re.compile(r"[a-z][a-z0-9-]*[a-z0-9]\Z")
_CONFIG_NAMES = ("REGION", "PROJECT_ID", "REPOSITORY", "SERVICE_NAME")
# The CI deploy action labels revisions `commit-sha=<GITHUB_SHA>`; release
# verification reads the same label, so a manual rollout must restamp it.
COMMIT_LABEL = "commit-sha"
MANUAL_TAG = "manual-candidate"
_USAGE = "usage: mise run deploy <digest-ref> <commit-sha>\n"


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
    """Run validated gcloud argv with inherited streams and signals."""
    return subprocess.run(tuple(arguments), check=False).returncode  # noqa: S603 - fixed gcloud argv only.


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


def build_deploy_commands(
    arguments: Sequence[str], target: DeploymentTarget, *, revision_suffix: str
) -> tuple[tuple[str, ...], ...]:
    """Validate one digest and its commit, then return the fixed gcloud argv sequence.

    Create a uniquely named no-traffic candidate, then promote only that name.
    The caller must verify the candidate between these two commands.
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
        ("gcloud", "run", "services", "update-traffic", *scope, f"--to-revisions={revision}=100", "--quiet"),
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


def main(
    arguments: Sequence[str] | None = None,
    *,
    target: DeploymentTarget | None = None,
    runner: Runner | None = None,
    verifier: Verifier | None = None,
) -> int:
    """Validate first, then run each gcloud step, stopping at the first failure."""
    try:
        deployment_target = target or DeploymentTarget.from_environment()
        release_arguments = tuple(sys.argv[1:] if arguments is None else arguments)
        suffix = f"manual-{secrets.token_hex(6)}"
        commands = build_deploy_commands(release_arguments, deployment_target, revision_suffix=suffix)
    except DeploymentUsageError as error:
        sys.stderr.write(f"{_USAGE}deploy: {error}\n")
        return 2

    execute = runner or run_command
    try:
        if returncode := execute(commands[0]):
            return returncode
        try:
            (verifier or verify_created_revision)(
                deployment_target,
                release_arguments[0],
                release_arguments[1],
                f"{deployment_target.service_name}-{suffix}",
            )
        except Exception as error:
            # Provider/HTTP diagnostics may contain private data. Fail closed
            # and report the cause's type without reflecting its unsafe text.
            sys.stderr.write(f"candidate verification failed: {type(error).__name__}; traffic was not promoted\n")
            return 1
        return execute(commands[1])
    except FileNotFoundError:
        sys.stderr.write("deployment failed: gcloud is not installed or executable\n")
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
