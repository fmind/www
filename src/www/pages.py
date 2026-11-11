"""Pure page metadata builders shared by routes and tests."""

import json
from collections.abc import Mapping
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import UnidentifiedImageError

from www.assets import STATIC_MANIFEST
from www.connect import CONNECT_URL
from www.content import image_dimensions
from www.data import IDENTITY_GRAPH, METADATA, json_ld
from www.models import Article, ArticleIndexView, PageMetadata, SitePage
from www.news import NEWS_FEED_PATH, NEWS_TOPICS, NewsEdition

_IDENTITY = f"{METADATA.name} ({METADATA.alternate_name})"
_ARTICLE_INDEX_TITLE = f"Articles | {_IDENTITY}"
_HOME_URL = f"{METADATA.site_url}/"
_ARTICLES_URL = f"{METADATA.site_url}/articles/"
_SITES_URL = f"{METADATA.site_url}/sites/"
# Pages other than articles share the site's social card.
_WEBSITE = PageMetadata(
    image_url=f"{METADATA.site_url}/static/img/og-image.jpg",
    image_alt="Fmind.dev — AI, Agents, Security",
    kind="website",
)


@lru_cache(maxsize=4)
def _manifest_image_sizes(manifest_path: str) -> dict[str, tuple[int, int]]:
    """Read precomputed raster dimensions when the image build manifest is present."""
    manifest = Path(manifest_path)
    if not manifest.is_file():
        return {}
    try:
        entries = json.loads(manifest.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    if not isinstance(entries, dict):
        return {}
    sizes: dict[str, tuple[int, int]] = {}
    for route, entry in entries.items():
        if isinstance(entry, dict) and isinstance(entry.get("width"), int) and isinstance(entry.get("height"), int):
            sizes[route] = (entry["width"], entry["height"])
    return sizes


@lru_cache(maxsize=256)
def _static_image_size(image_url: str, manifest_path: str) -> tuple[int, int] | None:
    """Resolve (width, height) for a /static/ image URL without decoding pixel payloads."""
    prefix = f"{METADATA.site_url}/static/"
    if not image_url.startswith(prefix):
        return None
    relative = image_url.removeprefix(prefix)
    route = f"/static/{relative}"
    if dimensions := _manifest_image_sizes(manifest_path).get(route):
        return dimensions
    static_root = Path("static").resolve()
    path = (static_root / relative).resolve()
    if not path.is_relative_to(static_root) or not path.is_file():
        return None
    try:
        return image_dimensions(path)
    except OSError, UnidentifiedImageError:
        return None


def _resolve_image_size(
    image_url: str,
    image_sizes: Mapping[str, tuple[int, int]] | None = None,
) -> tuple[int, int] | None:
    if image_sizes is not None:
        prefix = f"{METADATA.site_url}/static/"
        if not image_url.startswith(prefix):
            return None
        return image_sizes.get(f"/static/{image_url.removeprefix(prefix)}")
    return _static_image_size(image_url, STATIC_MANIFEST)


def _image_object(
    url: str,
    caption: str,
    image_sizes: Mapping[str, tuple[int, int]] | None = None,
) -> dict[str, object]:
    image: dict[str, object] = {"@type": "ImageObject", "url": url, "caption": caption}
    if dimensions := _resolve_image_size(url, image_sizes):
        image["width"], image["height"] = dimensions
    return image


def _breadcrumb_list(url: str, *crumbs: tuple[str, str]) -> dict[str, object]:
    return {
        "@id": f"{url}#breadcrumb",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": position, "name": label, "item": target}
            for position, (label, target) in enumerate(crumbs, start=1)
        ],
    }


