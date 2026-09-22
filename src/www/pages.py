"""Pure page metadata builders shared by routes and tests."""

from __future__ import annotations

import json

from www.connect import CONNECT_URL
from www.data import METADATA, get_page_structured_data
from www.models import Article, ArticleIndexView, PageMetadata, SitePage


def home_metadata(structured_data: str) -> PageMetadata:
    return PageMetadata(
        title=METADATA.title,
        description=METADATA.description,
        canonical=f"{METADATA.site_url}/",
        image_url=f"{METADATA.site_url}/static/img/og-image.jpg",
        image_alt="Fmind.dev — AI, Agents, Security",
        kind="website",
        structured_data=structured_data,
        is_home=True,
        # Deferred sections change height during animated fragment scrolling.
        instant_scroll=True,
    )


def _web_page(page_type: str, *, title: str, description: str, canonical: str, no_index: bool = False) -> PageMetadata:
    """Metadata for a hosted page whose JSON-LD describes that page, not the profile."""
    return PageMetadata(
        title=title,
        description=description,
        canonical=canonical,
        image_url=f"{METADATA.site_url}/static/img/og-image.jpg",
        image_alt="Fmind.dev — AI, Agents, Security",
        kind="website",
        structured_data=get_page_structured_data(page_type, canonical, title, description),
        no_index=no_index,
    )


def connect_metadata() -> PageMetadata:
    return _web_page(
        "ContactPage",
        title=f"Connect with {METADATA.name} ({METADATA.alternate_name})",
        description="Connect with Médéric Hurier (Fmind), freelance AI Architect based in Luxembourg. Find me on LinkedIn or save my contact details.",
        canonical=CONNECT_URL,
    )


def agents_metadata() -> PageMetadata:
    return _web_page(
        "WebPage",
        title="For AI agents | Médéric Hurier (Fmind)",
        description="Explore Médéric Hurier (Fmind)'s profile, services, articles, and decision tools through free, read-only APIs and MCP.",
        canonical=f"{METADATA.site_url}/agents",
    )


def privacy_metadata() -> PageMetadata:
    return _web_page(
        "WebPage",
        title="Privacy | Médéric Hurier (Fmind)",
        description="How this website measures visits and handles personal information.",
        canonical=f"{METADATA.site_url}/privacy",
    )


def scan_metadata() -> PageMetadata:
    return _web_page(
        "ContactPage",
        title=f"Scan to connect | {METADATA.name} ({METADATA.alternate_name})",
        description="Scan the QR code to connect with Médéric Hurier on LinkedIn or save his contact details.",
        canonical=f"{METADATA.site_url}/scan",
        no_index=True,
    )


_ARTICLE_INDEX_DESCRIPTION = (
    "Articles on AI agents, MLOps, cloud architecture, security, and pragmatic engineering systems."
)
_ARTICLE_INDEX_STRUCTURED_DATA = get_page_structured_data(
    "CollectionPage", f"{METADATA.site_url}/articles/", "Articles | Médéric Hurier (Fmind)", _ARTICLE_INDEX_DESCRIPTION
)


def article_index_metadata(view: ArticleIndexView) -> PageMetadata:
    preload = ""
    if view.results:
        preload = view.results[0].card_image_path()
    elif view.years and view.years[0].articles:
        preload = view.years[0].articles[0].card_image_path()
    title = "Articles | Médéric Hurier (Fmind)"
    if view.searching():
        title = f"Search: {view.query} | Articles | Médéric Hurier (Fmind)"
    return PageMetadata(
        title=title,
        description=_ARTICLE_INDEX_DESCRIPTION,
        canonical=f"{METADATA.site_url}/articles/",
        image_url=f"{METADATA.site_url}/static/img/og-image.jpg",
        image_alt="Fmind.dev — AI, Agents, Security",
        kind="website",
        structured_data=_ARTICLE_INDEX_STRUCTURED_DATA,
        preload_image=preload,
        no_index=view.searching(),
    )


def article_metadata(article: Article, structured_data: str) -> PageMetadata:
    return PageMetadata(
        article=article,
        title=f"{article.title} | Fmind",
        description=article.description,
        canonical=article.canonical_url(),
        image_url=article.image_url,
        image_alt=article.image_alt,
        kind="article",
        structured_data=structured_data,
        preload_image=article.image_path(),
        preload_image_srcset=article.cover_srcset,
        preload_image_sizes=article.cover_sizes,
        no_index=article.draft,
    )


def site_structured_data(page: SitePage) -> str:
    return json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "WebApplication",
            "name": page.title,
            "description": page.description,
            "url": page.url,
            "applicationCategory": "BusinessApplication",
            "operatingSystem": "Web",
            "author": {"@type": "Person", "name": METADATA.name, "url": METADATA.site_url},
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def site_index_metadata() -> PageMetadata:
    return _web_page(
        "CollectionPage",
        title=f"Sites | {METADATA.site_name}",
        description="Source-backed decision tools for AI architecture, infrastructure, and operating economics.",
        canonical=f"{METADATA.site_url}/sites/",
    )


def site_page_metadata(page: SitePage, structured_data: str) -> PageMetadata:
    return PageMetadata(
        title=f"{page.title} | {METADATA.site_name}",
        description=page.description,
        canonical=page.url,
        image_url=f"{METADATA.site_url}/static/img/og-image.jpg",
        image_alt="Fmind.dev — AI, Agents, Security",
        kind="website",
        structured_data=structured_data,
        instant_scroll=True,
    )


def not_found_metadata() -> PageMetadata:
    # A missing page describes nothing, so it carries no JSON-LD graph.
    return PageMetadata(
        title="Page not found | Fmind",
        description="The requested page could not be found.",
        canonical=f"{METADATA.site_url}/",
        image_url=f"{METADATA.site_url}/static/img/og-image.jpg",
        image_alt="Fmind.dev — AI, Agents, Security",
        kind="website",
        no_index=True,
    )
