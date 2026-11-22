"""Pure page metadata builders shared by routes and tests."""

from collections.abc import Mapping
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from www.assets import image_dimensions
from www.connect import CONNECT_URL
from www.data import IDENTITY_GRAPH, METADATA, json_ld
from www.models import NEWS_FEED_PATH, Article, ArticleIndexView, PageMetadata, SitePage
from www.news import NEWS_TOPICS, NewsEdition

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


@lru_cache(maxsize=256)
def _static_image_size(image_url: str) -> tuple[int, int] | None:
    """Resolve (width, height) for a /static/ image URL without decoding pixel payloads."""
    prefix = f"{METADATA.site_url}/static/"
    if not image_url.startswith(prefix):
        return None
    relative = image_url.removeprefix(prefix)
    static_root = Path("static").resolve()
    path = (static_root / relative).resolve()
    if not path.is_relative_to(static_root) or not path.is_file():
        return None
    try:
        return image_dimensions(path)
    except OSError, ValueError:
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
    return _static_image_size(image_url)


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


def _enriched_page_structured_data(
    page_type: str,
    canonical: str,
    title: str,
    description: str,
    *,
    breadcrumb_label: str = "",
    image_sizes: Mapping[str, tuple[int, int]] | None = None,
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
        "primaryImageOfPage": _image_object(_WEBSITE.image_url, _WEBSITE.image_alt, image_sizes),
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
    image_sizes: Mapping[str, tuple[int, int]] | None = None,
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
            image_sizes=image_sizes,
        ),
        no_index=no_index,
        preload_code_font=preload_code_font,
    )


def connect_metadata(image_sizes: Mapping[str, tuple[int, int]] | None = None) -> PageMetadata:
    return _web_page(
        "ContactPage",
        title=f"Connect with {_IDENTITY}",
        description="Connect with Médéric Hurier (Fmind), freelance AI Architect based in Luxembourg. Find me on LinkedIn or save my contact details.",
        canonical=CONNECT_URL,
        breadcrumb_label="Connect",
        image_sizes=image_sizes,
    )


def agents_metadata(image_sizes: Mapping[str, tuple[int, int]] | None = None) -> PageMetadata:
    return _web_page(
        "WebPage",
        title=f"For AI agents | {_IDENTITY}",
        description="Explore Médéric Hurier (Fmind)'s profile, services, articles, and decision tools through free, read-only APIs and MCP.",
        canonical=f"{METADATA.site_url}/agents",
        breadcrumb_label="For AI agents",
        preload_code_font=True,
        image_sizes=image_sizes,
    )


def privacy_metadata(image_sizes: Mapping[str, tuple[int, int]] | None = None) -> PageMetadata:
    return _web_page(
        "WebPage",
        title=f"Privacy | {_IDENTITY}",
        description="How this website measures visits and handles personal information.",
        canonical=f"{METADATA.site_url}/privacy",
        breadcrumb_label="Privacy",
        # The page names the _ga cookies in <code>.
        preload_code_font=True,
        image_sizes=image_sizes,
    )


def scan_metadata(image_sizes: Mapping[str, tuple[int, int]] | None = None) -> PageMetadata:
    return _web_page(
        "ContactPage",
        title=f"Scan to connect | {_IDENTITY}",
        description="Scan the QR code to connect with Médéric Hurier on LinkedIn or save his contact details.",
        canonical=f"{METADATA.site_url}/scan",
        no_index=True,
        preload_code_font=True,
        image_sizes=image_sizes,
    )


_ARTICLE_INDEX_DESCRIPTION = (
    "Articles on AI agents, MLOps, cloud architecture, security, and pragmatic engineering systems."
)


def article_index_structured_data(image_sizes: Mapping[str, tuple[int, int]] | None = None) -> str:
    return _enriched_page_structured_data(
        "CollectionPage",
        _ARTICLES_URL,
        _ARTICLE_INDEX_TITLE,
        _ARTICLE_INDEX_DESCRIPTION,
        breadcrumb_label="Articles",
        image_sizes=image_sizes,
    )


def article_index_metadata(view: ArticleIndexView, structured_data: str = "") -> PageMetadata:
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
        structured_data=structured_data or article_index_structured_data(),
        preload_image=preload,
        no_index=view.searching(),
    )


def article_structured_data(
    article: Article,
    image_sizes: Mapping[str, tuple[int, int]] | None = None,
) -> str:
    """Build the connected Person/WebSite/BreadcrumbList/BlogPosting graph directly once."""
    person_id = f"{METADATA.site_url}/#person"
    website_id = f"{METADATA.site_url}/#website"
    canonical = article.url
    posting: dict[str, object] = {
        "@id": f"{canonical}#article",
        "@type": "BlogPosting",
        "headline": article.title,
        "description": article.description,
        "url": canonical,
        "datePublished": article.date.date().isoformat(),
        "dateModified": article.modified_date().date().isoformat(),
        "author": {"@id": person_id},
        "publisher": {"@id": person_id},
        "isPartOf": {"@id": website_id},
        "mainEntityOfPage": canonical,
        "inLanguage": "en",
        "isAccessibleForFree": True,
        "timeRequired": f"PT{article.reading_minutes}M",
        "image": _image_object(article.image_url, article.image_alt, image_sizes),
        "keywords": list(article.tags),
    }
    if article.tags:
        posting["articleSection"] = list(article.tags)
    breadcrumb = _breadcrumb_list(
        canonical,
        ("Home", _HOME_URL),
        ("Articles", _ARTICLES_URL),
        (article.title, canonical),
    )
    return json_ld([*IDENTITY_GRAPH, breadcrumb, posting])


def article_metadata(
    article: Article,
    structured_data: str | None = None,
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
        structured_data=article_structured_data(article, image_sizes) if structured_data is None else structured_data,
        preload_code_font="<code" in article.html,
        no_index=article.draft,
    )


_NEWS_INDEX_DESCRIPTION = (
    f"Daily curated links on {NEWS_TOPICS}, with one sentence on what changed. "
    "I read and watch all the content I share."
)


def news_index_metadata(image_sizes: Mapping[str, tuple[int, int]] | None = None) -> PageMetadata:
    page = _web_page(
        "CollectionPage",
        title=f"News | {_IDENTITY}",
        description=_NEWS_INDEX_DESCRIPTION,
        canonical=f"{METADATA.site_url}/news/",
        breadcrumb_label="News",
        image_sizes=image_sizes,
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


def site_index_metadata(image_sizes: Mapping[str, tuple[int, int]] | None = None) -> PageMetadata:
    return _web_page(
        "CollectionPage",
        title=f"Sites | {METADATA.site_name}",
        description="Source-backed decision tools for AI architecture, infrastructure, and operating economics.",
        canonical=_SITES_URL,
        breadcrumb_label="Sites",
        image_sizes=image_sizes,
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
