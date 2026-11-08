"""Pure page metadata builders shared by routes and tests."""

from dataclasses import replace

from www.connect import CONNECT_URL
from www.data import METADATA, get_application_structured_data, get_page_structured_data
from www.models import Article, ArticleIndexView, PageMetadata, SitePage
from www.news import NEWS_FEED_PATH, NEWS_TOPICS, NewsEdition

_IDENTITY = f"{METADATA.name} ({METADATA.alternate_name})"
_ARTICLE_INDEX_TITLE = f"Articles | {_IDENTITY}"
# Pages other than articles share the site's social card.
_WEBSITE = PageMetadata(
    image_url=f"{METADATA.site_url}/static/img/og-image.jpg",
    image_alt="Fmind.dev — AI, Agents, Security",
    kind="website",
)


def home_metadata(structured_data: str) -> PageMetadata:
    return replace(
        _WEBSITE,
        title=METADATA.title,
        description=METADATA.description,
        canonical=f"{METADATA.site_url}/",
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
    no_index: bool = False,
    preload_code_font: bool = False,
) -> PageMetadata:
    """Metadata for a hosted page whose JSON-LD describes that page, not the profile."""
    return replace(
        _WEBSITE,
        title=title,
        description=description,
        canonical=canonical,
        structured_data=get_page_structured_data(page_type, canonical, title, description),
        no_index=no_index,
        preload_code_font=preload_code_font,
    )


def connect_metadata() -> PageMetadata:
    return _web_page(
        "ContactPage",
        title=f"Connect with {_IDENTITY}",
        description="Connect with Médéric Hurier (Fmind), freelance AI Architect based in Luxembourg. Find me on LinkedIn or save my contact details.",
        canonical=CONNECT_URL,
    )


def agents_metadata() -> PageMetadata:
    return _web_page(
        "WebPage",
        title=f"For AI agents | {_IDENTITY}",
        description="Explore Médéric Hurier (Fmind)'s profile, services, articles, and decision tools through free, read-only APIs and MCP.",
        canonical=f"{METADATA.site_url}/agents",
        preload_code_font=True,
    )


def privacy_metadata() -> PageMetadata:
    return _web_page(
        "WebPage",
        title=f"Privacy | {_IDENTITY}",
        description="How this website measures visits and handles personal information.",
        canonical=f"{METADATA.site_url}/privacy",
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
ARTICLE_INDEX_STRUCTURED_DATA = get_page_structured_data(
    "CollectionPage", f"{METADATA.site_url}/articles/", _ARTICLE_INDEX_TITLE, _ARTICLE_INDEX_DESCRIPTION
)


def article_index_metadata(view: ArticleIndexView) -> PageMetadata:
    preload = ""
    if view.results:
        preload = view.results[0].card_image_path()
    elif view.years and view.years[0].articles:
        preload = view.years[0].articles[0].card_image_path()
    title = f"Search: {view.query} | {_ARTICLE_INDEX_TITLE}" if view.searching() else _ARTICLE_INDEX_TITLE
    return replace(
        _WEBSITE,
        title=title,
        description=_ARTICLE_INDEX_DESCRIPTION,
        canonical=f"{METADATA.site_url}/articles/",
        structured_data=ARTICLE_INDEX_STRUCTURED_DATA,
        preload_image=preload,
        no_index=view.searching(),
    )


def article_metadata(article: Article, structured_data: str) -> PageMetadata:
    return PageMetadata(
        article=article,
        title=f"{article.title} | Fmind",
        description=article.description,
        canonical=article.url,
        image_url=article.image_url,
        image_alt=article.image_alt,
        kind="article",
        structured_data=structured_data,
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
    )
    return replace(page, feed_path=NEWS_FEED_PATH, feed_title="Fmind news")


def news_edition_metadata(edition: NewsEdition) -> PageMetadata:
    page = _web_page(
        "CollectionPage",
        title=f"News: {edition.title} | Fmind",
        description=edition.description,
        canonical=edition.url,
        # Editions are short link summaries: readers follow them from /news/ and the feed, search engines do not index them.
        no_index=True,
    )
    return replace(page, feed_path=NEWS_FEED_PATH, feed_title="Fmind news")


def site_structured_data(page: SitePage) -> str:
    return get_application_structured_data(page.url, page.title, page.description)


def site_index_metadata() -> PageMetadata:
    return _web_page(
        "CollectionPage",
        title=f"Sites | {METADATA.site_name}",
        description="Source-backed decision tools for AI architecture, infrastructure, and operating economics.",
        canonical=f"{METADATA.site_url}/sites/",
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
    # A missing page describes nothing, so it carries no JSON-LD graph.
    return replace(
        _WEBSITE,
        title="Page not found | Fmind",
        description="The requested page could not be found.",
        canonical=f"{METADATA.site_url}/",
        no_index=True,
    )
