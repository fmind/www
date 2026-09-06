"""Pure page metadata builders shared by routes and tests."""

from __future__ import annotations

import json

from www.data import METADATA
from www.models import Article, ArticleIndexView, PageMetadata, SitePage


def home_metadata(structured_data: str) -> PageMetadata:
    return PageMetadata(
        title=METADATA.title,
        description=METADATA.description,
        canonical=f"{METADATA.site_url}/",
        image_url=f"{METADATA.site_url}/static/img/og-image.jpg",
        image_alt=f"{METADATA.name} — {METADATA.job_title}",
        kind="website",
        structured_data=structured_data,
        is_home=True,
    )


def article_index_metadata(view: ArticleIndexView, structured_data: str) -> PageMetadata:
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
        description="Articles on AI agents, MLOps, cloud architecture, security, and pragmatic engineering systems.",
        canonical=f"{METADATA.site_url}/articles/",
        image_url=f"{METADATA.site_url}/static/img/og-image.jpg",
        image_alt=f"Articles by {METADATA.name}",
        kind="website",
        structured_data=structured_data,
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


def site_index_metadata(structured_data: str) -> PageMetadata:
    return PageMetadata(
        title=f"Sites | {METADATA.site_name}",
        description="Source-backed decision tools for AI architecture, infrastructure, and operating economics.",
        canonical=f"{METADATA.site_url}/sites/",
        image_url=f"{METADATA.site_url}/static/img/og-image.jpg",
        image_alt="Fmind Sites",
        kind="website",
        structured_data=structured_data,
    )


def site_page_metadata(page: SitePage, structured_data: str) -> PageMetadata:
    return PageMetadata(
        title=f"{page.title} | {METADATA.site_name}",
        description=page.description,
        canonical=page.url,
        image_url=f"{METADATA.site_url}/static/img/og-image.jpg",
        image_alt=page.title,
        kind="website",
        structured_data=structured_data,
        instant_scroll=True,
    )


def not_found_metadata(structured_data: str) -> PageMetadata:
    return PageMetadata(
        title="Page not found | Fmind",
        description="The requested page could not be found.",
        canonical=f"{METADATA.site_url}/",
        image_url=f"{METADATA.site_url}/static/img/og-image.jpg",
        image_alt=f"{METADATA.name} — {METADATA.job_title}",
        kind="website",
        structured_data=structured_data,
        no_index=True,
    )
