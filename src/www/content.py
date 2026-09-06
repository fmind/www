"""Strict article loading and safe Markdown rendering."""

from __future__ import annotations

import html
import os
import re
import string
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from urllib.parse import urlsplit

from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict
from mdit_py_plugins.footnote import footnote_plugin
from PIL import Image, UnidentifiedImageError

from www.data import METADATA
from www.highlighting import highlight_code
from www.models import DERIVATIVE_WIDTHS, Article, ArticleSummary
from www.tags import is_tag, tag_names

WORDS_PER_MINUTE = 200
FIGURE_SIZES = "(max-width: 1312px) calc(100vw - 2rem), 1280px"
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_VIDEO = re.compile(r'<img src="(/static/img/articles/[^"]+\.mp4)" alt="([^"]*)">')
_FIGURE = re.compile(r'<p>(<img src="(/static/img/articles/[^"]+)" alt="([^"]*)">)</p>')
_CAPTION = re.compile(
    r'<figure><a ([^>]*)><img src="([^"]+)" alt="([^"]*)"></a></figure>\s*<p>(.*?)</p>',
    re.DOTALL,
)
_IMAGE = re.compile(r'<img src="(/static/img/articles/[^"]+)"')
_HTML_TAG = re.compile(r"<[^>]*>")
_INVALID_URL_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_THREE_BACKSLASH_BREAK = re.compile(r"(?<!\\)\\{3}(?=\r?\n|$)")
_URL_HOST_ASCII = frozenset(string.ascii_letters + string.digits + "-._~!$&'()*+,;=:%")
_KNOWN_FRONTMATTER = {
    "title",
    "description",
    "date",
    "updated",
    "slug",
    "canonical",
    "syndicated",
    "tags",
    "draft",
}


class ArticleError(ValueError):
    """An article cannot be accepted into the immutable startup collection."""


@dataclass(frozen=True, slots=True)
class ArticleCollection:
    all: tuple[Article, ...]
    by_slug: Mapping[str, Article]


def _fence(
    _renderer: object,
    tokens: Sequence[Token],
    index: int,
    _options: OptionsDict,
    _env: EnvType,
) -> str:
    token = tokens[index]
    language = token.info.strip().split(maxsplit=1)[0] if token.info.strip() else ""
    return highlight_code(token.content, language)


def _code_block(
    _renderer: object,
    tokens: Sequence[Token],
    index: int,
    _options: OptionsDict,
    _env: EnvType,
) -> str:
    return highlight_code(tokens[index].content)


def _image_rule(
    renderer: RendererHTML,
    tokens: Sequence[Token],
    index: int,
    options: OptionsDict,
    env: EnvType,
) -> str:
    token = tokens[index]
    # Reparse the raw label because markdown-it-py omits escaped punctuation
    # tokens from image children. This also applies the article typographer, as
    # Goldmark does when it derives accessible text from an image label.
    inline = _ARTICLE_MARKDOWN.parseInline(token.content, env)[0]
    token.attrSet("alt", renderer.renderInlineAsText(inline.children, options, env))
    return renderer.renderToken(tokens, index, options, env)


def _markdown() -> MarkdownIt:
    parser = MarkdownIt(
        "commonmark",
        {"html": False, "typographer": True, "xhtmlOut": False},
    ).use(footnote_plugin)
    parser.enable(("strikethrough", "table", "replacements", "smartquotes"))
    parser.add_render_rule("fence", _fence)
    parser.add_render_rule("code_block", _code_block)
    parser.add_render_rule("image", _image_rule)
    return parser


_ARTICLE_MARKDOWN = _markdown()


def split_frontmatter(data: bytes) -> tuple[bytes, bytes]:
    delimiter = b"+++"
    if not data.startswith(delimiter + b"\n"):
        raise ArticleError('frontmatter must start with "+++" on line 1')
    remainder = data[len(delimiter) + 1 :]
    end = remainder.find(b"\n+++\n")
    if end < 0:
        raise ArticleError('frontmatter opened on line 1 has no closing "+++" line')
    header = remainder[:end]
    markdown = remainder[end + len(delimiter) + 2 :].strip()
    if not markdown:
        raise ArticleError("article body is empty")
    return header, markdown


