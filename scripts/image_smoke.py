"""Smoke-test the already-built production image archive through Docker."""

from __future__ import annotations

import asyncio
import http.client
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from tempfile import TemporaryFile
from types import FrameType
from typing import NoReturn, Protocol, cast, override

import anyio
import httpx2
from anyio import to_thread
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp_types import Implementation, TextContent, TextResourceContents

from www.mcp import MCP_PROFILE_URI, MCP_PROTOCOL_VERSION

# This is a repository qualification command, so resolve its artifact from the
# task working directory rather than from an editable-install source path.
IMAGE_ARCHIVE = Path("tmp/www-image.tar")
CONTAINER_PORT = 8080
EXPECTED_UID = 10001
HEALTH_TIMEOUT_SECONDS = 120
COMMAND_OUTPUT_LIMIT = 16 * 1024
RESPONSE_BODY_LIMIT = 2 * 1024 * 1024
OTEL_ENDPOINT_NAMES = {
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
}
HOMEPAGE_TITLE_PREFIX = "<title>Médéric Hurier (Fmind)".encode()
_IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
_IMAGE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_IMAGE_REFERENCE_CHARS = re.compile(r"[A-Za-z0-9_./:@-]+\Z")
_CONTAINER_ID = re.compile(r"[0-9a-f]{12,64}\Z")
_ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_EXPECTED_MCP_TOOLS = frozenset(("get_profile", "search_articles"))
_EXPECTED_MCP_PROMPTS = frozenset(("assess_fit", "brief_me"))
_MCP_SEARCH_QUERY = "kubeflow"
_MCP_FIT_BRIEF = "Secure an enterprise agent platform"
_READ_ONLY_FILE_PROBE = """\
import errno
import os
import stat
from pathlib import Path

for path in Path("/usr").rglob("*"):
    if path.is_file() and path.stat().st_mode & (stat.S_ISUID | stat.S_ISGID):
        raise SystemExit(4)

paths = (
    Path("/app/.venv/lib/python3.14/site-packages/www/app.py"),
    next(Path("/app/content/articles").glob("*.md"), Path("/missing-content")),
    Path("/app/static/dist/styles.css"),
)
for path in paths:
    if not path.is_file():
        raise SystemExit(2)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND)
    except OSError as error:
        if error.errno in {errno.EACCES, errno.EPERM, errno.EROFS}:
            continue
        raise
    os.close(descriptor)
    raise SystemExit(3)
"""


class SmokeError(RuntimeError):
    """A safe, user-facing image qualification failure."""


