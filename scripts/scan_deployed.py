"""Resolve and scan every serving Cloud Run revision with Trivy."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from scripts.deploy import DeploymentTarget, DeploymentUsageError

type CompletedProcess = subprocess.CompletedProcess[str]


class ScanError(RuntimeError):
    """A deployed image security scan precondition or command failed."""


class Runner(Protocol):
    """Command execution seam for unit testing without gcloud or Trivy."""

    def __call__(
        self,
        arguments: Sequence[str],
        *,
        capture: bool = True,
        env: Mapping[str, str] | None = None,
    ) -> CompletedProcess: ...


def default_runner(
    arguments: Sequence[str],
    *,
    capture: bool = True,
    env: Mapping[str, str] | None = None,
) -> CompletedProcess:
    """Execute fixed gcloud or Trivy commands with optional stream capture."""
    return subprocess.run(  # noqa: S603 - fixed gcloud and trivy argv only.
        tuple(arguments),
        stdin=subprocess.DEVNULL,
        capture_output=capture,
        text=True,
        check=False,
        env=dict(env) if env is not None else None,
    )


def resolve_target(environment: Mapping[str, str] = os.environ) -> DeploymentTarget:
    """Resolve deployment target coordinates with Cloud Run environment fallback."""
    region = environment.get("REGION") or environment.get("CLOUDSDK_RUN_REGION", "")
    project_id = environment.get("PROJECT_ID") or environment.get("CLOUDSDK_CORE_PROJECT", "")
    repository = environment.get("REPOSITORY", "app")
    service_name = environment.get("SERVICE_NAME", "www-fmind-dev")
    return DeploymentTarget(
        region=region,
        project_id=project_id,
        repository=repository,
        service_name=service_name,
    )


def extract_serving_revisions(service_data: object) -> list[str]:
    """Extract sorted, unique revision names receiving traffic greater than 0%."""
    traffic_items: object = None
    if isinstance(service_data, dict):
        status = service_data.get("status")
        traffic_items = status.get("traffic") if isinstance(status, dict) else service_data.get("traffic")
    elif isinstance(service_data, list):
        traffic_items = service_data

    if not isinstance(traffic_items, list):
        raise ScanError("invalid traffic format in service description")

    revisions: set[str] = set()
    for item in traffic_items:
        if not isinstance(item, dict):
            raise ScanError("invalid traffic entry in service description")
        percent = item.get("percent", 0)
        if type(percent) is not int or not 0 <= percent <= 100:
            raise ScanError("invalid traffic percentage in service description")
        if percent > 0:
            name = item.get("revisionName")
            if not isinstance(name, str) or not name:
                raise ScanError("serving traffic entry has no revision name")
            revisions.add(name)

    if not revisions:
        raise ScanError("no serving revision receiving traffic found")

    return sorted(revisions)


def validate_revision_name(revision: str, service_name: str) -> None:
    """Verify the revision name conforms to the repository service naming pattern."""
    pattern = rf"^{re.escape(service_name)}-[a-z0-9-]+\Z"
    if not re.fullmatch(pattern, revision):
        raise ScanError(f"revision name '{revision}' does not match service pattern '{service_name}-*'")


def validate_image_digest(digest: str, image_repository: str) -> None:
    """Verify the image digest matches the repository Artifact Registry repository."""
    pattern = rf"^{re.escape(image_repository)}@sha256:[a-f0-9]{{64}}\Z"
    if not re.fullmatch(pattern, digest):
        raise ScanError(f"image digest '{digest}' does not match repository '{image_repository}@sha256:<64 hex>'")


def build_service_describe_command(target: DeploymentTarget) -> tuple[str, ...]:
    """Construct gcloud command to fetch Cloud Run service traffic configuration."""
    return (
        "gcloud",
        "run",
        "services",
        "describe",
        target.service_name,
        "--project",
        target.project_id,
        "--region",
        target.region,
        "--format=json(status.traffic)",
        "--quiet",
    )


def build_revision_describe_command(revision: str, target: DeploymentTarget) -> tuple[str, ...]:
    """Construct gcloud command to fetch a revision's immutable image digest."""
    return (
        "gcloud",
        "run",
        "revisions",
        "describe",
        revision,
        "--project",
        target.project_id,
        "--region",
        target.region,
        "--format=value(status.imageDigest)",
        "--quiet",
    )