def _unknown_key_line(header: str, key: str) -> int:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=", re.MULTILINE)
    match = pattern.search(header)
    return header.count("\n", 0, match.start()) + 2 if match else 1


def _read_frontmatter(name: str, header: bytes) -> dict[str, object]:
    try:
        metadata = tomllib.loads(header.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ArticleError(f'parse "{name}" frontmatter: {error}') from error
    for key in metadata:
        if key not in _KNOWN_FRONTMATTER:
            line = _unknown_key_line(header.decode(), key)
            raise ArticleError(f'parse "{name}" frontmatter: unknown key {key!r} at line {line}')
    return metadata


def _string(metadata: Mapping[str, object], field: str, *, required: bool = False) -> str:
    value = metadata.get(field, "")
    if not isinstance(value, str):
        raise ArticleError(f"{field} must be a string")
    if required and not value:
        raise ArticleError("title, description, date, and slug are required")
    return value


def _validate_url(name: str, field: str, value: str) -> None:
    if not value:
        return
    invalid = (
        any(character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F for character in value)
        or _INVALID_URL_ESCAPE.search(value) is not None
    )
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        # Accessing port performs urllib's numeric and range validation.
        _port = parsed.port
    except ValueError:
        invalid = True
        parsed = urlsplit("")
        hostname = None
    if hostname is not None and any(
        ord(character) < 128 and character not in _URL_HOST_ASCII for character in hostname
    ):
        invalid = True
    if invalid or parsed.scheme != "https" or not parsed.netloc or not hostname:
        raise ArticleError(f'parse "{name}": {field} must be an absolute HTTPS URL')
    site_hostname = urlsplit(METADATA.site_url).hostname
    if (
        field == "canonical"
        and site_hostname is not None
        and hostname.casefold().rstrip(".") == site_hostname.casefold().rstrip(".")
    ):
        raise ArticleError(f'parse "{name}": canonical must not point at this site (omit it instead)')


def _parse_date(name: str, field: str, value: str) -> datetime:
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ArticleError(f'parse "{name}": {field} {value!r}: expected YYYY-MM-DD')
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ArticleError(f'parse "{name}": {field} {value!r}: {error}') from error
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)


def _cover(static_dir: Path, slug: str) -> str:
    directory = static_dir / "img" / "articles" / slug
    for extension in (".webp", ".gif", ".png", ".jpg"):
        candidate = directory / f"cover{extension}"
        if candidate.is_file():
            return f"/static/img/articles/{slug}/{candidate.name}"
    raise ArticleError(f'missing article cover under "static/img/articles/{slug}"')


def _card_cover(static_dir: Path, slug: str) -> str:
    relative = f"img/articles/{slug}/cover-800.webp"
    if not (static_dir / relative).is_file():
        raise ArticleError(f'missing card cover "static/{relative}": run `mise run build:images`')
    return f"/static/{relative}"


def _heading_slug(text: str) -> str:
    # Preserve Goldmark's published anchor contract byte-for-byte: only ASCII
    # letters and digits survive, while each ASCII space, hyphen, or underscore
    # becomes one hyphen. Non-ASCII bytes (including NBSP and accents) vanish.
    # Collapsing separators or transliterating Unicode would break old links.
    value = text.encode().strip(b" \t\r\n")
    slug = bytearray()
    for character in value:
        if 65 <= character <= 90:
            slug.append(character + 32)
        elif 97 <= character <= 122 or 48 <= character <= 57:
            slug.append(character)
        elif character in b" \t\r\n-_":
            slug.append(45)
    return slug.decode() or "heading"


def _normalize_headings(tokens: Sequence[Token]) -> None:
    headings = [token for token in tokens if token.type == "heading_open"]
    if headings:
        shallowest = min(int(token.tag[1]) for token in headings)
        if shallowest != 2:
            shift = 2 - shallowest
            for token in headings:
                token.tag = f"h{min(6, int(token.tag[1]) + shift)}"
            for token in tokens:
                if token.type == "heading_close":
                    token.tag = f"h{min(6, int(token.tag[1]) + shift)}"

    seen: dict[str, int] = {}
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or index + 1 >= len(tokens):
            continue
        inline = tokens[index + 1]
        base = _heading_slug(inline.content)
        count = seen.get(base, 0)
        seen[base] = count + 1
        token.attrSet("id", base if count == 0 else f"{base}-{count}")


