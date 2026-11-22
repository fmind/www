"""Precomputed feeds, machine-readable publications, and article index views."""

import html
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
    SERVICES,
    SITE_PAGES,
    SPECIALIZATIONS,
    THESIS,
    YOUTUBE_SERIES,
)
from www.models import (
    NEWS_FEED_PATH,
    Article,
    ArticleIndexView,
    ArticleSectionLink,
    ArticleSummary,
    ArticleYear,
    Portfolio,
    utc_stamp,
)
from www.search import SearchIndex, normalize_search_query
from www.tags import TAGS, sort_tags

_PORTFOLIO_ADAPTER = TypeAdapter(Portfolio)

ATOM_FULL_CONTENT_LIMIT = 15
RELATED_ARTICLE_COUNT = 3
# Media RSS is the de facto thumbnail signal for feed readers (Feedly, Inoreader, NetNewsWire).
_MEDIA = "http://search.yahoo.com/mrss/"
ElementTree.register_namespace("media", _MEDIA)
_SITEMAP = "http://www.sitemaps.org/schemas/sitemap/0.9"
_URL_ATTRS = frozenset({"href", "src"})


def xml_sub(parent: ElementTree.Element, name: str, text: str = "", **attributes: str) -> ElementTree.Element:
    """Append one feed or sitemap element with its text and attributes."""
    child = ElementTree.SubElement(parent, name, attributes)
    child.text = text
    return child


def xml_document(element: ElementTree.Element) -> str:
    """Serialize a feed or sitemap with a declaration and a final newline."""
    # Indented output reads well when a browser or feed reader shows the raw XML.
    ElementTree.indent(element)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ElementTree.tostring(element, encoding="unicode") + "\n"


def atom_feed_root(
    title: str, page_path: str, feed_path: str, updated: datetime, subtitle: str = ""
) -> ElementTree.Element:
    """Build the shared Atom feed header for hosted publications."""
    feed = ElementTree.Element("feed", xmlns="http://www.w3.org/2005/Atom")
    xml_sub(feed, "title", title)
    if subtitle:
        xml_sub(feed, "subtitle", subtitle)
    xml_sub(feed, "id", f"{METADATA.site_url}{page_path}")
    xml_sub(feed, "updated", utc_stamp(updated))
    xml_sub(feed, "link", href=f"{METADATA.site_url}{feed_path}", rel="self", type="application/atom+xml")
    xml_sub(feed, "link", href=f"{METADATA.site_url}{page_path}", rel="alternate", type="text/html")
    # Atom `icon` is the square branding image feed readers show next to the feed name.
    xml_sub(feed, "icon", f"{METADATA.site_url}/static/img/favicons/icon-192.png")
    author = xml_sub(feed, "author")
    xml_sub(author, "name", METADATA.name)
    xml_sub(author, "uri", f"{METADATA.site_url}/")
    return feed


def _absolute_srcset(candidates: str) -> str:
    absolute = (
        METADATA.site_url + candidate if candidate.startswith("/") and not candidate.startswith("//") else candidate
        for candidate in (item.strip() for item in candidates.split(","))
    )
    return ", ".join(absolute)


def _format_tag(tag: str, attrs: list[tuple[str, str | None]], *, self_closing: bool) -> str:
    parts = [tag]
    for name, value in attrs:
        if value is None:
            parts.append(name)
        else:
            parts.append(f'{name}="{html.escape(value, quote=True)}"')
    return f"<{' '.join(parts)} />" if self_closing else f"<{' '.join(parts)}>"


class _AbsoluteHTMLRewriter(HTMLParser):
    """Rewrite root-relative/fragment URLs strictly inside HTML start tags, preserving text and code blocks."""

    def __init__(self, fragment_base: str) -> None:
        super().__init__(convert_charrefs=False)
        self._fragment_base = fragment_base
        self._chunks: list[str] = []

    def _rewrite_attrs(self, attrs: list[tuple[str, str | None]]) -> list[tuple[str, str | None]] | None:
        changed = False
        rewritten: list[tuple[str, str | None]] = []
        for name, raw_value in attrs:
            attr_value = raw_value
            if attr_value is not None:
                lower = name.lower()
                if lower in _URL_ATTRS:
                    if attr_value.startswith("/") and not attr_value.startswith("//"):
                        attr_value = METADATA.site_url + attr_value
                        changed = True
                    elif lower == "href" and self._fragment_base and attr_value.startswith("#"):
                        attr_value = self._fragment_base + attr_value
                        changed = True
                elif lower == "srcset":
                    updated = _absolute_srcset(attr_value)
                    if updated != attr_value:
                        attr_value = updated
                        changed = True
            rewritten.append((name, attr_value))
        return rewritten if changed else None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        rewritten = self._rewrite_attrs(attrs)
        if rewritten is None:
            self._chunks.append(self.get_starttag_text() or _format_tag(tag, attrs, self_closing=False))
        else:
            self._chunks.append(_format_tag(tag, rewritten, self_closing=False))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        rewritten = self._rewrite_attrs(attrs)
        if rewritten is None:
            self._chunks.append(self.get_starttag_text() or _format_tag(tag, attrs, self_closing=True))
        else:
            self._chunks.append(_format_tag(tag, rewritten, self_closing=True))

    def handle_endtag(self, tag: str) -> None:
        self._chunks.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def handle_entityref(self, name: str) -> None:
        self._chunks.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._chunks.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self._chunks.append(f"<!--{data}-->")

    def result(self) -> str:
        return "".join(self._chunks)


