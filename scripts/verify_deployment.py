"""Verify that an expected immutable release owns the ready production traffic.

`candidate` mode runs before promotion: it proves that the no-traffic revision
under CANDIDATE_TAG is the qualified release and serves health/discovery on its
tagged URL. The default mode runs after promotion against the public origin and
also completes one MCP initialize there, because /mcp accepts only the public host.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx2

from scripts.deploy import DeploymentTarget, DeploymentUsageError, validate_commit, validate_image_reference

PUBLIC_ORIGIN = "https://www.fmind.dev"
PROBE_PATHS = ("/health", "/api/profile", "/.well-known/mcp/server-card.json")
MCP_PATH = "/mcp"
_MCP_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "verify-deployment", "version": "1.0"},
    },
}
_REQUIRED_ENVIRONMENT = {
    "IMAGE_REF": "the qualified <repository>@sha256:<digest> image reference",
    "GITHUB_SHA": "the full commit SHA that image was built from",
    "CANDIDATE_TAG": "the traffic tag of the no-traffic revision (CI uses `candidate`)",
}
_TAG = re.compile(r"[a-z][a-z0-9-]*[a-z0-9]\Z")
_USAGE = "usage: python -m scripts.verify_deployment [candidate]\n"


class VerificationError(ValueError):
    """A public release invariant failed, with a safe diagnostic."""


def _verify_latest_revision(service: Mapping[str, Any], image: str, commit: str) -> str:
    """Require the newest revision to be ready, observed, qualified, and within capacity policy."""
    status = service["status"]
    revision = status["latestReadyRevisionName"]
    if not isinstance(revision, str) or not revision or revision != status["latestCreatedRevisionName"]:
        raise VerificationError("latest revision is not ready")
    if not any(item.get("type") == "Ready" and item.get("status") == "True" for item in status["conditions"]):
        raise VerificationError("service is not ready")
    if status["observedGeneration"] != service["metadata"]["generation"]:
        raise VerificationError("latest service configuration has not been observed")
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


def verify_service(service: Mapping[str, Any], image: str, commit: str) -> str:
    """Reject incomplete rollouts, stale releases, and capacity drift."""
    revision = _verify_latest_revision(service, image, commit)
    traffic = service["status"]["traffic"]
    if sum(item.get("percent", 0) for item in traffic) != 100 or any(
        item.get("percent", 0) > 0 and item.get("revisionName") != revision for item in traffic
    ):
        raise VerificationError("expected revision does not own all traffic")
    return revision


def verify_candidate(
    service: Mapping[str, Any], image: str, commit: str, *, tag: str, service_name: str
) -> tuple[str, str]:
    """Return the qualified no-traffic revision and its tagged run.app URL."""
    revision = _verify_latest_revision(service, image, commit)
    tagged = [item for item in service["status"]["traffic"] if item.get("tag") == tag]
    if len(tagged) != 1 or tagged[0].get("revisionName") != revision:
        raise VerificationError("candidate tag does not address the latest ready revision")
    if any(
        item.get("revisionName") == revision and item.get("percent", 0) > 0 for item in service["status"]["traffic"]
    ):
        raise VerificationError("candidate already receives production traffic")
    # Probe only this service's tagged run.app host, never an arbitrary URL.
    url_pattern = rf"https://{re.escape(tag)}---{re.escape(service_name)}-[a-z0-9-]+(?:\.[a-z0-9-]+)*\.run\.app\Z"
    url = tagged[0].get("url")
    if not isinstance(url, str) or not re.fullmatch(url_pattern, url):
        raise VerificationError("candidate tag has no run.app URL for this service")
    if not re.fullmatch(rf"{re.escape(service_name)}-[a-z0-9-]+\Z", revision):
        raise VerificationError("candidate revision name does not belong to this service")
    return revision, url


def probe(origin: str, *, timeout: float) -> None:
    """Require JSON health, profile, and MCP server card responses from one origin."""
    with httpx2.Client(timeout=timeout, follow_redirects=False) as client:
        for path in PROBE_PATHS:
            response = client.get(origin + path)
            response.raise_for_status()
            document = response.json()
            if response.status_code != 200 or not isinstance(document, dict):
                raise VerificationError(f"invalid response at {path}")
            if path == "/health" and document != {"status": "ok"}:
                raise VerificationError("health check is not healthy")


def probe_mcp(origin: str, *, timeout: float) -> None:
    """POST one finite MCP initialize with the public Host and Origin that real clients use."""
    with httpx2.Client(timeout=timeout, follow_redirects=False) as client:
        response = client.post(
            origin + MCP_PATH,
            json=_MCP_INITIALIZE,
            headers={"accept": "application/json, text/event-stream", "origin": origin},
        )
        response.raise_for_status()
        document = response.json()
    result = document.get("result") if isinstance(document, dict) else None
    server_info = result.get("serverInfo") if isinstance(result, dict) else None
    if response.status_code != 200 or not isinstance(server_info, dict) or server_info.get("name") != "www":
        raise VerificationError("MCP initialize did not return the www server")


def describe_service(target: DeploymentTarget) -> dict[str, Any]:
    """Read the Cloud Run service through a fixed read-only gcloud argv."""
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
    document = json.loads(result.stdout)
    if not isinstance(document, dict):
        raise VerificationError("service description is not an object")
    return document


def _record_output(revision: str, environment: Mapping[str, str]) -> None:
    """Expose the verified revision to a later GitHub Actions promotion step."""
    if output := environment.get("GITHUB_OUTPUT"):
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(f"revision={revision}\n")


def _required(name: str, environment: Mapping[str, str]) -> str:
    """Name a missing variable and its expected value instead of reporting a bare KeyError."""
    if value := environment.get(name):
        return value
    raise VerificationError(f"{name} is not set; export it as {_REQUIRED_ENVIRONMENT[name]}")


def main(arguments: Sequence[str] = ()) -> int:
    """Use read-only Cloud Run metadata and bounded HTTP requests; never mutate traffic."""
    if tuple(arguments) not in {(), ("candidate",)}:
        sys.stderr.write(_USAGE)
        return 2
    candidate = bool(arguments)
    try:
        target = DeploymentTarget.from_environment()
        image = validate_image_reference(_required("IMAGE_REF", os.environ), target)
        commit = validate_commit(_required("GITHUB_SHA", os.environ))
        if candidate:
            tag = _required("CANDIDATE_TAG", os.environ)
            if not _TAG.fullmatch(tag):
                raise VerificationError("CANDIDATE_TAG is invalid")
            revision, url = verify_candidate(
                describe_service(target), image, commit, tag=tag, service_name=target.service_name
            )
            # A zero-traffic revision may cold start; allow the 60s startup-probe budget.
            probe(url, timeout=65)
            _record_output(revision, os.environ)
            sys.stdout.write(f"Verified candidate {revision}: {commit}, {image}, tagged health/discovery\n")
        else:
            revision = verify_service(describe_service(target), image, commit)
            probe(PUBLIC_ORIGIN, timeout=15)
            probe_mcp(PUBLIC_ORIGIN, timeout=15)
            sys.stdout.write(
                f"Verified {revision}: {commit}, {image}, 100% traffic, scale-to-zero, public health/discovery/MCP\n"
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
        detail = str(error) if isinstance(error, VerificationError | DeploymentUsageError) else type(error).__name__
        sys.stderr.write(f"deployment verification failed: {detail}; inspect revision and public health\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