def _normalize_goldmark_three_backslashes(tokens: Sequence[Token]) -> None:
    """Preserve the one archive construct Goldmark parses unlike CommonMark."""
    for token in tokens:
        if token.type != "inline" or not token.children:
            continue
        break_count = len(_THREE_BACKSLASH_BREAK.findall(token.content))
        if break_count == 0:
            continue

        for index, child in enumerate(token.children):
            if child.type == "text":
                # Goldmark substitutes dashes without markdown-it's word-boundary
                # restriction and leaves attribute-style quotes straight.
                child.content = child.content.replace("---", "\N{EM DASH}").replace("--", "\N{EN DASH}")
                child.content = re.sub(
                    r"=\N{LEFT DOUBLE QUOTATION MARK}([^\N{RIGHT DOUBLE QUOTATION MARK}\n]*)"
                    r"\N{RIGHT DOUBLE QUOTATION MARK}",
                    "=\N{QUOTATION MARK}\\1\N{QUOTATION MARK}",
                    child.content,
                )
                child.content = re.sub(
                    r"(^|\s)\"(?=\S)",
                    "\\1\N{LEFT DOUBLE QUOTATION MARK}",
                    child.content,
                )
            elif (
                child.type == "hardbreak"
                and break_count > 0
                and index > 0
                and token.children[index - 1].type == "text"
                and token.children[index - 1].content.endswith("\\")
            ):
                token.children[index - 1].content += "\\"
                child.type = "softbreak"
                break_count -= 1


def render_markdown(markdown: str) -> str:
    environment: EnvType = {}
    tokens = _ARTICLE_MARKDOWN.parse(markdown, environment)
    _normalize_goldmark_three_backslashes(tokens)
    _normalize_headings(tokens)
    rendered = _ARTICLE_MARKDOWN.renderer.render(tokens, _ARTICLE_MARKDOWN.options, environment)
    # Goldmark uses the semantic HTML5 element for GFM strikethrough.
    return rendered.replace("<s>", "<del>").replace("</s>", "</del>")


def _caption_text(fragment: str) -> str:
    unescaped = html.unescape(_HTML_TAG.sub("", fragment))
    return " ".join(unescaped.replace("\ufeff", " ").split())


def _fold_captions(body: str) -> str:
    def replace(match: re.Match[str]) -> str:
        link, source, alt, caption = match.groups()
        if not _caption_text(alt) or _caption_text(caption) != _caption_text(alt):
            return match.group(0)
        return f'<figure><a {link}><img src="{source}" alt=""></a><figcaption>{caption}</figcaption></figure>'

    return _CAPTION.sub(replace, body)


def _asset_path(static_dir: Path, source: str) -> Path:
    prefix = "/static/"
    if not source.startswith(prefix):
        raise ArticleError(f"body image is outside the static asset tree: {source!r}")
    root = static_dir.resolve()
    path = (root / source.removeprefix(prefix)).resolve()
    if not path.is_relative_to(root):
        raise ArticleError(f"body image escapes the static asset tree: {source!r}")
    return path


def _webp_chunk_dimensions(chunk: bytes, prefix: bytes, size: int) -> tuple[int, int] | None:
    if chunk == b"VP8X" and size == 10 and len(prefix) == 10:
        width = int.from_bytes(prefix[4:7], "little") + 1
        height = int.from_bytes(prefix[7:10], "little") + 1
        return (width, height) if width * height <= (1 << 32) - 1 else None
    if chunk == b"VP8 " and size >= 10 and len(prefix) == 10:
        if prefix[0] & 1 or prefix[3:6] != b"\x9d\x01\x2a":
            return None
        width = int.from_bytes(prefix[6:8], "little") & 0x3FFF
        height = int.from_bytes(prefix[8:10], "little") & 0x3FFF
        return (width, height) if width and height else None
    if chunk == b"VP8L" and size >= 5 and len(prefix) >= 5 and prefix[0] == 0x2F:
        packed = int.from_bytes(prefix[1:5], "little")
        if packed >> 29:
            return None
        return (packed & 0x3FFF) + 1, ((packed >> 14) & 0x3FFF) + 1
    return None


