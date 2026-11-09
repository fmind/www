"""Daily news editions: strict parsing, URL canonicalization, and the news feed and Markdown exports."""

import html
import json
import re
import tomllib
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from xml.etree import ElementTree

from pydantic import TypeAdapter

from www.data import METADATA
from www.models import utc_midnight
from www.search import tokenize

NEWS_FEED_PATH = "/news/feed.xml"
FEED_EDITION_LIMIT = 30
# /news/ shows the latest edition in full, the rest of its week as preview cards, and older editions one per line.
RECENT_DAYS = 7
NEWS_TOPICS = "AI agents, Python, security, Google Cloud, and engineering"

# An edition is Markdown: one list line per link, "- [Title](https://...): One-sentence description",
# ordered from most to least interesting.
# A corrected or extended edition starts with front matter: +++, updated = "YYYY-MM-DD" or a UTC
# "YYYY-MM-DDTHH:MM:SSZ" timestamp (scripts.news stamps links added later the same day), +++.
DESCRIPTION_WORD_LIMIT = 30
_LINE = re.compile(r"^- \[(?P<title>[^\[\]]+)\]\((?P<url>https://\S+?)\): (?P<description>\S.*)$")
# Descriptions are plain prose: the .md export serves them raw, so no Markdown links, autolinks, or HTML.
_DESCRIPTION_MARKUP = re.compile(r"[\[\]<]|://")
# A daily edition is YYYY-MM-DD; a special edition appends a topic, such as 2026-04-23-google-next.
_UPDATED = re.compile(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}Z)?")
_SLUG = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})(?:-(?P<topic>[a-z0-9]+(?:-[a-z0-9]+)*))?$")
_STRIP_PARAMS = frozenset({"si", "fbclid", "gclid", "feature", "igshid", "spm", "ref", "taid", "share_id", "is"})
# X share links append s= and t= trackers; elsewhere t= or s= can name a topic or a timestamp, so keep them.
_X_STRIP_PARAMS = frozenset({"s", "t"})
_STRIP_PREFIXES = ("utm_", "ref_", "mc_")
_YOUTUBE_HOSTS = frozenset({"youtu.be", "youtube.com", "www.youtube.com", "m.youtube.com"})


class NewsError(ValueError):
    """A news edition cannot be accepted into the immutable startup collection."""


@dataclass(frozen=True, slots=True, kw_only=True)
class NewsItemSummary:
    title: str
    url: str
    domain: str
    description: str


