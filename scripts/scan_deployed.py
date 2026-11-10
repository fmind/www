"""Resolve and scan every serving Cloud Run revision with Trivy."""

import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from scripts.deploy import DeploymentTarget, DeploymentUsageError, validate_image_reference

type CompletedProcess = subprocess.CompletedProcess[str]
# A Trivy scan pulls the image and may download its database; the scheduled job allows 20 minutes in total.
COMMAND_TIMEOUT_SECONDS: float = 600


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
    """Execute fixed gcloud or Trivy commands with optional stream capture, for at most COMMAND_TIMEOUT_SECONDS."""
    try:
        return subprocess.run(  # noqa: S603 - fixed gcloud and trivy argv only.
            tuple(arguments),
            stdin=subprocess.DEVNULL,
            capture_output=capture,
            text=True,
            check=False,
            env=dict(env) if env is not None else None,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise ScanError(
            f"{arguments[0]} timed out after {COMMAND_TIMEOUT_SECONDS:g}s; check network access and rerun the scan"
        ) from error


def extract_serving_revisions(service_data: object) -> list[str]:
    """Extract sorted, unique revision names receiving traffic or reachable through a public tag URL."""
    # `--format=json(status.traffic)` always nests the list under `status`.
    status = service_data.get("status") if isinstance(service_data, dict) else None
    traffic_items = status.get("traffic") if isinstance(status, dict) else None
    if not isinstance(traffic_items, list):
        raise ScanError("invalid traffic format in service description")

    revisions: set[str] = set()
    for item in traffic_items:
        if not isinstance(item, dict):
            raise ScanError("invalid traffic entry in service description")
        percent = item.get("percent", 0)
        if type(percent) is not int or not 0 <= percent <= 100:
            raise ScanError("invalid traffic percentage in service description")
        # A tagged revision stays public on its tag URL even at 0%, such as a failed candidate.
        if percent > 0 or item.get("tag"):
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


def build_gate_command(digest: str) -> tuple[str, ...]:
    """Reuse the `check:image:digest` task, the single owner of the fixable HIGH/CRITICAL image gate."""
    return ("mise", "run", "check:image:digest", digest)


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

    has_gate_failure = False

    # Closing the file on any exit keeps the digests resolved before a failure in the uploaded evidence.
    with (output_dir / "digests.txt").open("w", encoding="utf-8") as digests:
        for revision in revisions:
            validate_revision_name(revision, target.service_name)

            revision_command = build_revision_describe_command(revision, target)
            revision_process = runner(revision_command, capture=True)
            if revision_process.returncode != 0:
                message = revision_process.stderr.strip() or f"exit status {revision_process.returncode}"
                raise ScanError(f"failed to describe revision {revision}: {message}")

            digest = revision_process.stdout.strip()
            try:
                validate_image_reference(digest, target)
            except DeploymentUsageError as error:
                raise ScanError(f"revision {revision} serves an unexpected image: {error}") from error
            digests.write(f"{revision} {digest}\n")

            evidence_file = output_dir / f"{revision}.json"
            evidence_command = build_trivy_evidence_command(digest, evidence_file)
            evidence_process = runner(evidence_command, capture=True, env=trivy_env)
            if evidence_process.returncode != 0:
                message = evidence_process.stderr.strip() or f"exit status {evidence_process.returncode}"
                raise ScanError(f"failed to generate advisory evidence for {digest}: {message}")

            gate_process = runner(build_gate_command(digest), capture=False, env=trivy_env)
            if gate_process.returncode != 0:
                has_gate_failure = True

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
    if list(sys.argv[1:] if arguments is None else arguments):
        sys.stderr.write("usage: python -m scripts.scan_deployed\n")
        return 2
    try:
        deployment_target = target or DeploymentTarget.from_environment(environment)
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