def _webp_size(path: Path) -> tuple[int, int] | None:
    """Read bounded WebP metadata while validating the complete RIFF shape."""
    with path.open("rb") as image:
        header = image.read(12)
        if len(header) != 12 or header[:4] != b"RIFF" or header[8:] != b"WEBP":
            return None
        file_size = os.fstat(image.fileno()).st_size
        if int.from_bytes(header[4:8], "little") + 8 != file_size:
            return None

        # Pillow's WebP plugin reads the complete compressed payload merely to
        # obtain dimensions. Validate every RIFF chunk boundary, but read only
        # the ten-byte dimension prefix so startup does not reread large media.
        offset = 12
        dimensions: tuple[int, int] | None = None
        while offset < file_size:
            chunk_header = image.read(8)
            if len(chunk_header) != 8:
                return None
            chunk_size = int.from_bytes(chunk_header[4:8], "little")
            data_end = offset + 8 + chunk_size
            next_offset = data_end + (chunk_size & 1)
            if data_end > file_size or next_offset > file_size:
                return None
            if dimensions is None:
                prefix = image.read(min(chunk_size, 10))
                dimensions = _webp_chunk_dimensions(chunk_header[:4], prefix, chunk_size)
                if dimensions is None:
                    return None
            if chunk_size & 1:
                image.seek(data_end)
                if image.read(1) != b"\0":
                    return None
            image.seek(next_offset)
            offset = next_offset
        return dimensions


def _image_size(static_dir: Path, source: str) -> tuple[int, int]:
    path = _asset_path(static_dir, source)
    try:
        if dimensions := _webp_size(path):
            return dimensions
        with Image.open(path) as image:
            return image.size
    except (OSError, UnidentifiedImageError) as error:
        raise ArticleError(f"decode body image {source.removeprefix('/')!r}: {error}") from error


def _source_set(static_dir: Path, source: str, source_width: int) -> tuple[str, str]:
    path = PurePosixPath(source)
    candidates: list[str] = []
    for width in DERIVATIVE_WIDTHS:
        if width >= source_width:
            continue
        derivative = str(path.with_name(f"{path.stem}-{width}.webp"))
        if _asset_path(static_dir, derivative).is_file():
            candidates.append(f"{derivative} {width}w")
    if not candidates:
        return "", ""
    candidates.append(f"{source} {source_width}w")
    return ", ".join(candidates), FIGURE_SIZES


def enhance_body_images(body: str, static_dir: Path) -> tuple[str, str, str]:
    body = _VIDEO.sub(
        r'<video muted loop playsinline autoplay controls aria-label="\2"><source src="\1" type="video/mp4">Your browser does not support embedded video.</video>',
        body,
    )
    body = _FIGURE.sub(
        r'<figure><a href="\2" target="_blank" rel="noopener" aria-label="\3 (opens the full-resolution image in a new tab)">\1</a></figure>',
        body,
    )
    body = _fold_captions(body)
    lead_srcset = ""
    lead_sizes = ""
    position = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal lead_srcset, lead_sizes, position
        source = match.group(1)
        width, height = _image_size(static_dir, source)
        srcset, sizes = _source_set(static_dir, source, width)
        loading = "" if position == 0 else ' loading="lazy"'
        priority = ' fetchpriority="high"' if position == 0 else ""
        if position == 0:
            lead_srcset, lead_sizes = srcset, sizes
        position += 1
        responsive = f' srcset="{srcset}" sizes="{sizes}"' if srcset else ""
        return f'<img{loading}{priority} decoding="async" width="{width}" height="{height}"{responsive} src="{source}"'

    return _IMAGE.sub(replace, body), lead_srcset, lead_sizes


