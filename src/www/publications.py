"""Precomputed feeds, machine-readable publications, and article index views."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from html.parser import HTMLParser
from xml.etree import ElementTree

from pydantic import TypeAdapter

from www.data import (
    BADGES,
    BIOGRAPHY,
    EXPERIENCES,
    EXPERTISE,
    LEADERSHIP,
    METADATA,
    OPEN_SOURCE,
    PAPERS,
    SITE_PAGES,
    SPECIALIZATIONS,
    THESIS,
    YOUTUBE_SERIES,
    get_services,
)
from www.markdown import rewrite_markdown_links
from www.models import Article, ArticleIndexView, ArticleSummary, ArticleYear, Portfolio
from www.search import SearchIndex, normalize_search_query
from www.tags import TAGS, sort_tags

_PORTFOLIO_ADAPTER = TypeAdapter(Portfolio)

ATOM_FULL_CONTENT_LIMIT = 15
RELATED_ARTICLE_COUNT = 3
_ATOM = "http://www.w3.org/2005/Atom"
_SITEMAP = "http://www.sitemaps.org/schemas/sitemap/0.9"


def _sub(parent: ElementTree.Element, name: str, text: str = "", **attributes: str) -> ElementTree.Element:
    child = ElementTree.SubElement(parent, name, attributes)
    child.text = text
    return child


def _xml(element: ElementTree.Element) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ElementTree.tostring(element, encoding="unicode")


def _atom_time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def absolute_article_html(body: str) -> str:
    body = body.replace('href="/', f'href="{METADATA.site_url}/')
    return body.replace('src="/', f'src="{METADATA.site_url}/')


def render_atom_feed(articles: Sequence[Article]) -> str:
    feed = ElementTree.Element("feed", xmlns=_ATOM)
    _sub(feed, "title", "Fmind articles")
    _sub(feed, "id", f"{METADATA.site_url}/articles/")
    updated = max((article.modified_date() for article in articles), default=datetime(1970, 1, 1, tzinfo=UTC))
    _sub(feed, "updated", _atom_time(updated))
    _sub(feed, "link", href=f"{METADATA.site_url}/articles/feed.xml", rel="self", type="application/atom+xml")
    _sub(feed, "link", href=f"{METADATA.site_url}/articles/", rel="alternate", type="text/html")
    author = _sub(feed, "author")
    _sub(author, "name", METADATA.name)
    _sub(author, "uri", f"{METADATA.site_url}/")
    for index, article in enumerate(articles):
        entry = _sub(feed, "entry")
        _sub(entry, "title", article.title)
        _sub(entry, "id", article.url)
        _sub(entry, "published", _atom_time(article.date))
        _sub(entry, "updated", _atom_time(article.modified_date()))
        _sub(entry, "link", href=article.url, rel="alternate", type="text/html")
        for tag in article.tags:
            # Feed readers filter and group by category; terms are the site's closed tag vocabulary.
            _sub(entry, "category", term=tag, scheme=f"{METADATA.site_url}/articles/?tag=", label=tag)
        if index < ATOM_FULL_CONTENT_LIMIT:
            # Feed readers need the article URL when following a section link.
            body = absolute_article_html(article.html).replace('href="#', f'href="{article.url}#')
            _sub(entry, "content", body, type="html")
        _sub(entry, "summary", article.description, type="text")
    return _xml(feed)


def render_sitemap(articles: Sequence[Article]) -> str:
    root = ElementTree.Element("urlset", xmlns=_SITEMAP)
    locations = (
        f"{METADATA.site_url}/",
        f"{METADATA.site_url}/articles/",
        f"{METADATA.site_url}/connect",
        f"{METADATA.site_url}/privacy",
        f"{METADATA.site_url}/agents",
        f"{METADATA.site_url}/sites/",
        *(page.url for page in SITE_PAGES),
    )
    for location in locations:
        url = _sub(root, "url")
        _sub(url, "loc", location)
    for article in articles:
        if article.canonical:
            continue
        url = _sub(root, "url")
        _sub(url, "loc", article.url)
        _sub(url, "lastmod", article.modified_date().date().isoformat())
    return _xml(root)


def render_llms_txt(articles: Sequence[Article]) -> str:
    lines = [
        f"# {METADATA.name} — {METADATA.alternate_name}",
        "",
        f"> {METADATA.headline_primary}",
        f"> {METADATA.headline_secondary}",
        "",
        METADATA.description,
        "",
        "## Services and contact",
        "",
        f"Based in {METADATA.work_location}.",
        "",
        *(
            f"- **{service.title}**: {service.description} {service.badge}. [{service.cta_text}]({service.cta_url})"
            for service in get_services()
        ),
        "",
        f"- [Professional profile and experience]({METADATA.site_url}/#about)",
        "",
        "## Machine-readable portfolio",
        "",
        f"- [Connect]({METADATA.site_url}/connect): LinkedIn, a downloadable contact card, and the full website.",
        f"- [Agent guide]({METADATA.site_url}/agents): Connection instructions, tool examples, and data boundaries.",
        f"- [API catalog]({METADATA.site_url}/.well-known/api-catalog): Public API discovery.",
        f"- [Agent skill]({METADATA.site_url}/.well-known/agent-skills/index.json): Research articles and compare hosting scenarios.",
        f"- [MCP server]({METADATA.site_url}/mcp): Read-only portfolio tools, resources, and prompts.",
        f"- [JSON profile]({METADATA.site_url}/api/profile): Canonical portfolio and article index.",
        f"- [Profile schema]({METADATA.site_url}/api/profile/schema.json): JSON Schema for validating the profile response.",
        f"- [MCP discovery]({METADATA.site_url}/mcp/server-card): Available tools, prompts, and portfolio resource URI.",
        f"- [Full LLM context]({METADATA.site_url}/llms-full.txt): This index plus every public article in Markdown.",
        f"- Article source: append `.md` to any article slug ({METADATA.site_url}/articles/<slug>.md) for its raw Markdown.",
        f"- [Atom feed]({METADATA.site_url}/articles/feed.xml): Reverse-chronological publication feed.",
        f"- [Sitemap]({METADATA.site_url}/sitemap.xml): Canonical hosted pages.",
        "",
        "## Expertise",
        "",
    ]
    lines.extend(f"- **{card.title}**: {card.description}" for card in EXPERTISE)
    lines.extend(("", "## Sites", ""))
    lines.extend(f"- [{page.title}]({page.url}) — {page.description}" for page in SITE_PAGES)
    lines.extend(("", "## Articles", ""))
    lines.extend(
        f"- [{article.title}]({article.url}) — {article.description} ([Markdown]({article.markdown_url()}))"
        for article in articles
    )
    lines.extend(("", "## Optional", "", f"- [PhD thesis]({THESIS.url}): {THESIS.title}"))
    lines.extend(f"- [{paper.title}]({paper.url}) — {paper.venue}" for paper in PAPERS)
    return "\n".join(lines) + "\n"


def render_llms_full(index: str, articles: Sequence[Article], markdown_by_slug: Mapping[str, str]) -> str:
    body = index + "\n## Full articles\n"
    for article in articles:
        body += f"\n{markdown_by_slug[article.slug]}\n"
    return body


def related_articles(current: Article, articles: Sequence[Article]) -> tuple[Article, ...]:
    candidates = [article for article in articles if article.slug != current.slug]
    candidates.sort(key=lambda article: sum(tag in current.tags for tag in article.tags), reverse=True)
    return tuple(candidates[:RELATED_ARTICLE_COUNT])


def related_article_index(articles: Sequence[Article]) -> dict[str, tuple[Article, ...]]:
    return {article.slug: related_articles(article, articles) for article in articles}


def article_index_data(
    articles: Sequence[Article], index: SearchIndex, requested_tag: str, requested_query: str
) -> ArticleIndexView:
    tags = sort_tags({tag for article in articles for tag in article.tags})
    active_tag = next((tag for tag in tags if tag.casefold() == requested_tag.casefold()), "")

    def matches_tag(article: Article) -> bool:
        return not active_tag or active_tag in article.tags

    query = normalize_search_query(requested_query)
    if query:
        return ArticleIndexView(
            query=query,
            active_tag=active_tag,
            tags=tags,
            results=tuple(article for article in index.search(query) if matches_tag(article)),
        )

    groups: list[ArticleYear] = []
    for article in articles:
        if not matches_tag(article):
            continue
        year = article.date.year
        if not groups or groups[-1].year != year:
            groups.append(ArticleYear(year=year))
        current = groups[-1]
        groups[-1] = ArticleYear(articles=(*current.articles, article), year=current.year)
    return ArticleIndexView(active_tag=active_tag, tags=tags, years=tuple(groups))


def absolute_markdown_links(markdown: str) -> str:
    def absolute(destination: str) -> str:
        if destination.startswith("/") and not destination.startswith("//"):
            return METADATA.site_url + destination
        return destination

    return rewrite_markdown_links(markdown, absolute)


def render_article_markdown(article: Article) -> str:
    lines = [
        f"# {article.title}",
        "",
        f"> {article.description}",
        "",
        f"- Author: [{METADATA.name} ({METADATA.alternate_name})]({METADATA.site_url}/)",
        f"- Published: {article.date.date().isoformat()}",
    ]
    if article.modified_date() > article.date:
        lines.append(f"- Updated: {article.modified_date().date().isoformat()}")
    lines.extend(
        (
            f"- Reading time: {article.reading_minutes} min",
            f"- Tags: {', '.join(article.tags)}",
            f"- URL: {article.url}",
        )
    )
    if article.canonical:
        lines.append(f"- Canonical: {article.canonical}")
    if article.syndicated:
        lines.append(f"- Also published at: {article.syndicated}")
    lines.extend(("", absolute_markdown_links(article.markdown)))
    return "\n".join(lines) + "\n"


def article_markdown_index(articles: Sequence[Article]) -> dict[str, str]:
    return {article.slug: render_article_markdown(article) for article in articles}


def portfolio_snapshot(articles: Sequence[ArticleSummary]) -> Portfolio:
    return Portfolio(
        metadata=METADATA,
        biography=BIOGRAPHY,
        leadership=LEADERSHIP,
        expertise=EXPERTISE,
        experience=EXPERIENCES,
        certifications=BADGES,
        specializations=SPECIALIZATIONS,
        thesis=THESIS,
        papers=PAPERS,
        tags=TAGS,
        articles=tuple(articles),
        site_pages=SITE_PAGES,
        open_source=OPEN_SOURCE,
        youtube_series=YOUTUBE_SERIES,
        services=get_services(),
    )


def render_profile_json(articles: tuple[ArticleSummary, ...]) -> bytes:
    """Render the canonical, human-readable profile document with a final newline."""
    return _PORTFOLIO_ADAPTER.dump_json(portfolio_snapshot(articles), indent=2) + b"\n"


def render_profile_schema() -> bytes:
    """Describe the serialized public fields using the same model as the API."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{METADATA.site_url}/api/profile/schema.json",
        **_PORTFOLIO_ADAPTER.json_schema(mode="serialization"),
    }
    return (json.dumps(schema, ensure_ascii=False, indent=2) + "\n").encode()


