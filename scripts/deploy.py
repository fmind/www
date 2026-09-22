"""Fail-closed argument boundary for manual Cloud Run rollouts."""

from __future__ import annotations

import os
import re
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


def build_deploy_commands(arguments: Sequence[str], target: DeploymentTarget) -> tuple[tuple[str, ...], ...]:
    """Validate one digest and its commit, then return the fixed gcloud argv sequence.

    The first command creates a revision with the qualified image and restamps
    the commit label that release verification reads. CI pins traffic to its
    verified revision, so a new revision would otherwise receive no traffic;
    the second command routes all traffic to the revision just created.
    """
    if len(arguments) != 2:
        raise DeploymentUsageError("exactly one image reference and one commit SHA are required")

    image_reference = validate_image_reference(arguments[0], target)
    commit = validate_commit(arguments[1])
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
            "--quiet",
        ),
        ("gcloud", "run", "services", "update-traffic", *scope, "--to-latest", "--quiet"),
    )


def main(
    arguments: Sequence[str] | None = None,
    *,
    target: DeploymentTarget | None = None,
    runner: Runner | None = None,
) -> int:
    """Validate first, then run each gcloud step, stopping at the first failure."""
    try:
        deployment_target = target or DeploymentTarget.from_environment()
        commands = build_deploy_commands(sys.argv[1:] if arguments is None else arguments, deployment_target)
    except DeploymentUsageError as error:
        sys.stderr.write(f"{_USAGE}deploy: {error}\n")
        return 2

    execute = runner or run_command
    try:
        for command in commands:
            if returncode := execute(command):
                return returncode
    except FileNotFoundError:
        sys.stderr.write("deployment failed: gcloud is not installed or executable\n")
        return 127
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