class TerminationRequestedError(SmokeError):
    """A termination signal received while a container may be running."""

    def __init__(self, signal_number: int) -> None:
        self.signal_number = signal_number
        super().__init__(f"received {signal.Signals(signal_number).name}")


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Bounded output from one argument-vector process invocation."""

    returncode: int
    output: str


class Runner(Protocol):
    """Narrow command seam used by Docker-free unit tests."""

    def run(self, arguments: Sequence[str], *, timeout: float, check: bool = True) -> CommandResult: ...


class SubprocessRunner:
    """Run commands without a shell while retaining only a bounded output tail."""

    def run(self, arguments: Sequence[str], *, timeout: float, check: bool = True) -> CommandResult:
        if not arguments:
            raise ValueError("command arguments must not be empty")
        label = " ".join(arguments[:2])
        with TemporaryFile() as output:
            process = subprocess.Popen(  # noqa: S603 - every caller supplies fixed Docker argv.
                tuple(arguments),
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                shell=False,
            )
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as error:
                _terminate_process(process)
                raise SmokeError(f"{label} timed out after {timeout:g} seconds") from error
            except BaseException:
                _terminate_process(process)
                raise

            size = output.tell()
            output.seek(max(0, size - COMMAND_OUTPUT_LIMIT))
            bounded_output = output.read(COMMAND_OUTPUT_LIMIT).decode("utf-8", errors="replace")

        if check and returncode != 0:
            # Docker diagnostics may echo credentials from a misconfigured host;
            # keep the public failure bounded to the command and exit status.
            raise SmokeError(f"{label} failed with exit code {returncode}")
        return CommandResult(returncode=returncode, output=bounded_output)


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def parse_loaded_reference(output: str) -> str:
    """Extract exactly one image reference reported by `docker image load`."""
    prefixes = ("Loaded image: ", "Loaded image ID: ")
    references = {
        line.removeprefix(prefix).strip()
        for line in output.splitlines()
        for prefix in prefixes
        if line.startswith(prefix)
    }
    if not references:
        raise SmokeError("docker image load did not report a loaded image reference")
    if len(references) != 1:
        raise SmokeError("docker image load reported multiple image references")
    reference = references.pop()
    if not reference or len(reference) > 512 or any(character.isspace() for character in reference):
        raise SmokeError("docker image load reported an invalid image reference")
    return reference


def validate_image_reference(reference: str) -> None:
    """Ensure the target image reference is safe and well-formed."""
    if not reference or len(reference) > 512 or any(character.isspace() for character in reference):
        raise SmokeError("invalid image reference")
    if not _IMAGE_REFERENCE_CHARS.fullmatch(reference):
        raise SmokeError(f"image reference contains invalid characters: {reference!r}")
    if "@" in reference:
        repository, _, digest = reference.rpartition("@")
        if not repository or not _IMAGE_DIGEST.fullmatch(digest):
            raise SmokeError(f"invalid image digest: {digest}")


def _is_archive_target(target: str | Path | None) -> bool:
    if target is None:
        return True
    path = Path(target)
    return path.suffix == ".tar" or path.is_file()


def resolve_image_id(runner: Runner, target: str | Path | None = None) -> str:
    """Resolve the immutable Docker image ID from an archive or remote reference."""
    if _is_archive_target(target):
        archive_path = Path(target) if target is not None else IMAGE_ARCHIVE
        if archive_path.is_symlink() or not archive_path.is_file():
            raise SmokeError(f"{archive_path} is missing; run mise run check:image first")
        load = runner.run(("docker", "image", "load", "--input", os.fspath(archive_path)), timeout=120)
        reference = parse_loaded_reference(load.output)
        return parse_image_id(
            runner.run(("docker", "image", "inspect", "--format", "{{.Id}}", reference), timeout=30).output
        )

    image_reference = str(target).strip()
    validate_image_reference(image_reference)
    runner.run(("docker", "pull", "--platform", "linux/amd64", image_reference), timeout=180)
    return parse_image_id(
        runner.run(("docker", "image", "inspect", "--format", "{{.Id}}", image_reference), timeout=30).output
    )


def parse_image_id(output: str) -> str:
    """Require one immutable Docker image ID."""
    image_id = output.strip()
    if not _IMAGE_ID.fullmatch(image_id):
        raise SmokeError("docker image inspect did not return a valid image ID")
    return image_id


def parse_configured_user(output: str) -> tuple[int, int]:
    """Require the image's configured numeric UID and GID to be 10001."""
    try:
        value = json.loads(output)
    except json.JSONDecodeError as error:
        raise SmokeError("image runtime user must be configured as 10001:10001") from error
    if value != f"{EXPECTED_UID}:{EXPECTED_UID}":
        raise SmokeError("image runtime user must be configured as 10001:10001")
    return EXPECTED_UID, EXPECTED_UID


def exporter_environment_names(output: str) -> tuple[str, ...]:
    """Return every exporter variable that must be blanked for the smoke run."""
    try:
        values = json.loads(output)
    except json.JSONDecodeError as error:
        raise SmokeError("docker image inspect returned invalid environment metadata") from error
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise SmokeError("docker image inspect returned invalid environment metadata")

    names = set(OTEL_ENDPOINT_NAMES)
    for item in cast(list[str], values):
        name, separator, _ = item.partition("=")
        if separator and name.startswith("OTEL_EXPORTER_") and _ENVIRONMENT_NAME.fullmatch(name):
            names.add(name)
    return tuple(sorted(names))