@dataclass(frozen=True, slots=True, kw_only=True)
class NewsEditionSummary:
    slug: str
    date: date
    updated: datetime
    title: str
    topic: str
    description: str
    url: str
    markdown_url: str
    items: tuple[NewsItemSummary, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class NewsArchive:
    title: str
    description: str
    url: str
    feed_url: str
    updated: datetime
    editions: tuple[NewsEditionSummary, ...]


_NEWS_ARCHIVE_ADAPTER = TypeAdapter(NewsArchive)


@dataclass(frozen=True, slots=True)
class NewsItem:
    title: str
    url: str
    description: str

    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc.removeprefix("www.")

    def summary(self) -> NewsItemSummary:
        return NewsItemSummary(
            title=self.title,
            url=self.url,
            domain=self.domain,
            description=self.description,
        )


@dataclass(frozen=True, slots=True)
class NewsEdition:
    slug: str
    date: date
    topic: str
    items: tuple[NewsItem, ...]
    source: str
    updated: datetime
    # Search term counts for the edition header, then for each item: tokenized once at load, not on every query.
    search_terms: tuple[Counter[str], tuple[Counter[str], ...]] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        header = Counter(tokenize(f"{self.slug} {self.title} {self.topic}"))
        items: list[Counter[str]] = []
        for item in self.items:
            terms: Counter[str] = Counter()
            for text, boost in ((item.title, 3), (item.domain, 3), (item.description, 2), (item.url, 1)):
                terms.update({term: count * boost for term, count in Counter(tokenize(text)).items()})
            items.append(terms)
        object.__setattr__(self, "search_terms", (header, tuple(items)))

    @property
    def url(self) -> str:
        return f"{METADATA.site_url}/news/{self.slug}/"

    @property
    def path(self) -> str:
        return f"/news/{self.slug}/"

    def markdown_path(self) -> str:
        return f"/news/{self.slug}.md"

    def markdown_url(self) -> str:
        return f"{METADATA.site_url}{self.markdown_path()}"

    def date_label(self) -> str:
        return f"{self.date:%B} {self.date.day}, {self.date.year}"

    @property
    def title(self) -> str:
        return f"{self.topic}: {self.date_label()}" if self.topic else self.date_label()

    @property
    def description(self) -> str:
        count = len(self.items)
        noun = "link" if count == 1 else "links"
        return f"{count} curated {noun} on {NEWS_TOPICS}, selected by {METADATA.name}."

    def published(self) -> datetime:
        return utc_midnight(self.date)

    def modified(self) -> datetime:
        return self.updated

    def summary(self, items: Sequence[NewsItem] | None = None) -> NewsEditionSummary:
        selected = self.items if items is None else items
        return NewsEditionSummary(
            slug=self.slug,
            date=self.date,
            updated=self.updated,
            title=self.title,
            topic=self.topic,
            description=self.description,
            url=self.url,
            markdown_url=self.markdown_url(),
            items=tuple(item.summary() for item in selected),
        )


def canonicalize_url(raw_url: str) -> str:
    """Normalize a URL for duplicate detection: standard hosts, no trackers, no fragment or trailing slash."""
    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise NewsError(f"unsupported or invalid URL {raw_url!r}")
    if "@" in parsed.netloc:
        raise NewsError(f"URL {raw_url!r} carries credentials; share the public link")
    host = parsed.netloc.lower().removeprefix("mobile.")
    if host in ("twitter.com", "www.twitter.com", "www.x.com"):
        host = "x.com"
    path = parsed.path
    if host in _YOUTUBE_HOSTS:
        video = ""
        if host == "youtu.be":
            video = path.strip("/").split("/")[0]
        elif path.startswith(("/live/", "/shorts/", "/embed/")):
            parts = [part for part in path.split("/") if part]
            video = parts[1] if len(parts) > 1 else ""
        else:
            video = dict(parse_qsl(parsed.query)).get("v", "")
        if video:
            return f"https://www.youtube.com/watch?v={video}"
        host = "www.youtube.com"
    if (
        host in ("arxiv.org", "www.arxiv.org", "export.arxiv.org")
        and path.startswith(("/pdf/", "/html/"))
        and (paper := path.removeprefix("/pdf/").removeprefix("/html/").removesuffix(".pdf").strip("/"))
    ):
        return f"https://arxiv.org/abs/{paper}"
    strip = _STRIP_PARAMS | _X_STRIP_PARAMS if host == "x.com" else _STRIP_PARAMS
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in strip and not key.lower().startswith(_STRIP_PREFIXES)
    ]
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse(("https", host, path, parsed.params, urlencode(query), ""))


def utc_stamp(value: datetime) -> str:
    """Format a UTC time as RFC 3339 with seconds and a Z suffix."""
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


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


def _split_front_matter(slug: str, text: str, edition_date: date) -> tuple[datetime, str, int]:
    """Return the update time (the edition date when absent), the Markdown body, and the body's first line."""
    published = utc_midnight(edition_date)
    if not text.startswith("+++\n"):
        return published, text, 1
    end = text.find("\n+++\n", 3)
    if end < 0:
        raise NewsError(f"{slug}: front matter opened on line 1 has no closing '+++' line")
    header = text[4:end]
    usage = 'front matter holds only updated = "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM:SSZ"'
    try:
        metadata = tomllib.loads(header)
    except tomllib.TOMLDecodeError as error:
        raise NewsError(f"{slug}: {usage}: {error}") from error
    value = metadata.get("updated")
    if set(metadata) != {"updated"} or not isinstance(value, str) or not _UPDATED.fullmatch(value):
        raise NewsError(f"{slug}: {usage}")
    try:
        updated = datetime.fromisoformat(value if "T" in value else f"{value}T00:00:00Z")
    except ValueError as error:
        raise NewsError(f"{slug}: updated {value!r} is not a calendar date") from error
    if updated < published:
        raise NewsError(f"{slug}: updated {value} precedes the edition date")
    return updated, text[end + 5 :], header.count("\n") + 4