class _ArticleSections(HTMLParser):
    """Read the section links already generated by the canonical HTML renderer."""

    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url
        self.sections: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "a" and "heading-anchor" in (attributes.get("class") or "").split():
            self.sections.append(
                {
                    "title": (attributes.get("aria-label") or "").removeprefix("Link to section: "),
                    "url": self.url + (attributes.get("href") or ""),
                }
            )


def article_sections(article: Article) -> tuple[dict[str, str], ...]:
    parser = _ArticleSections(article.url)
    parser.feed(article.html)
    return tuple(parser.sections)


def render_home_markdown(articles: tuple[ArticleSummary, ...]) -> bytes:
    """Render the complete public portfolio without scraping its HTML layout."""
    profile = json.loads(render_profile_json(articles))
    lines = [
        f"# {METADATA.name} ({METADATA.alternate_name})",
        "",
        METADATA.description,
        "",
        f"[Agent guide]({METADATA.site_url}/agents)",
    ]

    def append(value: object, depth: int = 0) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                label = str(key).replace("_", " ").capitalize()
                if isinstance(item, (dict, list)):
                    lines.append("  " * depth + f"- {label}:")
                    append(item, depth + 1)
                elif item not in (None, ""):
                    lines.append("  " * depth + f"- {label}: {item}")
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    lines.append("  " * depth + "- Entry:")
                    append(item, depth + 1)
                else:
                    append(item, depth)
        elif value not in (None, ""):
            lines.append("  " * depth + f"- {value}")

    for name, value in profile.items():
        lines.extend(("", "## " + name.replace("_", " ").capitalize(), ""))
        append(value)
    return ("\n".join(lines) + "\n").encode()