def parse_container_id(output: str) -> str:
    """Require the detached container ID without exposing Docker output."""
    container_id = output.strip()
    if not _CONTAINER_ID.fullmatch(container_id):
        raise SmokeError("docker run did not return a valid container ID")
    return container_id


def parse_published_port(output: str) -> int:
    """Require one Docker-assigned TCP port bound only to IPv4 loopback."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) != 1:
        raise SmokeError("docker did not report exactly one published port")
    host, separator, raw_port = lines[0].rpartition(":")
    if separator != ":" or host != "127.0.0.1" or not raw_port.isascii() or not raw_port.isdecimal():
        raise SmokeError("docker published port must use 127.0.0.1")
    port = int(raw_port)
    if not 1 <= port <= 65535:
        raise SmokeError("docker published port must be between 1 and 65535")
    return port


@contextmanager
def container_guard(runner: Runner, name: str) -> Iterator[None]:
    """Force-remove the uniquely named container on every exit path."""
    body_error: BaseException | None = None
    try:
        yield
    except BaseException as error:
        body_error = error
        raise
    finally:
        try:
            result = runner.run(
                ("docker", "container", "rm", "--force", "--volumes", name),
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                raise SmokeError("could not remove smoke container")
        except SmokeError as cleanup_error:
            if body_error is None:
                raise
            body_error.add_note(str(cleanup_error))


def wait_for_health(
    probe: Callable[[], None],
    is_running: Callable[[], bool],
    *,
    timeout_seconds: float,
    interval_seconds: float,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> None:
    """Poll a health probe until success, container exit, or the fixed deadline."""
    deadline = monotonic() + timeout_seconds
    while True:
        try:
            probe()
            return
        except OSError, SmokeError:
            if not is_running():
                raise SmokeError("container exited before becoming healthy") from None

        remaining = deadline - monotonic()
        if remaining <= 0:
            raise SmokeError(f"container did not become healthy within {timeout_seconds:g} seconds")
        sleep(min(interval_seconds, remaining))


@dataclass(frozen=True, slots=True)
class HTTPResponse:
    status: int
    headers: dict[str, str]
    body: bytes


def _request(
    port: int, method: str, path: str, *, body: bytes | None = None, headers: dict[str, str] | None = None
) -> HTTPResponse:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        response_body = response.read(RESPONSE_BODY_LIMIT + 1)
        if len(response_body) > RESPONSE_BODY_LIMIT:
            raise SmokeError(f"{path} response exceeded {RESPONSE_BODY_LIMIT} bytes")
        return HTTPResponse(
            status=response.status,
            headers={name.lower(): value for name, value in response.getheaders()},
            body=response_body,
        )
    except (http.client.HTTPException, OSError) as error:
        raise SmokeError(f"{path} request failed ({type(error).__name__})") from error
    finally:
        connection.close()


def _expect_ok(response: HTTPResponse, path: str) -> None:
    if response.status != http.client.OK:
        raise SmokeError(f"{path} returned HTTP {response.status}, expected 200")


class _LocalTransport(httpx2.AsyncBaseTransport):
    """Give the SDK the same bounded, loopback-only HTTP boundary as page probes."""

    def __init__(self, port: int) -> None:
        self.port = port

    @override
    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        # Cancellation must return control to the container guard immediately.
        # asyncio's executor shutdown otherwise waits for a stalled socket before
        # cleanup can terminate the peer and release that connection.
        response = await to_thread.run_sync(
            partial(
                _request,
                self.port,
                request.method,
                request.url.raw_path.decode("ascii"),
                body=await request.aread(),
                headers=dict(request.headers),
            ),
            abandon_on_cancel=True,
        )
        return httpx2.Response(response.status, headers=response.headers, content=response.body, request=request)


async def _probe_mcp(port: int) -> None:
    # The transport bounds each read and response size; the enclosing deadline
    # also bounds the complete protocol exchange, including SDK retries.
    with anyio.fail_after(30):
        async with (
            httpx2.AsyncClient(transport=_LocalTransport(port), trust_env=False) as client,
            streamable_http_client(f"http://127.0.0.1:{port}/mcp", http_client=client) as streams,
            ClientSession(
                *streams, read_timeout_seconds=5, client_info=Implementation(name="image-smoke", version="1.0")
            ) as session,
        ):
            discovery = await session.discover()
            if session.protocol_version != MCP_PROTOCOL_VERSION:
                raise SmokeError(f"MCP server/discover did not advertise {MCP_PROTOCOL_VERSION}")
            if session.server_info is None or session.server_info.name != "www":
                raise SmokeError("MCP server/discover returned an unexpected server identity")
            capabilities = discovery.capabilities
            if capabilities.tools is None or capabilities.resources is None or capabilities.prompts is None:
                raise SmokeError("MCP server/discover did not advertise tools, resources, and prompts")

            tools = await session.list_tools()
            if not _EXPECTED_MCP_TOOLS.issubset(tool.name for tool in tools.tools):
                raise SmokeError("MCP tools/list omitted representative portfolio tools")
            resources = await session.list_resources()
            if MCP_PROFILE_URI not in {str(resource.uri) for resource in resources.resources}:
                raise SmokeError("MCP resources/list omitted the portfolio resource")
            prompts = await session.list_prompts()
            if not _EXPECTED_MCP_PROMPTS.issubset(prompt.name for prompt in prompts.prompts):
                raise SmokeError("MCP prompts/list omitted representative portfolio prompts")

            search = await session.call_tool("search_articles", {"query": _MCP_SEARCH_QUERY, "limit": 1})
            if search.is_error or not isinstance(search.structured_content, dict):
                raise SmokeError("MCP tools/call did not return a successful structured result")
            if search.structured_content.get("query") != _MCP_SEARCH_QUERY:
                raise SmokeError("MCP tools/call did not return the normalized query")
            articles = search.structured_content.get("articles")
            if not isinstance(articles, list) or not articles:
                raise SmokeError("MCP tools/call did not return a matching article")

            resource = await session.read_resource(MCP_PROFILE_URI)
            if len(resource.contents) != 1 or not isinstance(resource.contents[0], TextResourceContents):
                raise SmokeError("MCP resources/read did not return the portfolio profile")
            content = resource.contents[0]
            if str(content.uri) != MCP_PROFILE_URI or content.mime_type != "application/json":
                raise SmokeError("MCP resources/read did not return the portfolio profile")
            profile = json.loads(content.text)
            if (
                not isinstance(profile, dict)
                or not isinstance(metadata := profile.get("metadata"), dict)
                or metadata.get("alternate_name") != "Fmind"
            ):
                raise SmokeError("MCP resources/read returned an unexpected portfolio profile")

            fit = await session.get_prompt("assess_fit", {"brief": _MCP_FIT_BRIEF})
            if not fit.messages:
                raise SmokeError("MCP prompts/get did not return a grounded fit assessment")
            message = fit.messages[0]
            if (
                message.role != "user"
                or not isinstance(message.content, TextContent)
                or _MCP_FIT_BRIEF not in message.content.text
            ):
                raise SmokeError("MCP prompts/get did not return a grounded fit assessment")


def _probe_modern_mcp(port: int) -> None:
    try:
        asyncio.run(_probe_mcp(port))
    except Exception as error:
        # SDK task groups can wrap protocol failures. Keep credentials and raw
        # response payloads out of CLI diagnostics while retaining the cause.
        raise SmokeError(f"MCP qualification failed ({type(error).__name__})") from error


def _probe_health(port: int) -> None:
    response = _request(port, "GET", "/health")
    _expect_ok(response, "/health")
    if response.body != b'{"status":"ok"}':
        raise SmokeError("/health returned an unexpected body")


def _assert_http_contracts(port: int) -> None:
    homepage = _request(port, "GET", "/")
    _expect_ok(homepage, "/")
    if (
        not homepage.headers.get("content-type", "").startswith("text/html")
        or HOMEPAGE_TITLE_PREFIX not in homepage.body
    ):
        raise SmokeError("homepage did not return the expected HTML")

    stylesheet = _request(port, "GET", "/static/dist/styles.css")
    _expect_ok(stylesheet, "/static/dist/styles.css")
    if not stylesheet.headers.get("content-type", "").startswith("text/css") or not stylesheet.body.startswith(
        b"/*! tailwindcss"
    ):
        raise SmokeError("representative stylesheet did not return the expected CSS")

    _probe_modern_mcp(port)


def _container_is_running(runner: Runner, name: str) -> bool:
    result = runner.run(
        ("docker", "container", "inspect", "--format", "{{json .State.Running}}", name),
        timeout=10,
        check=False,
    )
    return result.returncode == 0 and result.output.strip() == "true"


def assert_runtime_read_only(runner: Runner, name: str) -> None:
    """Prove immutable application files and the absence of privileged helpers."""
    result = runner.run(
        ("docker", "container", "exec", name, "python", "-c", _READ_ONLY_FILE_PROBE),
        timeout=30,
        check=False,
    )
    if result.returncode == 3:
        raise SmokeError("runtime user can write application code, content, or static assets")
    if result.returncode == 4:
        raise SmokeError("runtime image contains setuid or setgid helpers")
    if result.returncode != 0:
        raise SmokeError("runtime write-protection probe failed")


@contextmanager
def _termination_handlers() -> Iterator[None]:
    def terminate(signal_number: int, _frame: FrameType | None) -> NoReturn:
        raise TerminationRequestedError(signal_number)

    signals = (signal.SIGINT, signal.SIGTERM)
    previous = {item: signal.signal(item, terminate) for item in signals}
    try:
        yield
    finally:
        for item, handler in previous.items():
            signal.signal(item, handler)


def smoke_image(target: str | Path | None = None, *, runner: Runner | None = None) -> None:
    """Load and qualify an image archive or remote reference without rebuilding it."""
    command_runner = SubprocessRunner() if runner is None else runner
    image_id = resolve_image_id(command_runner, target)
    parse_configured_user(
        command_runner.run(
            ("docker", "image", "inspect", "--format", "{{json .Config.User}}", image_id), timeout=30
        ).output
    )
    exporter_names = exporter_environment_names(
        command_runner.run(
            ("docker", "image", "inspect", "--format", "{{json .Config.Env}}", image_id), timeout=30
        ).output
    )

    container_name = f"www-image-smoke-{os.getpid()}-{secrets.token_hex(6)}"
    with container_guard(command_runner, container_name):
        arguments = [
            "docker",
            "container",
            "run",
            "--detach",
            "--name",
            container_name,
            "--publish",
            f"127.0.0.1::{CONTAINER_PORT}",
            "--env",
            "ENVIRONMENT=production",
            "--env",
            f"PORT={CONTAINER_PORT}",
        ]
        for name in exporter_names:
            arguments.extend(("--env", f"{name}="))
        arguments.extend(("--pull", "never", image_id))
        parse_container_id(command_runner.run(arguments, timeout=60).output)

        published_port = parse_published_port(
            command_runner.run(
                ("docker", "container", "port", container_name, f"{CONTAINER_PORT}/tcp"), timeout=30
            ).output
        )
        wait_for_health(
            lambda: _probe_health(published_port),
            lambda: _container_is_running(command_runner, container_name),
            timeout_seconds=HEALTH_TIMEOUT_SECONDS,
            interval_seconds=1,
            monotonic=time.monotonic,
            sleep=time.sleep,
        )
        assert_runtime_read_only(command_runner, container_name)
        _assert_http_contracts(published_port)


def main(arguments: Sequence[str] | None = None) -> int:
    args = sys.argv[1:] if arguments is None else arguments
    if len(args) > 1:
        sys.stderr.write("usage: python -m scripts.image_smoke [<image-archive-or-reference>]\n")
        return 2
    target = args[0] if args else None
    try:
        with _termination_handlers():
            smoke_image(target)
    except TerminationRequestedError as error:
        sys.stderr.write(f"image smoke interrupted: {error}\n")
        return 128 + error.signal_number
    except SmokeError as error:
        sys.stderr.write(f"image smoke failed: {error}\n")
        return 1
    sys.stdout.write("production image runtime smoke passed\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