def absolute_article_html(body: str, *, fragment_base: str = "") -> str:
    """Make root-relative links, images, srcset candidates, and optional fragments work off-site."""
    rewriter = _AbsoluteHTMLRewriter(fragment_base)
    rewriter.feed(body)
    rewriter.close()
    return rewriter.result()


def render_atom_feed(articles: Sequence[Article]) -> str:
    updated = max((article.modified_date() for article in articles), default=datetime(1970, 1, 1, tzinfo=UTC))
    feed = atom_feed_root("Fmind articles", "/articles/", "/articles/feed.xml", updated)
    for index, article in enumerate(articles):
        entry = xml_sub(feed, "entry")
        xml_sub(entry, "title", article.title)
        xml_sub(entry, "id", article.url)
        xml_sub(entry, "published", utc_stamp(article.date))
        xml_sub(entry, "updated", utc_stamp(article.modified_date()))
        xml_sub(entry, "link", href=article.url, rel="alternate", type="text/html")
        # Every entry gets a reader thumbnail, including the ones past the full-content limit.
        xml_sub(entry, f"{{{_MEDIA}}}thumbnail", url=article.card_image_url)
        for tag in article.tags:
            # Feed readers filter and group by category; terms are the site's closed tag vocabulary.
            xml_sub(entry, "category", term=tag, scheme=f"{METADATA.site_url}/articles/?tag=", label=tag)
        if index < ATOM_FULL_CONTENT_LIMIT:
            # Feed readers need the article URL when following a section link; keep code blocks untouched.
            body = absolute_article_html(article.html, fragment_base=article.url)
            xml_sub(entry, "content", body, type="html")
        xml_sub(entry, "summary", article.description, type="text")
    return xml_document(feed)