def build_trivy_evidence_command(digest: str, output_path: Path) -> tuple[str, ...]:
    """Construct Trivy command to export full advisory JSON evidence without suppression."""
    return (
        "trivy",
        "image",
        "--platform",
        "linux/amd64",
        "--scanners",
        "vuln",
        "--severity",
        "HIGH,CRITICAL",
        "--ignorefile",
        "/dev/null",
        "--format",
        "json",
        "--output",
        str(output_path),
        digest,
    )


def build_trivy_gate_command(digest: str) -> tuple[str, ...]:
    """Construct Trivy command enforcing the fixable HIGH/CRITICAL vulnerability gate."""
    return (
        "trivy",
        "image",
        "--platform",
        "linux/amd64",
        "--exit-code=1",
        "--severity",
        "HIGH,CRITICAL",
        "--ignore-unfixed",
        "--scanners",
        "vuln,secret",
        digest,
    )


def build_trivy_environment(base_environment: Mapping[str, str] = os.environ) -> dict[str, str]:
    """Unset TRIVY_CONFIG so scans do not inherit global developer configuration."""
    return {key: value for key, value in base_environment.items() if key != "TRIVY_CONFIG"}


def scan_deployed_revisions(
    target: DeploymentTarget,
    output_dir: Path,
    runner: Runner,
    *,
    environment: Mapping[str, str] = os.environ,
) -> int:
    """Resolve, record, and scan every serving revision receiving traffic."""
    output_dir.mkdir(parents=True, exist_ok=True)
    trivy_env = build_trivy_environment(environment)

    service_command = build_service_describe_command(target)
    service_process = runner(service_command, capture=True)
    if service_process.returncode != 0:
        message = service_process.stderr.strip() or f"exit status {service_process.returncode}"
        raise ScanError(f"failed to describe service {target.service_name}: {message}")

    (output_dir / "service.json").write_text(service_process.stdout, encoding="utf-8")

    try:
        service_data = json.loads(service_process.stdout)
    except json.JSONDecodeError as error:
        raise ScanError(f"invalid JSON received from service describe: {error}") from error

    revisions = extract_serving_revisions(service_data)
    (output_dir / "revisions.txt").write_text("\n".join(revisions) + "\n", encoding="utf-8")

    digests_lines: list[str] = []
    has_gate_failure = False

    for revision in revisions:
        validate_revision_name(revision, target.service_name)

        revision_command = build_revision_describe_command(revision, target)
        revision_process = runner(revision_command, capture=True)
        if revision_process.returncode != 0:
            message = revision_process.stderr.strip() or f"exit status {revision_process.returncode}"
            raise ScanError(f"failed to describe revision {revision}: {message}")

        digest = revision_process.stdout.strip()
        validate_image_digest(digest, target.image_repository)
        digests_lines.append(f"{revision} {digest}\n")

        evidence_file = output_dir / f"{revision}.json"
        evidence_command = build_trivy_evidence_command(digest, evidence_file)
        evidence_process = runner(evidence_command, capture=True, env=trivy_env)
        if evidence_process.returncode != 0:
            message = evidence_process.stderr.strip() or f"exit status {evidence_process.returncode}"
            raise ScanError(f"failed to generate advisory evidence for {digest}: {message}")

        gate_command = build_trivy_gate_command(digest)
        gate_process = runner(gate_command, capture=False, env=trivy_env)
        if gate_process.returncode != 0:
            has_gate_failure = True

    (output_dir / "digests.txt").write_text("".join(digests_lines), encoding="utf-8")

    return 1 if has_gate_failure else 0


def main(
    arguments: Sequence[str] | None = None,
    *,
    target: DeploymentTarget | None = None,
    runner: Runner | None = None,
    output_dir: Path | None = None,
    environment: Mapping[str, str] = os.environ,
) -> int:
    """Resolve targets and run deployed image security qualification."""
    del arguments
    try:
        deployment_target = target or resolve_target(environment)
    except DeploymentUsageError as error:
        sys.stderr.write(f"scan: configuration error: {error}\n")
        return 2

    command_runner = runner or default_runner
    target_output_dir = output_dir or Path("tmp/security")

    try:
        return scan_deployed_revisions(
            deployment_target,
            target_output_dir,
            command_runner,
            environment=environment,
        )
    except ScanError as error:
        sys.stderr.write(f"scan failed: {error}\n")
        return 1
    except FileNotFoundError as error:
        sys.stderr.write(f"scan failed: required executable not found: {error}\n")
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