def parse_article(name: str, data: bytes, static_dir: Path = Path("static")) -> Article:
    try:
        header, markdown_bytes = split_frontmatter(data)
        metadata = _read_frontmatter(name, header)
        title = _string(metadata, "title", required=True)
        description = _string(metadata, "description", required=True)
        date_value = _string(metadata, "date", required=True)
        slug = _string(metadata, "slug", required=True)
        canonical = _string(metadata, "canonical")
        syndicated = _string(metadata, "syndicated")
        if not _SLUG.fullmatch(slug):
            raise ArticleError(f'parse "{name}": invalid slug {slug!r}')
        if Path(name).stem != slug:
            raise ArticleError(f'parse "{name}": filename must match slug {slug!r}')
        _validate_url(name, "canonical", canonical)
        _validate_url(name, "syndicated", syndicated)

        raw_tags = metadata.get("tags", [])
        if not isinstance(raw_tags, list) or any(not isinstance(tag, str) for tag in raw_tags):
            raise ArticleError(f'parse "{name}": tags must be an array of strings')
        tags = tuple(raw_tags)
        if not tags:
            raise ArticleError(f'parse "{name}": at least one tag is required')
        for tag in tags:
            if not is_tag(tag):
                raise ArticleError(f'parse "{name}": unknown tag {tag!r} (allowed: {", ".join(tag_names())})')
        raw_draft = metadata.get("draft", False)
        if not isinstance(raw_draft, bool):
            raise ArticleError(f'parse "{name}": draft must be a boolean')

        published = _parse_date(name, "date", date_value)
        updated_value = _string(metadata, "updated")
        updated = _parse_date(name, "updated", updated_value) if updated_value else published
        if updated < published:
            raise ArticleError(f'parse "{name}": updated date must not precede publish date')
        image_path = _cover(static_dir, slug)
        card_image_path = _card_cover(static_dir, slug)
        markdown = markdown_bytes.decode("utf-8")
        body, srcset, sizes = enhance_body_images(render_markdown(markdown), static_dir)
        word_count = len(markdown.split())
        reading_minutes = max(1, (word_count + WORDS_PER_MINUTE - 1) // WORDS_PER_MINUTE)
        article_url = f"{METADATA.site_url}/articles/{slug}/"
        return Article(
            title=title,
            description=description,
            date=published,
            updated=updated,
            tags=tags,
            slug=slug,
            canonical=canonical,
            syndicated=syndicated,
            draft=raw_draft,
            url=article_url,
            image_url=METADATA.site_url + image_path,
            card_image_url=METADATA.site_url + card_image_path,
            cover_srcset=srcset,
            cover_sizes=sizes,
            image_alt=title,
            reading_minutes=reading_minutes,
            markdown=markdown,
            html=body,
        )
    except ArticleError as error:
        if str(error).startswith(f'parse "{name}"'):
            raise
        raise ArticleError(f'parse "{name}": {error}') from error
    except UnicodeDecodeError as error:
        raise ArticleError(f'parse "{name}": body must be UTF-8: {error}') from error


def load_articles(content_dir: Path = Path("content/articles"), static_dir: Path = Path("static")) -> ArticleCollection:
    names = tuple(sorted(content_dir.glob("*.md")))
    if not names:
        raise ArticleError(f'list articles: no files match "{content_dir}/*.md"')
    by_slug: dict[str, Article] = {}
    articles: list[Article] = []
    for path in names:
        article = parse_article(path.as_posix(), path.read_bytes(), static_dir)
        if article.slug in by_slug:
            raise ArticleError(f'parse "{path}": duplicate slug {article.slug!r}')
        articles.append(article)
        by_slug[article.slug] = article
    articles.sort(key=lambda article: (-article.date.timestamp(), article.slug))
    return ArticleCollection(tuple(articles), MappingProxyType(by_slug))


def visible_articles(articles: Sequence[Article], include_drafts: bool = False) -> tuple[Article, ...]:
    return tuple(article for article in articles if include_drafts or not article.draft)


def article_summaries(articles: Sequence[Article]) -> tuple[ArticleSummary, ...]:
    return tuple(article.summary() for article in articles)
