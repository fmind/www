"""Daily news editions: strict parsing, URL canonicalization, and the news feed and Markdown exports."""

import html
import re
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from xml.etree import ElementTree

from www.data import METADATA

NEWS_FEED_PATH = "/news/feed.xml"
FEED_EDITION_LIMIT = 30
# /news/ shows the latest edition in full, the rest of its week as highlight cards, and older editions one per line.
RECENT_DAYS = 7
NEWS_TOPICS = "AI agents, Python, security, Google Cloud, and engineering"

# An edition is Markdown: "## Highlights" with 1 to 3 links, then "## More" with the rest when it has more than 3.
# Each link is one list line: "- [Title](https://...): One-sentence description".
# A corrected edition starts with the article front matter's correction date: +++, updated = "YYYY-MM-DD", +++.
_SECTIONS = ("## Highlights", "## More")
HIGHLIGHT_LIMIT = 3
DESCRIPTION_WORD_LIMIT = 30
_LINE = re.compile(r"^- \[(?P<title>[^\[\]]+)\]\((?P<url>https://\S+?)\): (?P<description>\S.*)$")
# A daily edition is YYYY-MM-DD; a special edition appends a topic, such as 2026-04-23-google-next.
_SLUG = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})(?:-(?P<topic>[a-z0-9]+(?:-[a-z0-9]+)*))?$")
_STRIP_PARAMS = frozenset(
    {"si", "fbclid", "gclid", "feature", "s", "t", "igshid", "spm", "ref", "taid", "share_id", "is"}
)
_STRIP_PREFIXES = ("utm_", "ref_", "mc_")
_YOUTUBE_HOSTS = frozenset({"youtu.be", "youtube.com", "www.youtube.com", "m.youtube.com"})


class NewsError(ValueError):
    """A news edition cannot be accepted into the immutable startup collection."""


@dataclass(frozen=True, slots=True)
class NewsItem:
    title: str
    url: str
    description: str

    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc.removeprefix("www.")


@dataclass(frozen=True, slots=True)
class NewsEdition:
    slug: str
    date: date
    topic: str
    items: tuple[NewsItem, ...]
    highlight_count: int
    source: str
    updated: date

    @property
    def highlights(self) -> tuple[NewsItem, ...]:
        return self.items[: self.highlight_count]

    @property
    def more(self) -> tuple[NewsItem, ...]:
        return self.items[self.highlight_count :]

    @property
    def url(self) -> str:
        return f"{METADATA.site_url}/news/{self.slug}/"

    @property
    def path(self) -> str:
        return f"/news/{self.slug}/"

    def markdown_path(self) -> str:
        return f"/news/{self.slug}.md"

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
        return datetime(self.date.year, self.date.month, self.date.day, tzinfo=UTC)

    def modified(self) -> datetime:
        return datetime(self.updated.year, self.updated.month, self.updated.day, tzinfo=UTC)


def canonicalize_url(raw_url: str) -> str:
    """Normalize a URL for duplicate detection: standard hosts, no trackers, no fragment or trailing slash."""
    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise NewsError(f"unsupported or invalid URL {raw_url!r}")
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
    if host in ("arxiv.org", "www.arxiv.org", "export.arxiv.org") and path.startswith("/pdf/"):
        return f"https://arxiv.org/abs/{path.removeprefix('/pdf/').removesuffix('.pdf').strip('/')}"
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query)
        if key.lower() not in _STRIP_PARAMS and not key.lower().startswith(_STRIP_PREFIXES)
    ]
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse(("https", host, path, "", urlencode(query), ""))


def _split_front_matter(slug: str, text: str, edition_date: date) -> tuple[date, str, int]:
    """Return the correction date (the edition date when absent), the Markdown body, and the body's first line."""
    if not text.startswith("+++\n"):
        return edition_date, text, 1
    end = text.find("\n+++\n", 3)
    if end < 0:
        raise NewsError(f"{slug}: front matter opened on line 1 has no closing '+++' line")
    header = text[4:end]
    usage = 'front matter holds only updated = "YYYY-MM-DD"'
    try:
        metadata = tomllib.loads(header)
    except tomllib.TOMLDecodeError as error:
        raise NewsError(f"{slug}: {usage}: {error}") from error
    value = metadata.get("updated")
    if set(metadata) != {"updated"} or not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise NewsError(f"{slug}: {usage}")
    try:
        updated = date.fromisoformat(value)
    except ValueError as error:
        raise NewsError(f"{slug}: updated {value!r} is not a calendar date") from error
    if updated < edition_date:
        raise NewsError(f"{slug}: updated {value} precedes the edition date")
    return updated, text[end + 5 :], header.count("\n") + 4