def parse_edition(slug: str, text: str) -> NewsEdition:
    """Parse one edition file: optional front matter and one link per nonblank line."""
    match = _SLUG.fullmatch(slug)
    if match is None:
        raise NewsError(f"{slug}: file name must be YYYY-MM-DD or YYYY-MM-DD-topic")
    try:
        edition_date = date.fromisoformat(match["date"])
    except ValueError as error:
        raise NewsError(f"{slug}: {match['date']} is not a calendar date") from error
    updated, body, first_line = _split_front_matter(slug, text, edition_date)
    items: list[NewsItem] = []
    for number, line in enumerate(body.splitlines(), first_line):
        line = line.strip()
        if not line:
            continue
        entry = _LINE.fullmatch(line)
        if entry is None:
            raise NewsError(f"{slug}:{number}: expected '- [Title](https://...): Description'")
        description = entry["description"].strip()
        if _DESCRIPTION_MARKUP.search(description):
            raise NewsError(f"{slug}:{number}: description must be plain text, without links, brackets, or HTML")
        if (words := len(description.split())) > DESCRIPTION_WORD_LIMIT:
            raise NewsError(f"{slug}:{number}: description has {words} words; keep it to {DESCRIPTION_WORD_LIMIT}")
        items.append(NewsItem(entry["title"].strip(), entry["url"], description))
    if not items:
        raise NewsError(f"{slug}: edition has no links")
    topic = (match["topic"] or "").replace("-", " ").title()
    return NewsEdition(
        slug=slug,
        date=edition_date,
        topic=topic,
        items=tuple(items),
        source=body,
        updated=updated,
    )


def load_news(directory: Path = Path("content/news")) -> tuple[NewsEdition, ...]:
    """Load every edition, newest first, and reject a link already published in another edition."""
    editions = []
    for path in sorted(directory.iterdir()):
        if path.suffix != ".md":
            raise NewsError(f"{path}: an edition must be a YYYY-MM-DD.md Markdown file")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise NewsError(f"{path}: cannot read edition") from error
        editions.append(parse_edition(path.stem, text))
    seen: dict[str, str] = {}
    for edition in editions:
        for number, item in enumerate(edition.items, 1):
            canonical = canonicalize_url(item.url)
            location = f"{edition.slug}:{number}"
            if canonical in seen:
                raise NewsError(f"{location}: duplicate link {canonical} (already in {seen[canonical]})")
            seen[canonical] = location
    return tuple(sorted(editions, key=lambda edition: (edition.date, edition.slug), reverse=True))


def adjacent_editions(editions: Sequence[NewsEdition]) -> dict[str, tuple[NewsEdition | None, NewsEdition | None]]:
    """Map each slug to its (older, newer) neighbours in a newest-first sequence."""
    return {
        edition.slug: (
            editions[index + 1] if index + 1 < len(editions) else None,
            editions[index - 1] if index > 0 else None,
        )
        for index, edition in enumerate(editions)
    }


@dataclass(frozen=True, slots=True)
class NewsIndex:
    latest: NewsEdition | None
    recent: tuple[NewsEdition, ...]
    archive: tuple[tuple[str, tuple[NewsEdition, ...]], ...]


def split_news_index(editions: Sequence[NewsEdition]) -> NewsIndex:
    """Split newest-first editions by the latest edition's date, so the page never depends on the clock."""
    if not editions:
        return NewsIndex(None, (), ())
    latest, *rest = editions
    start = latest.date - timedelta(days=RECENT_DAYS - 1)
    recent = tuple(edition for edition in rest if edition.date >= start)
    months: dict[str, list[NewsEdition]] = {}
    for edition in rest[len(recent) :]:
        months.setdefault(f"{edition.date:%B %Y}", []).append(edition)
    return NewsIndex(latest, recent, tuple((month, tuple(group)) for month, group in months.items()))


def _updated_label(value: datetime) -> str:
    """A date for a day-level correction, or the full UTC time for links added later that day."""
    return value.date().isoformat() if value.time() == datetime.min.time() else utc_stamp(value)


def render_news_markdown(edition: NewsEdition) -> str:
    lines = [
        f"# News: {edition.title}",
        "",
        f"> {edition.description}",
        "",
        f"- Author: [{METADATA.name} ({METADATA.alternate_name})]({METADATA.site_url}/)",
        f"- Published: {edition.date.isoformat()}",
        *([f"- Updated: {_updated_label(edition.updated)}"] if edition.updated != edition.published() else []),
        f"- URL: {edition.url}",
        "",
    ]
    return "\n".join(lines) + "\n" + edition.source.strip() + "\n"


