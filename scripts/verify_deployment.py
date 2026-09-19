"""Verify that an expected immutable release owns the ready production traffic."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from typing import Any

import httpx2

from scripts.deploy import DeploymentTarget, build_deploy_command


class VerificationError(ValueError):
    """A public release invariant failed, with a safe diagnostic."""


def verify_service(service: Mapping[str, Any], image: str, commit: str) -> str:
    """Reject incomplete rollouts, stale releases, and capacity drift."""
    status = service["status"]
    revision = status["latestReadyRevisionName"]
    if not isinstance(revision, str) or not revision or revision != status["latestCreatedRevisionName"]:
        raise VerificationError("latest revision is not ready")
    if not any(item.get("type") == "Ready" and item.get("status") == "True" for item in status["conditions"]):
        raise VerificationError("service is not ready")
    if status["observedGeneration"] != service["metadata"]["generation"]:
        raise VerificationError("latest service configuration has not been observed")
    traffic = status["traffic"]
    if sum(item.get("percent", 0) for item in traffic) != 100 or any(
        item.get("percent", 0) > 0 and item.get("revisionName") != revision for item in traffic
    ):
        raise VerificationError("expected revision does not own all traffic")
    template = service["spec"]["template"]
    if template["spec"]["containers"][0]["image"] != image:
        raise VerificationError("deployed image differs from qualified digest")
    if template["metadata"]["labels"].get("commit-sha") != commit:
        raise VerificationError("deployed commit differs from qualified commit")
    service_annotations = service["metadata"].get("annotations", {})
    revision_annotations = template["metadata"].get("annotations", {})
    if (
        service_annotations.get("run.googleapis.com/minScale", "0") != "0"
        or service_annotations.get("run.googleapis.com/maxScale") != "5"
        or revision_annotations.get("autoscaling.knative.dev/minScale", "0") != "0"
        or revision_annotations.get("autoscaling.knative.dev/maxScale") != "5"
        or revision_annotations.get("run.googleapis.com/cpu-throttling", "true") != "true"
    ):
        raise VerificationError("deployed scaling or CPU policy differs from the runtime contract")
    return revision


def main() -> int:
    """Use read-only Cloud Run metadata and bounded public health requests."""
    try:
        target = DeploymentTarget.from_environment()
        image = os.environ["IMAGE_REF"]
        commit = os.environ["GITHUB_SHA"]
        build_deploy_command((image,), target)  # Reuse the repository's digest boundary; never execute it.
        if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
            raise VerificationError("expected commit must be a full lowercase SHA")
        executable = shutil.which("gcloud")
        if executable is None:
            raise FileNotFoundError("gcloud is not installed")
        result = subprocess.run(  # noqa: S603 - fixed read-only gcloud argv.
            (
                executable,
                "run",
                "services",
                "describe",
                target.service_name,
                "--project",
                target.project_id,
                "--billing-project",
                target.project_id,
                "--region",
                target.region,
                "--format=json",
                "--quiet",
            ),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        revision = verify_service(json.loads(result.stdout), image, commit)
        with httpx2.Client(timeout=15, follow_redirects=False) as client:
            for path in ("/health", "/api/profile", "/.well-known/mcp/server-card.json"):
                response = client.get("https://www.fmind.dev" + path)
                response.raise_for_status()
                document = response.json()
                if response.status_code != 200 or not isinstance(document, dict):
                    raise VerificationError(f"invalid public response at {path}")
                if path == "/health" and document != {"status": "ok"}:
                    raise VerificationError("public health check is not healthy")
        sys.stdout.write(
            f"Verified {revision}: {commit}, {image}, 100% traffic, scale-to-zero, public health/discovery\n"
        )
    except (
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        OSError,
        subprocess.SubprocessError,
        httpx2.HTTPError,
    ) as error:
        # Only our own invariant messages are safe; provider diagnostics may contain private data.
        detail = str(error) if isinstance(error, VerificationError) else type(error).__name__
        sys.stderr.write(f"deployment verification failed: {detail}; inspect revision and public health\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
