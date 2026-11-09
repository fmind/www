"""Tests for the deployed image security scanning script."""

import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from scripts import scan_deployed
from scripts.deploy import DeploymentTarget
from scripts.scan_deployed import (
    ScanError,
    build_gate_command,
    build_revision_describe_command,
    build_service_describe_command,
    build_trivy_evidence_command,
    default_runner,
    extract_serving_revisions,
    main,
    scan_deployed_revisions,
    validate_revision_name,
)

TARGET = DeploymentTarget(
    region="europe-west1",
    project_id="www-fmind-dev",
    repository="app",
    service_name="www-fmind-dev",
)
ENVIRONMENT = {
    "REGION": TARGET.region,
    "PROJECT_ID": TARGET.project_id,
    "REPOSITORY": TARGET.repository,
    "SERVICE_NAME": TARGET.service_name,
}
REVISION = "www-fmind-dev-00042-abc"
DIGEST = f"{TARGET.image_repository}@sha256:{'a' * 64}"
SERVICE_PAYLOAD = json.dumps({"status": {"traffic": [{"percent": 100, "revisionName": REVISION}]}})


class FakeRunner:
    """Deterministic runner simulating gcloud, Trivy, and mise CLI behavior."""

    def __init__(self, responses: Mapping[tuple[str, ...], subprocess.CompletedProcess[str]]) -> None:
        self.responses = dict(responses)
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
        return self.responses.get(args, subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr=""))


def completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=(), returncode=returncode, stdout=stdout, stderr=stderr)


def scan_runner(output_dir: Path, **overrides: subprocess.CompletedProcess[str]) -> FakeRunner:
    """Answer the four commands of a one-revision scan; `overrides` replaces a step by name."""
    steps = {
        "service": (build_service_describe_command(TARGET), completed(stdout=SERVICE_PAYLOAD)),
        "revision": (build_revision_describe_command(REVISION, TARGET), completed(stdout=f"{DIGEST}\n")),
        "evidence": (build_trivy_evidence_command(DIGEST, output_dir / f"{REVISION}.json"), completed(stdout="{}")),
        "gate": (build_gate_command(DIGEST), completed(stdout="OK")),
    }
    return FakeRunner({command: overrides.get(name, response) for name, (command, response) in steps.items()})


def test_extract_serving_revisions_keeps_serving_and_tagged_revisions() -> None:
    data = {
        "status": {
            "traffic": [
                {"percent": 100, "revisionName": "rev-b"},
                {"percent": 0, "revisionName": "rev-idle"},
                {"percent": 10, "revisionName": "rev-a"},
                {"percent": 10, "revisionName": "rev-b"},
                # A failed candidate keeps its public tag URL at 0% traffic, so it stays in scope.
                {"percent": 0, "revisionName": "rev-f", "tag": "candidate"},
            ],
        },
    }
    assert extract_serving_revisions(data) == ["rev-a", "rev-b", "rev-f"]

    with pytest.raises(ScanError, match="no serving revision"):
        extract_serving_revisions({"status": {"traffic": [{"percent": 0, "revisionName": "rev-idle"}]}})

    # Only the `json(status.traffic)` shape is a service description.
    for malformed in ("invalid-format", [{"percent": 100, "revisionName": "rev-d"}], {"traffic": []}, {"status": []}):
        with pytest.raises(ScanError, match="invalid traffic format"):
            extract_serving_revisions(malformed)

    with pytest.raises(ScanError, match="traffic percentage"):
        extract_serving_revisions({"status": {"traffic": [{"percent": "100", "revisionName": "rev-e"}]}})

    with pytest.raises(ScanError, match="no revision name"):
        extract_serving_revisions({"status": {"traffic": [{"percent": 100}]}})


def test_validate_revision_name() -> None:
    validate_revision_name("www-fmind-dev-00123-xyz", "www-fmind-dev")
    with pytest.raises(ScanError, match="does not match service pattern"):
        validate_revision_name("other-service-001", "www-fmind-dev")