def parse_edition(slug: str, text: str) -> NewsEdition:
    """Parse one edition file: optional front matter, section headings in order, and one link per nonblank line."""
    match = _SLUG.fullmatch(slug)
    if match is None:
        raise NewsError(f"{slug}: file name must be YYYY-MM-DD or YYYY-MM-DD-topic")
    try:
        edition_date = date.fromisoformat(match["date"])
    except ValueError as error:
        raise NewsError(f"{slug}: {match['date']} is not a calendar date") from error
    updated, body, first_line = _split_front_matter(slug, text, edition_date)
    items: list[NewsItem] = []
    sections = 0
    highlights = 0
    for number, line in enumerate(body.splitlines(), first_line):
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if sections == len(_SECTIONS) or line != _SECTIONS[sections]:
                raise NewsError(f"{slug}:{number}: unexpected heading; use '## Highlights', then '## More'")
            sections += 1
            continue
        if not sections:
            raise NewsError(f"{slug}:{number}: start the edition with '## Highlights'")
        entry = _LINE.fullmatch(line)
        if entry is None:
            raise NewsError(f"{slug}:{number}: expected '- [Title](https://...): Description'")
        description = entry["description"].strip()
        if (words := len(description.split())) > DESCRIPTION_WORD_LIMIT:
            raise NewsError(f"{slug}:{number}: description has {words} words; keep it to {DESCRIPTION_WORD_LIMIT}")
        items.append(NewsItem(entry["title"].strip(), entry["url"], description))
        highlights += sections == 1
    if not items:
        raise NewsError(f"{slug}: edition has no links")
    if highlights > HIGHLIGHT_LIMIT or (sections == len(_SECTIONS) and highlights != HIGHLIGHT_LIMIT):
        raise NewsError(f"{slug}: '## Highlights' holds {HIGHLIGHT_LIMIT} links, or every link of a smaller edition")
    if sections == len(_SECTIONS) and len(items) == highlights:
        raise NewsError(f"{slug}: '## More' has no links")
    topic = (match["topic"] or "").replace("-", " ").title()
    return NewsEdition(
        slug=slug,
        date=edition_date,
        topic=topic,
        items=tuple(items),
        highlight_count=highlights,
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


def render_news_markdown(edition: NewsEdition) -> str:
    lines = [
        f"# News: {edition.title}",
        "",
        f"> {edition.description}",
        "",
        f"- Author: [{METADATA.name} ({METADATA.alternate_name})]({METADATA.site_url}/)",
        f"- Published: {edition.date.isoformat()}",
        *([f"- Updated: {edition.updated.isoformat()}"] if edition.updated != edition.date else []),
        f"- URL: {edition.url}",
        "",
    ]
    return "\n".join(lines) + "\n" + edition.source.strip() + "\n"


def _edition_html(edition: NewsEdition) -> str:
    sections = []
    for heading, items in (("Highlights", edition.highlights), ("More", edition.more)):
        if items:
            entries = "".join(
                f'<li><a href="{html.escape(item.url)}">{html.escape(item.title)}</a>: {html.escape(item.description)}</li>'
                for item in items
            )
            sections.append(f"<h2>{heading}</h2><ul>{entries}</ul>")
    return "".join(sections)


def render_news_feed(editions: Sequence[NewsEdition]) -> str:
    """One Atom entry per edition, so a busy day never floods a reader with separate link entries."""
    atom = "http://www.w3.org/2005/Atom"
    feed = ElementTree.Element("feed", xmlns=atom)

    def sub(parent: ElementTree.Element, name: str, text: str = "", **attributes: str) -> ElementTree.Element:
        child = ElementTree.SubElement(parent, name, attributes)
        child.text = text
        return child

    def stamp(value: datetime) -> str:
        return value.isoformat(timespec="seconds").replace("+00:00", "Z")

    sub(feed, "title", "Fmind news")
    sub(feed, "subtitle", f"Daily curated links on {NEWS_TOPICS}.")
    sub(feed, "id", f"{METADATA.site_url}/news/")
    entries = editions[:FEED_EDITION_LIMIT]
    # A correction moves an entry's `updated`, so feed readers fetch it again.
    latest = max((edition.modified() for edition in entries), default=datetime(1970, 1, 1, tzinfo=UTC))
    sub(feed, "updated", stamp(latest))
    sub(feed, "link", href=f"{METADATA.site_url}{NEWS_FEED_PATH}", rel="self", type="application/atom+xml")
    sub(feed, "link", href=f"{METADATA.site_url}/news/", rel="alternate", type="text/html")
    # Atom `icon` is the square branding image feed readers show next to the feed name.
    sub(feed, "icon", f"{METADATA.site_url}/logo.png")
    author = sub(feed, "author")
    sub(author, "name", METADATA.name)
    sub(author, "uri", f"{METADATA.site_url}/")
    for edition in entries:
        entry = sub(feed, "entry")
        sub(entry, "title", f"News: {edition.title}")
        sub(entry, "id", edition.url)
        sub(entry, "published", stamp(edition.published()))
        sub(entry, "updated", stamp(edition.modified()))
        sub(entry, "link", href=edition.url, rel="alternate", type="text/html")
        sub(entry, "content", _edition_html(edition), type="html")
        sub(entry, "summary", edition.description, type="text")
    ElementTree.indent(feed)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ElementTree.tostring(feed, encoding="unicode") + "\n"
