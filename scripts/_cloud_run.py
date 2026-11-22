"""Shared stdlib-only Cloud Run target and digest/commit/revision validators.

Used by `scripts/deploy.py`, `scripts/verify_deployment.py`, and `scripts/scan_deployed.py`
(which runs in `security.yml` without third-party packages).
"""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_CONFIG_VALUE = re.compile(r"[a-z][a-z0-9-]*[a-z0-9]\Z")
_CONFIG_NAMES = ("REGION", "PROJECT_ID", "REPOSITORY", "SERVICE_NAME")


class DeploymentUsageError(ValueError):
    """The deployment or verification request does not match the Cloud Run contract."""


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


def is_valid_revision_name(revision: str, service_name: str) -> bool:
    """Return whether `revision` matches the Cloud Run `<service>-<suffix>` naming contract."""
    return bool(re.fullmatch(rf"{re.escape(service_name)}-[a-z0-9-]+\Z", revision))


def build_service_describe_command(
    target: DeploymentTarget,
    *,
    executable: str = "gcloud",
    format_spec: str = "json",
    include_billing_project: bool = False,
) -> tuple[str, ...]:
    """Construct a fixed read-only `gcloud run services describe` argv."""
    args: list[str] = [
        executable,
        "run",
        "services",
        "describe",
        target.service_name,
        "--project",
        target.project_id,
    ]
    if include_billing_project:
        args.extend(("--billing-project", target.project_id))
    args.extend(("--region", target.region, f"--format={format_spec}", "--quiet"))
    return tuple(args)