def test_scan_records_evidence_and_gates_each_digest_without_the_global_trivy_config(tmp_path: Path) -> None:
    runner = scan_runner(tmp_path)

    exit_code = scan_deployed_revisions(
        TARGET, tmp_path, runner, environment={"TRIVY_CONFIG": "/path/to/config", "KEEP": "value"}
    )

    assert exit_code == 0
    assert (tmp_path / "service.json").read_text(encoding="utf-8") == SERVICE_PAYLOAD
    assert (tmp_path / "revisions.txt").read_text(encoding="utf-8") == f"{REVISION}\n"
    assert (tmp_path / "digests.txt").read_text(encoding="utf-8") == f"{REVISION} {DIGEST}\n"
    evidence, gate = runner.executed[2:]
    # The evidence export ignores the repository's suppressions; the gate is the task CI runs before a deploy.
    assert evidence[:2] == ("trivy", "image")
    assert evidence[evidence.index("--ignorefile") + 1] == "/dev/null"
    assert gate == ("mise", "run", "check:image:digest", DIGEST)
    assert runner.envs[2:] == [{"KEEP": "value"}, {"KEEP": "value"}]


def test_scan_reports_a_failed_gate_after_recording_the_digest(tmp_path: Path) -> None:
    runner = scan_runner(tmp_path, gate=completed(returncode=1, stdout="VULNERABILITY"))

    assert scan_deployed_revisions(TARGET, tmp_path, runner) == 1
    assert (tmp_path / "digests.txt").read_text(encoding="utf-8") == f"{REVISION} {DIGEST}\n"


@pytest.mark.parametrize(
    ("step", "response", "message", "digests"),
    [
        ("service", completed(1, stderr="permission denied"), "failed to describe service", None),
        ("service", completed(stdout="{bad json"), "invalid JSON", None),
        ("revision", completed(1, stderr="not found"), "failed to describe revision", ""),
        ("revision", completed(stdout="wrong-repo@sha256:123"), "serves an unexpected image", ""),
        # The digest resolved before the failure stays in the uploaded evidence.
        (
            "evidence",
            completed(1, stderr="disk error"),
            "failed to generate advisory evidence",
            f"{REVISION} {DIGEST}\n",
        ),
    ],
    ids=("service", "service-json", "revision", "foreign-image", "evidence"),
)
def test_scan_stops_at_the_first_failed_step(
    tmp_path: Path, step: str, response: subprocess.CompletedProcess[str], message: str, digests: str | None
) -> None:
    runner = scan_runner(tmp_path, **{step: response})

    with pytest.raises(ScanError, match=message):
        scan_deployed_revisions(TARGET, tmp_path, runner)

    recorded = tmp_path / "digests.txt"
    assert (recorded.read_text(encoding="utf-8") if recorded.exists() else None) == digests
    assert build_gate_command(DIGEST) not in runner.executed


def test_main_cli_entry_points(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # 1. Invalid or missing configuration fails closed: mise `[env]` always sets the four names.
    assert main(environment={**ENVIRONMENT, "REGION": "BAD!"}) == 2
    assert main(environment={name: value for name, value in ENVIRONMENT.items() if name != "SERVICE_NAME"}) == 2
    assert capsys.readouterr().err == (
        "scan: configuration error: REGION is missing or invalid\n"
        "scan: configuration error: SERVICE_NAME is missing or invalid\n"
    )

    # 2. Executable not found
    def missing_runner(
        arguments: Sequence[str], *, capture: bool = True, env: Mapping[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        del arguments, capture, env
        raise FileNotFoundError("gcloud")

    assert main(target=TARGET, runner=missing_runner, output_dir=tmp_path) == 127

    # 3. ScanError handling
    failing = scan_runner(tmp_path, service=completed(1, stderr="fail"))
    assert main(target=TARGET, runner=failing, output_dir=tmp_path) == 1

    # 4. Success path via main, with the target read from the environment
    assert main(runner=scan_runner(tmp_path), output_dir=tmp_path, environment=ENVIRONMENT) == 0


def test_default_runner_captures_output_and_bounds_a_hung_command(monkeypatch: pytest.MonkeyPatch) -> None:
    result = default_runner(
        [sys.executable, "-c", "import sys; sys.stdout.write('hello'); sys.stderr.write('err')"], capture=True
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "hello", "err")

    monkeypatch.setattr(scan_deployed, "COMMAND_TIMEOUT_SECONDS", 0.2)
    with pytest.raises(ScanError, match=r"timed out after 0\.2s; check network access and rerun") as failure:
        default_runner([sys.executable, "-c", "import time; time.sleep(60)"])
    assert isinstance(failure.value.__cause__, subprocess.TimeoutExpired)


def test_script_imports_with_the_standard_library_only() -> None:
    # security.yml installs only python and trivy for this task: no uv environment, so no third-party package.
    program = "import sys; assert not any('site-packages' in entry for entry in sys.path); import scripts.scan_deployed"

    result = subprocess.run(  # noqa: S603 - fixed interpreter and program
        [sys.executable, "-S", "-E", "-c", program],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