def render_news_index_markdown(editions: Sequence[NewsEdition]) -> str:
    lines = [
        f"# News — {METADATA.name} ({METADATA.alternate_name})",
        "",
        f"> Daily curated links on {NEWS_TOPICS}, with one sentence on what changed.",
        "",
        f"- Author: [{METADATA.name} ({METADATA.alternate_name})]({METADATA.site_url}/)",
        f"- Feed: {METADATA.site_url}{NEWS_FEED_PATH}",
        f"- JSON API: {METADATA.site_url}/api/news",
        f"- URL: {METADATA.site_url}/news/",
    ]
    # Like the feed, carry the latest editions in full; the archive grows daily, so older ones are one link each.
    for edition in editions[:FEED_EDITION_LIMIT]:
        lines.extend(
            (
                "",
                f"## [{edition.title}]({edition.url}) ([Markdown]({edition.markdown_url()}))",
                "",
                edition.source.strip(),
            )
        )
    if older := editions[FEED_EDITION_LIMIT:]:
        lines.extend(("", "## Older editions", ""))
        lines.extend(f"- [{edition.title}]({edition.url}) ([Markdown]({edition.markdown_url()}))" for edition in older)
    return "\n".join(lines) + "\n"


def news_archive_snapshot(editions: Sequence[NewsEdition]) -> NewsArchive:
    return NewsArchive(
        title="Fmind news",
        description=f"Daily curated links on {NEWS_TOPICS}, selected by {METADATA.name}.",
        url=f"{METADATA.site_url}/news/",
        feed_url=f"{METADATA.site_url}{NEWS_FEED_PATH}",
        updated=max((edition.modified() for edition in editions), default=datetime(1970, 1, 1, tzinfo=UTC)),
        editions=tuple(edition.summary() for edition in editions),
    )


def render_news_json(editions: Sequence[NewsEdition]) -> bytes:
    """Render the canonical machine-readable news archive with a final newline."""
    return _NEWS_ARCHIVE_ADAPTER.dump_json(news_archive_snapshot(editions), indent=2) + b"\n"


def render_news_schema() -> bytes:
    """Describe the serialized news archive fields using the same model as the API."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{METADATA.site_url}/api/news/schema.json",
        **_NEWS_ARCHIVE_ADAPTER.json_schema(mode="serialization"),
    }
    return (json.dumps(schema, ensure_ascii=False, indent=2) + "\n").encode()


def search_news_editions(editions: Sequence[NewsEdition], query: str) -> tuple[NewsEditionSummary, ...]:
    """Search editions by relevance across edition dates, topics, link titles, domains, URLs, and descriptions."""
    terms = tuple(dict.fromkeys(tokenize(query)))
    if not terms or not editions:
        return ()

    hits: list[tuple[int, int, NewsEditionSummary]] = []
    for position, edition in enumerate(editions):
        edition_terms, item_terms = edition.search_terms
        header_matches = all(term in edition_terms for term in terms)
        matched_items: list[NewsItem] = []
        edition_score = sum(edition_terms[term] * 3 for term in terms) if header_matches else 0
        for item, counts in zip(edition.items, item_terms, strict=True):
            # An item matches when the edition header and its own text cover every term between them.
            if all(term in edition_terms or term in counts for term in terms):
                matched_items.append(item)
                edition_score += sum(counts[term] for term in terms)
        if header_matches:
            hits.append((edition_score, position, edition.summary()))
        elif matched_items:
            hits.append((edition_score, position, edition.summary(matched_items)))
    hits.sort(key=lambda hit: (-hit[0], hit[1]))
    return tuple(summary for _, _, summary in hits)


def _edition_html(edition: NewsEdition) -> str:
    entries = "".join(
        f'<li><a href="{html.escape(item.url)}">{html.escape(item.title)}</a>: {html.escape(item.description)}</li>'
        for item in edition.items
    )
    return f"<ul>{entries}</ul>"


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


def render_news_feed(editions: Sequence[NewsEdition]) -> str:
    """One Atom entry per edition, so a busy day never floods a reader with separate link entries."""
    entries = editions[:FEED_EDITION_LIMIT]
    # A correction moves an entry's `updated`, so feed readers fetch it again.
    latest = max((edition.modified() for edition in entries), default=datetime(1970, 1, 1, tzinfo=UTC))
    feed = atom_feed_root(
        "Fmind news",
        "/news/",
        NEWS_FEED_PATH,
        latest,
        subtitle=f"Daily curated links on {NEWS_TOPICS}.",
    )
    for edition in entries:
        entry = xml_sub(feed, "entry")
        xml_sub(entry, "title", f"News: {edition.title}")
        xml_sub(entry, "id", edition.url)
        xml_sub(entry, "published", utc_stamp(edition.published()))
        xml_sub(entry, "updated", utc_stamp(edition.modified()))
        xml_sub(entry, "link", href=edition.url, rel="alternate", type="text/html")
        xml_sub(entry, "content", _edition_html(edition), type="html")
        xml_sub(entry, "summary", edition.description, type="text")
    return xml_document(feed)
