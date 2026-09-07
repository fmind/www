"""Tests for the deployed image security scanning script."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from scripts.deploy import DeploymentTarget, DeploymentUsageError
from scripts.scan_deployed import (
    ScanError,
    build_revision_describe_command,
    build_service_describe_command,
    build_trivy_environment,
    build_trivy_evidence_command,
    build_trivy_gate_command,
    default_runner,
    extract_serving_revisions,
    main,
    resolve_target,
    scan_deployed_revisions,
    validate_image_digest,
    validate_revision_name,
)

TARGET = DeploymentTarget(
    region="europe-west1",
    project_id="www-fmind-dev",
    repository="app",
    service_name="www-fmind-dev",
)
REVISION = "www-fmind-dev-00042-abc"
DIGEST = f"{TARGET.image_repository}@sha256:{'a' * 64}"


class FakeRunner:
    """Deterministic runner simulating gcloud and Trivy CLI behavior."""

    def __init__(
        self,
        responses: Mapping[tuple[str, ...], subprocess.CompletedProcess[str]] | None = None,
        default_returncode: int = 0,
    ) -> None:
        self.responses = dict(responses or {})
        self.default_returncode = default_returncode
        self.executed: list[tuple[str, ...]] = []
        self.envs: list[Mapping[str, str] | None] = []

    def __call__(
        self,
        arguments: Sequence[str],
        *,
        capture: bool = True,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del capture
        args = tuple(arguments)
        self.executed.append(args)
        self.envs.append(env)
        if args in self.responses:
            return self.responses[args]
        return subprocess.CompletedProcess(
            args=args,
            returncode=self.default_returncode,
            stdout="",
            stderr="",
        )


def test_resolve_target_from_standard_and_fallback_environments() -> None:
    standard_env = {
        "REGION": "europe-west1",
        "PROJECT_ID": "www-fmind-dev",
        "REPOSITORY": "app",
        "SERVICE_NAME": "www-fmind-dev",
    }
    assert resolve_target(standard_env) == TARGET

    fallback_env = {
        "CLOUDSDK_RUN_REGION": "europe-west1",
        "CLOUDSDK_CORE_PROJECT": "www-fmind-dev",
    }
    assert resolve_target(fallback_env) == TARGET

    with pytest.raises(DeploymentUsageError):
        resolve_target({})


def test_extract_serving_revisions_handles_various_formats_and_filters_zero_percent() -> None:
    data_nested = {
        "status": {
            "traffic": [
                {"percent": 100, "revisionName": "rev-b"},
                {"percent": 0, "revisionName": "rev-idle"},
                {"percent": 10, "revisionName": "rev-a"},
                {"percent": 10, "revisionName": "rev-b"},
            ],
        },
    }
    assert extract_serving_revisions(data_nested) == ["rev-a", "rev-b"]

    data_direct = {"traffic": [{"percent": 50, "revisionName": "rev-c"}]}
    assert extract_serving_revisions(data_direct) == ["rev-c"]

    data_list = [{"percent": 100, "revisionName": "rev-d"}]
    assert extract_serving_revisions(data_list) == ["rev-d"]

    with pytest.raises(ScanError, match="no serving revision"):
        extract_serving_revisions({"status": {"traffic": [{"percent": 0, "revisionName": "rev-idle"}]}})

    with pytest.raises(ScanError, match="invalid traffic format"):
        extract_serving_revisions("invalid-format")

    with pytest.raises(ScanError, match="traffic percentage"):
        extract_serving_revisions({"traffic": [{"percent": "100", "revisionName": "rev-e"}]})

    with pytest.raises(ScanError, match="no revision name"):
        extract_serving_revisions({"traffic": [{"percent": 100}]})


def test_validate_revision_name_and_image_digest() -> None:
    validate_revision_name("www-fmind-dev-00123-xyz", "www-fmind-dev")
    with pytest.raises(ScanError, match="does not match service pattern"):
        validate_revision_name("other-service-001", "www-fmind-dev")

    validate_image_digest(DIGEST, TARGET.image_repository)
    with pytest.raises(ScanError, match="does not match repository"):
        validate_image_digest("wrong-repo@sha256:123", TARGET.image_repository)


def test_build_commands_and_trivy_environment() -> None:
    service_cmd = build_service_describe_command(TARGET)
    assert service_cmd[:4] == ("gcloud", "run", "services", "describe")
    assert TARGET.service_name in service_cmd
    assert "--quiet" in service_cmd

    revision_cmd = build_revision_describe_command(REVISION, TARGET)
    assert revision_cmd[:4] == ("gcloud", "run", "revisions", "describe")
    assert REVISION in revision_cmd
    assert "--quiet" in revision_cmd

    evidence_cmd = build_trivy_evidence_command(DIGEST, Path("tmp/security/rev.json"))
    assert evidence_cmd[:4] == ("trivy", "image", "--platform", "linux/amd64")
    assert "--ignorefile" in evidence_cmd

    gate_cmd = build_trivy_gate_command(DIGEST)
    assert gate_cmd[:4] == ("trivy", "image", "--platform", "linux/amd64")
    assert "--exit-code=1" in gate_cmd

    env = build_trivy_environment({"TRIVY_CONFIG": "/path/to/config", "KEEP": "value"})
    assert "TRIVY_CONFIG" not in env
    assert env["KEEP"] == "value"


def test_scan_deployed_revisions_success_generates_all_artifacts(tmp_path: Path) -> None:
    service_payload = json.dumps({"status": {"traffic": [{"percent": 100, "revisionName": REVISION}]}})
    runner = FakeRunner(
        responses={
            build_service_describe_command(TARGET): subprocess.CompletedProcess(
                args=(), returncode=0, stdout=service_payload, stderr=""
            ),
            build_revision_describe_command(REVISION, TARGET): subprocess.CompletedProcess(
                args=(), returncode=0, stdout=f"{DIGEST}\n", stderr=""
            ),
            build_trivy_evidence_command(DIGEST, tmp_path / f"{REVISION}.json"): subprocess.CompletedProcess(
                args=(), returncode=0, stdout="{}", stderr=""
            ),
            build_trivy_gate_command(DIGEST): subprocess.CompletedProcess(
                args=(), returncode=0, stdout="OK", stderr=""
            ),
        }
    )

    exit_code = scan_deployed_revisions(TARGET, tmp_path, runner)
    assert exit_code == 0

    assert (tmp_path / "service.json").read_text(encoding="utf-8") == service_payload
    assert (tmp_path / "revisions.txt").read_text(encoding="utf-8") == f"{REVISION}\n"
    assert (tmp_path / "digests.txt").read_text(encoding="utf-8") == f"{REVISION} {DIGEST}\n"


def test_scan_deployed_revisions_handles_gate_failure(tmp_path: Path) -> None:
    service_payload = json.dumps({"status": {"traffic": [{"percent": 100, "revisionName": REVISION}]}})
    runner = FakeRunner(
        responses={
            build_service_describe_command(TARGET): subprocess.CompletedProcess(
                args=(), returncode=0, stdout=service_payload, stderr=""
            ),
            build_revision_describe_command(REVISION, TARGET): subprocess.CompletedProcess(
                args=(), returncode=0, stdout=DIGEST, stderr=""
            ),
            build_trivy_evidence_command(DIGEST, tmp_path / f"{REVISION}.json"): subprocess.CompletedProcess(
                args=(), returncode=0, stdout="{}", stderr=""
            ),
            build_trivy_gate_command(DIGEST): subprocess.CompletedProcess(
                args=(), returncode=1, stdout="VULNERABILITY", stderr=""
            ),
        }
    )

    exit_code = scan_deployed_revisions(TARGET, tmp_path, runner)
    assert exit_code == 1
    assert (tmp_path / "digests.txt").read_text(encoding="utf-8") == f"{REVISION} {DIGEST}\n"


def test_scan_deployed_revisions_propagates_failures(tmp_path: Path) -> None:
    service_cmd = build_service_describe_command(TARGET)
    failing_service_runner = FakeRunner(
        responses={
            service_cmd: subprocess.CompletedProcess(
                args=service_cmd, returncode=1, stdout="", stderr="permission denied"
            )
        }
    )
    with pytest.raises(ScanError, match="failed to describe service"):
        scan_deployed_revisions(TARGET, tmp_path, failing_service_runner)

    corrupt_json_runner = FakeRunner(
        responses={
            service_cmd: subprocess.CompletedProcess(args=service_cmd, returncode=0, stdout="{bad json", stderr="")
        }
    )
    with pytest.raises(ScanError, match="invalid JSON"):
        scan_deployed_revisions(TARGET, tmp_path, corrupt_json_runner)

    service_payload = json.dumps({"status": {"traffic": [{"percent": 100, "revisionName": REVISION}]}})
    revision_cmd = build_revision_describe_command(REVISION, TARGET)
    failing_revision_runner = FakeRunner(
        responses={
            service_cmd: subprocess.CompletedProcess(args=service_cmd, returncode=0, stdout=service_payload, stderr=""),
            revision_cmd: subprocess.CompletedProcess(args=revision_cmd, returncode=1, stdout="", stderr="not found"),
        }
    )
    with pytest.raises(ScanError, match="failed to describe revision"):
        scan_deployed_revisions(TARGET, tmp_path, failing_revision_runner)

    evidence_cmd = build_trivy_evidence_command(DIGEST, tmp_path / f"{REVISION}.json")
    failing_evidence_runner = FakeRunner(
        responses={
            service_cmd: subprocess.CompletedProcess(args=service_cmd, returncode=0, stdout=service_payload, stderr=""),
            revision_cmd: subprocess.CompletedProcess(args=revision_cmd, returncode=0, stdout=DIGEST, stderr=""),
            evidence_cmd: subprocess.CompletedProcess(args=evidence_cmd, returncode=1, stdout="", stderr="disk error"),
        }
    )
    with pytest.raises(ScanError, match="failed to generate advisory evidence"):
        scan_deployed_revisions(TARGET, tmp_path, failing_evidence_runner)


def test_main_cli_entry_points(tmp_path: Path) -> None:
    # 1. Invalid configuration
    exit_code = main(environment={"REGION": "BAD!"})
    assert exit_code == 2

    # 2. Executable not found
    def missing_runner(
        arguments: Sequence[str], *, capture: bool = True, env: Mapping[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        del arguments, capture, env
        raise FileNotFoundError("gcloud")

    exit_code = main(target=TARGET, runner=missing_runner, output_dir=tmp_path)
    assert exit_code == 127

    # 3. ScanError handling
    def scan_error_runner(
        arguments: Sequence[str], *, capture: bool = True, env: Mapping[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        del capture, env
        return subprocess.CompletedProcess(args=arguments, returncode=1, stdout="", stderr="fail")

    exit_code = main(target=TARGET, runner=scan_error_runner, output_dir=tmp_path)
    assert exit_code == 1

    # 4. Success path via main
    service_payload = json.dumps({"status": {"traffic": [{"percent": 100, "revisionName": REVISION}]}})
    success_runner = FakeRunner(
        responses={
            build_service_describe_command(TARGET): subprocess.CompletedProcess(
                args=(), returncode=0, stdout=service_payload, stderr=""
            ),
            build_revision_describe_command(REVISION, TARGET): subprocess.CompletedProcess(
                args=(), returncode=0, stdout=DIGEST, stderr=""
            ),
            build_trivy_evidence_command(DIGEST, tmp_path / f"{REVISION}.json"): subprocess.CompletedProcess(
                args=(), returncode=0, stdout="{}", stderr=""
            ),
            build_trivy_gate_command(DIGEST): subprocess.CompletedProcess(
                args=(), returncode=0, stdout="OK", stderr=""
            ),
        }
    )
    exit_code = main(target=TARGET, runner=success_runner, output_dir=tmp_path)
    assert exit_code == 0


def test_default_runner_invokes_subprocess() -> None:
    result = default_runner(
        [sys.executable, "-c", "import sys; sys.stdout.write('hello'); sys.stderr.write('err')"], capture=True
    )
    assert result.returncode == 0
    assert result.stdout == "hello"
    assert result.stderr == "err"