def render_sitemap(articles: Sequence[Article], news_modified: datetime | None = None) -> str:
    root = ElementTree.Element("urlset", xmlns=_SITEMAP)
    articles_modified = max((article.modified_date() for article in articles), default=None)
    # Only the two archive indexes have a trustworthy change date: their newest article or edition.
    locations: tuple[tuple[str, datetime | None], ...] = (
        (f"{METADATA.site_url}/", None),
        (f"{METADATA.site_url}/articles/", articles_modified),
        (f"{METADATA.site_url}/news/", news_modified),
        (f"{METADATA.site_url}/connect", None),
        (f"{METADATA.site_url}/privacy", None),
        (f"{METADATA.site_url}/agents", None),
        (f"{METADATA.site_url}/sites/", None),
        *((page.url, None) for page in SITE_PAGES),
    )
    for location, modified in locations:
        url = xml_sub(root, "url")
        xml_sub(url, "loc", location)
        if modified is not None:
            xml_sub(url, "lastmod", modified.date().isoformat())
    for article in articles:
        url = xml_sub(root, "url")
        xml_sub(url, "loc", article.url)
        xml_sub(url, "lastmod", article.modified_date().date().isoformat())
    return xml_document(root)


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
            for service in SERVICES
        ),
        "",
        f"- [Professional profile and experience]({METADATA.site_url}/#about)",
        "",
        "## Channels",
        "",
        *(f"- [{social.name}]({social.url})" for social in METADATA.socials),
        *(f"- [{playlist.title}]({playlist.url}): {playlist.description}" for playlist in YOUTUBE_SERIES),
        "",
        "## Machine-readable portfolio",
        "",
        f"- [Connect]({METADATA.site_url}/connect): LinkedIn, a downloadable contact card, and the full website.",
        f"- [Agent guide]({METADATA.site_url}/agents): Connection instructions, tool examples, and data boundaries.",
        f"- [API catalog]({METADATA.site_url}/.well-known/api-catalog): Public API discovery.",
        f"- [Agent skill]({METADATA.site_url}/.well-known/agent-skills/index.json): Research articles and compare hosting or MCP context-cost scenarios.",
        f"- [MCP server]({METADATA.site_url}/agents#mcp): Read-only portfolio tools, resources, and prompts at `{METADATA.site_url}/mcp` (Streamable HTTP, POST only).",
        f"- [JSON profile]({METADATA.site_url}/api/profile): Canonical portfolio and article index.",
        f"- [Profile schema]({METADATA.site_url}/api/profile/schema.json): JSON Schema for validating the profile response.",
        f"- [JSON news]({METADATA.site_url}/api/news): Curated daily tech news archive as JSON.",
        f"- [News schema]({METADATA.site_url}/api/news/schema.json): JSON Schema for validating the news response.",
        f"- [MCP discovery]({METADATA.site_url}/.well-known/mcp/server-card.json): Available tools, prompts, and portfolio resource URI.",
        f"- [Bulk article export]({METADATA.site_url}/llms-full.txt): This index plus every public article in Markdown. Use only when you need the whole collection and your reader can handle its size; otherwise search and read individual articles.",
        f"- Article source: append `.md` to any article slug ({METADATA.site_url}/articles/<slug>.md) for its raw Markdown.",
        "- If your reader rejects `text/markdown`, read the regular article URL as HTML; the full article requires no JavaScript.",
        f"- [Atom feed]({METADATA.site_url}/articles/feed.xml): Reverse-chronological publication feed.",
        f"- [News]({METADATA.site_url}/news/): Daily curated links, one page per day; request `Accept: text/markdown` on `/news/` or append `.md` to an edition (`{METADATA.site_url}/news/<YYYY-MM-DD>.md`) for Markdown.",
        f"- [News feed]({METADATA.site_url}{NEWS_FEED_PATH}): Atom feed with one entry per daily edition.",
        f"- [Sitemap]({METADATA.site_url}/sitemap.xml): Canonical hosted pages.",
        "",
        "## Expertise",
        "",
    ]
    lines.extend(f"- **{card.title}**: {card.description}" for card in EXPERTISE)
    lines.extend(("", "## Sites", ""))
    lines.extend(f"- [{page.title}]({page.url}): {page.description}" for page in SITE_PAGES)
    lines.extend(("", "## Articles", ""))
    lines.extend(
        f"- [{article.title}]({article.url}): {article.description} ([Markdown]({article.markdown_url()}))"
        for article in articles
    )
    lines.extend(("", "## Optional", "", f"- [PhD thesis]({THESIS.url}): {THESIS.title}"))
    lines.extend(f"- [{paper.title}]({paper.url}): {paper.venue}" for paper in PAPERS)
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
    lines.extend(("", article.markdown))
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
        services=SERVICES,
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


_MARKDOWN_UI_KEYS = frozenset(
    {"badge_type", "brand_color", "google_analytics_id", "icon", "image_alt", "image_url", "logo"}
)


def article_sections(article: Article) -> tuple[ArticleSectionLink, ...]:
    """List every heading anchor that the HTML renderer generated, at any level."""
    return tuple(
        ArticleSectionLink(title=heading.label, url=f"{article.url}#{heading.identifier}")
        for heading in article.headings
    )


def render_home_markdown(articles: tuple[ArticleSummary, ...]) -> bytes:
    """Render the complete public portfolio without scraping its HTML layout or leaking UI-only keys."""
    profile = _PORTFOLIO_ADAPTER.dump_python(portfolio_snapshot(articles), mode="json")
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
                if key in _MARKDOWN_UI_KEYS:
                    continue
                label = str(key).replace("_", " ").capitalize()
                if isinstance(item, (dict, list)):
                    lines.append("  " * depth + f"- {label}:")
                    append(item, depth + 1)
                elif item not in (None, ""):
                    lines.append("  " * depth + f"- {label}: {item}")
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    fields = [(k, v) for k, v in item.items() if k not in _MARKDOWN_UI_KEYS and v not in (None, "")]
                    for index, (key, child) in enumerate(fields):
                        indent = depth if index == 0 else depth + 1
                        label = str(key).replace("_", " ").capitalize()
                        if isinstance(child, (dict, list)):
                            lines.append("  " * indent + f"- {label}:")
                            append(child, indent + 1)
                        else:
                            lines.append("  " * indent + f"- {label}: {child}")
                else:
                    append(item, depth)
        elif value not in (None, ""):
            lines.append("  " * depth + f"- {value}")

    for name, value in profile.items():
        lines.extend(("", "## " + name.replace("_", " ").capitalize(), ""))
        append(value)
    return ("\n".join(lines) + "\n").encode()
