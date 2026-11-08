"""Session fixtures shared by the application tests."""

import os
from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from litestar import Litestar

    from www.assets import ApplicationAssets
    from www.content import ArticleCollection


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