def _dump_json_ld(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _enriched_page_structured_data(
    page_type: str,
    canonical: str,
    title: str,
    description: str,
    *,
    breadcrumb_label: str = "",
) -> str:
    page: dict[str, object] = {
        "@id": f"{canonical}#webpage",
        "@type": page_type,
        "url": canonical,
        "name": title,
        "description": description,
        "isPartOf": {"@id": f"{METADATA.site_url}/#website"},
        "about": {"@id": f"{METADATA.site_url}/#person"},
        "inLanguage": "en",
        "primaryImageOfPage": _image_object(_WEBSITE.image_url, _WEBSITE.image_alt),
    }
    graph: list[dict[str, object]] = [*IDENTITY_GRAPH]
    if breadcrumb_label:
        breadcrumb = _breadcrumb_list(canonical, ("Home", _HOME_URL), (breadcrumb_label, canonical))
        page["breadcrumb"] = {"@id": breadcrumb["@id"]}
        graph.append(breadcrumb)
    graph.append(page)
    return json_ld(graph)


def home_metadata(structured_data: str) -> PageMetadata:
    return replace(
        _WEBSITE,
        title=METADATA.title,
        description=METADATA.description,
        canonical=_HOME_URL,
        structured_data=structured_data,
        is_home=True,
        # Deferred sections change height during animated fragment scrolling.
        instant_scroll=True,
    )


def _web_page(
    page_type: str,
    *,
    title: str,
    description: str,
    canonical: str,
    breadcrumb_label: str = "",
    no_index: bool = False,
    preload_code_font: bool = False,
) -> PageMetadata:
    """Metadata for a hosted page whose JSON-LD describes that page, not the profile."""
    return replace(
        _WEBSITE,
        title=title,
        description=description,
        canonical=canonical,
        structured_data=_enriched_page_structured_data(
            page_type,
            canonical,
            title,
            description,
            breadcrumb_label="" if no_index else breadcrumb_label,
        ),
        no_index=no_index,
        preload_code_font=preload_code_font,
    )


def connect_metadata() -> PageMetadata:
    return _web_page(
        "ContactPage",
        title=f"Connect with {_IDENTITY}",
        description="Connect with Médéric Hurier (Fmind), freelance AI Architect based in Luxembourg. Find me on LinkedIn or save my contact details.",
        canonical=CONNECT_URL,
        breadcrumb_label="Connect",
    )


def agents_metadata() -> PageMetadata:
    return _web_page(
        "WebPage",
        title=f"For AI agents | {_IDENTITY}",
        description="Explore Médéric Hurier (Fmind)'s profile, services, articles, and decision tools through free, read-only APIs and MCP.",
        canonical=f"{METADATA.site_url}/agents",
        breadcrumb_label="For AI agents",
        preload_code_font=True,
    )


def privacy_metadata() -> PageMetadata:
    return _web_page(
        "WebPage",
        title=f"Privacy | {_IDENTITY}",
        description="How this website measures visits and handles personal information.",
        canonical=f"{METADATA.site_url}/privacy",
        breadcrumb_label="Privacy",
        # The page names the _ga cookies in <code>.
        preload_code_font=True,
    )


def scan_metadata() -> PageMetadata:
    return _web_page(
        "ContactPage",
        title=f"Scan to connect | {_IDENTITY}",
        description="Scan the QR code to connect with Médéric Hurier on LinkedIn or save his contact details.",
        canonical=f"{METADATA.site_url}/scan",
        no_index=True,
        preload_code_font=True,
    )


_ARTICLE_INDEX_DESCRIPTION = (
    "Articles on AI agents, MLOps, cloud architecture, security, and pragmatic engineering systems."
)
ARTICLE_INDEX_STRUCTURED_DATA = _enriched_page_structured_data(
    "CollectionPage",
    _ARTICLES_URL,
    _ARTICLE_INDEX_TITLE,
    _ARTICLE_INDEX_DESCRIPTION,
    breadcrumb_label="Articles",
)


def article_index_metadata(view: ArticleIndexView) -> PageMetadata:
    preload = ""
    if view.results:
        preload = view.results[0].card_image_path()
    elif view.years and view.years[0].articles:
        preload = view.years[0].articles[0].card_image_path()
    if view.searching() and view.active_tag:
        title = f"Search: {view.query} ({view.active_tag}) | {_ARTICLE_INDEX_TITLE}"
    elif view.searching():
        title = f"Search: {view.query} | {_ARTICLE_INDEX_TITLE}"
    elif view.active_tag:
        title = f"{view.active_tag} Articles | {_IDENTITY}"
    else:
        title = _ARTICLE_INDEX_TITLE
    return replace(
        _WEBSITE,
        title=title,
        description=_ARTICLE_INDEX_DESCRIPTION,
        canonical=_ARTICLES_URL,
        structured_data=ARTICLE_INDEX_STRUCTURED_DATA,
        preload_image=preload,
        no_index=view.searching(),
    )


def _enriched_article_structured_data(
    article: Article,
    structured_data: str,
    image_sizes: Mapping[str, tuple[int, int]] | None = None,
) -> str:
    if not structured_data:
        return ""
    try:
        payload = json.loads(structured_data)
    except ValueError:
        return structured_data
    graph = payload.get("@graph")
    if not isinstance(graph, list):
        return structured_data
    posting = next((node for node in graph if isinstance(node, dict) and node.get("@type") == "BlogPosting"), None)
    if posting is None:
        return structured_data
    posting["publisher"] = {"@id": f"{METADATA.site_url}/#person"}
    posting["inLanguage"] = "en"
    posting["isAccessibleForFree"] = True
    posting["timeRequired"] = f"PT{article.reading_minutes}M"
    if article.tags:
        posting["articleSection"] = list(article.tags)
    image = posting.get("image")
    if isinstance(image, dict) and (dimensions := _resolve_image_size(article.image_url, image_sizes)):
        image["width"], image["height"] = dimensions
    breadcrumb = _breadcrumb_list(
        article.url,
        ("Home", _HOME_URL),
        ("Articles", _ARTICLES_URL),
        (article.title, article.url),
    )
    graph.insert(-1, breadcrumb)
    return _dump_json_ld(payload)


def article_metadata(
    article: Article,
    structured_data: str,
    image_sizes: Mapping[str, tuple[int, int]] | None = None,
) -> PageMetadata:
    return PageMetadata(
        article=article,
        title=f"{article.title} | Fmind",
        description=article.description,
        canonical=article.url,
        image_url=article.image_url,
        image_alt=article.image_alt,
        kind="article",
        structured_data=_enriched_article_structured_data(article, structured_data, image_sizes),
        preload_code_font="<code" in article.html,
        no_index=article.draft,
    )


_NEWS_INDEX_DESCRIPTION = (
    f"Daily curated links on {NEWS_TOPICS}, with one sentence on what changed. "
    "I read and watch all the content I share."
)


def news_index_metadata() -> PageMetadata:
    page = _web_page(
        "CollectionPage",
        title=f"News | {_IDENTITY}",
        description=_NEWS_INDEX_DESCRIPTION,
        canonical=f"{METADATA.site_url}/news/",
        breadcrumb_label="News",
    )
    return replace(page, feed_path=NEWS_FEED_PATH, feed_title="Fmind news")


def news_edition_metadata(edition: NewsEdition) -> PageMetadata:
    return replace(
        _WEBSITE,
        title=f"News: {edition.title} | Fmind",
        description=edition.description,
        canonical=edition.url,
        # Editions are short link summaries: readers follow them from /news/ and the feed, search engines do not
        # index them, so they carry no JSON-LD graph (like the 404 page).
        no_index=True,
        feed_path=NEWS_FEED_PATH,
        feed_title="Fmind news",
    )


def site_structured_data(
    page: SitePage,
    image_sizes: Mapping[str, tuple[int, int]] | None = None,
) -> str:
    breadcrumb = _breadcrumb_list(
        page.url,
        ("Home", _HOME_URL),
        ("Sites", _SITES_URL),
        (page.title, page.url),
    )
    return json_ld(
        [
            *IDENTITY_GRAPH,
            breadcrumb,
            {
                "@id": f"{page.url}#webpage",
                "@type": "WebPage",
                "url": page.url,
                "name": page.title,
                "description": page.description,
                "isPartOf": {"@id": f"{METADATA.site_url}/#website"},
                "mainEntity": {"@id": f"{page.url}#application"},
                "inLanguage": "en",
                "breadcrumb": {"@id": breadcrumb["@id"]},
                "primaryImageOfPage": _image_object(_WEBSITE.image_url, _WEBSITE.image_alt, image_sizes),
            },
            {
                "@id": f"{page.url}#application",
                "@type": "WebApplication",
                "name": page.title,
                "description": page.description,
                "url": page.url,
                "applicationCategory": "BusinessApplication",
                "operatingSystem": "Web",
                "isAccessibleForFree": True,
                "offers": {"@type": "Offer", "price": 0, "priceCurrency": "USD"},
                "author": {"@id": f"{METADATA.site_url}/#person"},
                "inLanguage": "en",
                "audience": {"@type": "Audience", "audienceType": page.audience},
            },
        ]
    )


def site_index_metadata() -> PageMetadata:
    return _web_page(
        "CollectionPage",
        title=f"Sites | {METADATA.site_name}",
        description="Source-backed decision tools for AI architecture, infrastructure, and operating economics.",
        canonical=_SITES_URL,
        breadcrumb_label="Sites",
    )


def site_page_metadata(page: SitePage, structured_data: str) -> PageMetadata:
    return replace(
        _WEBSITE,
        title=f"{page.title} | {METADATA.site_name}",
        description=page.description,
        canonical=page.url,
        structured_data=structured_data,
        instant_scroll=True,
    )


def not_found_metadata() -> PageMetadata:
    # A missing page describes nothing, so it carries no canonical URL or JSON-LD graph.
    return replace(
        _WEBSITE,
        title="Page not found | Fmind",
        description="The requested page could not be found.",
        canonical="",
        no_index=True,
    )
