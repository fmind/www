"""Session fixtures and plain helpers shared by the application tests."""

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import unquote

import pytest

if TYPE_CHECKING:
    from httpx import Response
    from litestar import Litestar
    from litestar.testing import TestClient
    from litestar.types import Scope

    from www.assets import ApplicationAssets
    from www.content import ArticleCollection

MCP_ACCEPT = {"accept": "application/json, text/event-stream"}
# The stateless revision: each request carries its own protocol metadata instead of a session.
MCP_MODERN_PROTOCOL = "2026-07-28"
# MCP validates Host and has no test-only entry, so its clients call it as a local client does.
LOCAL_BASE_URL = "http://127.0.0.1"


@dataclass
class RecordingLogger:
    """Keep every logged event and its values, in order, in place of the site logger."""

    records: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def info(self, event: str, **values: Any) -> None:
        self.records.append((event, values))

    def error(self, event: str, **values: Any) -> None:
        self.records.append((event, values))


def asgi_scope(
    method: str = "GET",
    raw_path: bytes = b"/",
    *,
    headers: Sequence[tuple[bytes, bytes]] = (),
    host: str = "testserver.local",
    extensions: dict[str, dict[object, object]] | None = None,
) -> Scope:
    """Build a raw HTTPS request scope, for requests an HTTP client would normalize or cannot send."""
    scope: dict[str, object] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": unquote(raw_path.decode("ascii")),
        "raw_path": raw_path,
        "query_string": b"",
        "root_path": "",
        "headers": list(headers),
        "client": ("127.0.0.1", 12345),
        "server": (host, 443),
        "state": {},
    }
    if extensions is not None:
        scope["extensions"] = extensions
    return cast("Scope", scope)


def mcp_post(
    client: TestClient[Any],
    method: str,
    params: dict[str, Any],
    *,
    protocol: str | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    """POST one JSON-RPC request to /mcp.

    `protocol` sends the version header; the modern revision also gets its per-request headers and metadata.
    """
    request_headers = {**MCP_ACCEPT, **(headers or {})}
    if protocol is not None:
        request_headers["mcp-protocol-version"] = protocol
    if protocol == MCP_MODERN_PROTOCOL:
        request_headers["mcp-method"] = method
        if "name" in params:
            request_headers["mcp-name"] = params["name"]
        meta = {
            "io.modelcontextprotocol/protocolVersion": protocol,
            "io.modelcontextprotocol/clientCapabilities": {},
        }
        params = {**params, "_meta": meta}
    return client.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, headers=request_headers
    )


@pytest.fixture(autouse=True)
def isolate_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop the GIT_* variables a Git hook exports, so tests never act on the repository running them.

    A pre-push hook in a linked worktree exports an absolute GIT_DIR; without this, the news-script
    fixtures committed to that worktree and pushed their commits to the real origin main (2026-11-07).
    """
    for name in [name for name in os.environ if name.startswith("GIT_")]:
        monkeypatch.delenv(name)


@pytest.fixture(scope="session")
def snapshots() -> tuple[ApplicationAssets, ArticleCollection]:
    """Load the validated startup content once; frozen dataclasses and read-only mappings make it safe to share."""
    from www.assets import load_application_assets
    from www.content import load_articles

    assets = load_application_assets()
    return assets, load_articles(image_sizes=assets.image_sizes)


@pytest.fixture(scope="session")
def make_app(snapshots: tuple[ApplicationAssets, ArticleCollection]) -> Callable[[], Litestar]:
    """Build a fresh default application from the shared snapshots.

    Each TestClient lifespan needs its own instance: an app's MCP session manager starts only once per process.
    """
    # Import lazily: importing www.app also builds its module-level app, which unrelated test files skip.
    from www.app import create_app
    from www.news import load_news

    assets, collection = snapshots
    news = load_news()
    return partial(create_app, assets=assets, collection=collection, news=news)
