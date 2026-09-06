"""Fail-closed argument boundary for manual Cloud Run rollouts."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CONFIG_VALUE = re.compile(r"[a-z][a-z0-9-]*[a-z0-9]\Z")
_CONFIG_NAMES = ("REGION", "PROJECT_ID", "REPOSITORY", "SERVICE_NAME")
_USAGE = "usage: mise run deploy <digest-ref>\n"


class DeploymentUsageError(ValueError):
    """The manual deployment request does not match the one-digest contract."""


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


class Runner(Protocol):
    """Narrow process seam that keeps contract tests away from gcloud."""

    def run(self, arguments: Sequence[str]) -> int: ...


class SubprocessRunner:
    """Run the already-validated gcloud command with inherited streams and signals."""

    def run(self, arguments: Sequence[str]) -> int:
        return subprocess.run(tuple(arguments), check=False).returncode  # noqa: S603 - fixed gcloud argv only.


def build_deploy_command(arguments: Sequence[str], target: DeploymentTarget) -> tuple[str, ...]:
    """Validate one immutable repository digest and return the fixed gcloud argv."""
    if len(arguments) != 1:
        raise DeploymentUsageError("exactly one image reference is required")

    image_reference = arguments[0]
    repository, separator, digest = image_reference.rpartition("@")
    if separator != "@" or repository != target.image_repository or not _DIGEST.fullmatch(digest):
        raise DeploymentUsageError(f"image must match {target.image_repository}@sha256:<64 lowercase hex>")

    return (
        "gcloud",
        "run",
        "services",
        "update",
        target.service_name,
        "--project",
        target.project_id,
        "--billing-project",
        target.project_id,
        "--region",
        target.region,
        "--image",
        image_reference,
        "--quiet",
    )


def main(
    arguments: Sequence[str] | None = None,
    *,
    target: DeploymentTarget | None = None,
    runner: Runner | None = None,
) -> int:
    """Validate first, then invoke gcloud exactly once."""
    try:
        deployment_target = target or DeploymentTarget.from_environment()
        command = build_deploy_command(sys.argv[1:] if arguments is None else arguments, deployment_target)
    except DeploymentUsageError as error:
        sys.stderr.write(f"{_USAGE}deploy: {error}\n")
        return 2

    try:
        return (runner or SubprocessRunner()).run(command)
    except FileNotFoundError:
        sys.stderr.write("deployment failed: gcloud is not installed or executable\n")
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
