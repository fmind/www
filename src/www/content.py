"""Strict article loading and safe Markdown rendering."""

import html
import re
import tomllib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict
from mdit_py_plugins.footnote import footnote_plugin

from www.assets import image_dimensions, video_dimensions
from www.data import METADATA
from www.highlighting import highlight_code
from www.markdown import rewrite_markdown_links
from www.models import DERIVATIVE_WIDTHS, SOURCE_EXTENSIONS, Article, ArticleSection, ArticleSummary, utc_midnight
from www.tags import is_tag, tag_names

WORDS_PER_MINUTE = 200
FIGURE_SIZES = "(max-width: 1312px) calc(100vw - 2rem), 1280px"
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_VIDEO = re.compile(r'<img src="(/static/img/articles/[^"]+\.mp4)" alt="([^"]*)"(?: [^>]*)?>')
_FIGURE = re.compile(r'<p>(<img src="(/static/img/articles/[^"]+)" alt="([^"]*)"(?: [^>]*)?>)</p>')
_CAPTION = re.compile(
    r'<figure><a ([^>]*)><img src="([^"]+)" alt="([^"]*)"([^>]*)></a></figure>\s*<p>(.*?)</p>',
    re.DOTALL,
)
_IMAGE = re.compile(r'<img src="(/static/img/articles/[^"]+)"')
_MEDIA_PREFIX = "/static/img/articles/"
# Ids that pages/article.html, base.html and their partials already own. A body
# heading that slugs to one of them takes a "-N" suffix instead of duplicating it.
_TEMPLATE_IDS = frozenset(
    {
        "article-author",
        "article-sections",
        "consent",
        "copy-link-status",
        "main-content",
        "related-articles",
        "section-menu",
        "section-toolbar",
    }
)
_HTML_TAG = re.compile(r"<[^>]*>")
_KNOWN_FRONTMATTER = {
    "title",
    "description",
    "date",
    "updated",
    "slug",
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
    # tokens from image children. This also applies the article typographer, so
    # the accessible text matches the label as readers see it in prose.
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


def _read_frontmatter(header: bytes) -> dict[str, object]:
    try:
        metadata = tomllib.loads(header.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ArticleError(f"frontmatter: {error}") from error
    for key in metadata:
        if key not in _KNOWN_FRONTMATTER:
            line = _unknown_key_line(header.decode(), key)
            raise ArticleError(f"frontmatter: unknown key {key!r} at line {line}")
    return metadata


def _string(metadata: Mapping[str, object], field: str, *, required: bool = False) -> str:
    value = metadata.get(field, "")
    if not isinstance(value, str):
        raise ArticleError(f"{field} must be a string")
    if required and not value:
        raise ArticleError(f"{field} is required")
    return value


def _parse_date(field: str, value: str) -> datetime:
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ArticleError(f"{field} {value!r}: expected YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ArticleError(f"{field} {value!r}: {error}") from error
    return utc_midnight(parsed)


def _cover(static_dir: Path, slug: str, static_files: Mapping[str, Path] | None = None) -> str:
    prefix = f"/static/img/articles/{slug}/cover."
    if static_files is not None:
        candidates = sorted(
            route
            for route in static_files
            if route.startswith(prefix)
            and "/" not in route.removeprefix(prefix)
            and PurePosixPath(route).stem == "cover"
        )
    else:
        directory = static_dir / "img" / "articles" / slug
        # Accept every source format that `build_images.py` derives from, case-insensitively
        # as it does, and pick by its fixed preference order when several exist.
        candidates = sorted(
            f"/static/img/articles/{slug}/{path.name}"
            for path in directory.glob("cover.*")
            if path.stem == "cover" and path.is_file()
        )
    for extension in SOURCE_EXTENSIONS:
        for candidate in candidates:
            if PurePosixPath(candidate).suffix.lower() == extension:
                return candidate
    raise ArticleError(
        f'missing article cover under "static/img/articles/{slug}": '
        f"expected one of {', '.join(f'cover{extension}' for extension in SOURCE_EXTENSIONS)}"
    )


def _card_cover(static_dir: Path, slug: str, static_files: Mapping[str, Path] | None = None) -> str:
    relative = f"img/articles/{slug}/cover-800.webp"
    route = f"/static/{relative}"
    exists = route in static_files if static_files is not None else (static_dir / relative).is_file()
    if not exists:
        raise ArticleError(f'missing card cover "static/{relative}": run `mise run build:images`')
    return route


def _heading_slug(text: str) -> str:
    # Heading ids are published URLs that external links depend on: only ASCII
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


def _heading_text(tokens: Sequence[Token]) -> str:
    return "".join(
        _heading_text(token.children)
        if token.children
        else " "
        if token.type in {"softbreak", "hardbreak"}
        else token.content
        if token.type in {"text", "code_inline"}
        else ""
        for token in tokens
    )


def _html_inline(content: str) -> Token:
    token = Token("html_inline", "", 0)
    token.content = content
    return token


def _normalize_headings(tokens: Sequence[Token]) -> tuple[tuple[ArticleSection, ...], tuple[ArticleSection, ...]]:
    """Anchor every heading and return all headings, then the h2 sections alone."""
    headings: list[ArticleSection] = []
    sections: list[ArticleSection] = []
    openings = [token for token in tokens if token.type == "heading_open"]
    if openings:
        shallowest = min(int(token.tag[1]) for token in openings)
        if shallowest != 2:
            shift = 2 - shallowest
            for token in openings:
                token.tag = f"h{min(6, int(token.tag[1]) + shift)}"
            for token in tokens:
                if token.type == "heading_close":
                    token.tag = f"h{min(6, int(token.tag[1]) + shift)}"

    seen: dict[str, int] = {}
    identifiers = set(_TEMPLATE_IDS)
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or index + 1 >= len(tokens):
            continue
        inline = tokens[index + 1]
        base = _heading_slug(inline.content)
        count = seen.get(base, 0)
        identifier = base if count == 0 else f"{base}-{count}"
        # A literal heading such as "Setup-1" can collide with a repeat of "Setup".
        while identifier in identifiers:
            count += 1
            identifier = f"{base}-{count}"
        seen[base] = count + 1
        # Slugs never contain "_", so the text id cannot match an earlier heading id.
        text_identifier = f"{identifier}_text"
        identifiers.update((identifier, text_identifier))
        token.attrSet("id", identifier)
        # Name the heading by its text alone: its name would otherwise also take the
        # section link's label, as in "Setup Link to section: Setup".
        token.attrSet("aria-labelledby", text_identifier)
        # Name the anchor with the rendered heading text: the raw source would
        # expose Markdown link syntax and URLs to screen readers and MCP sections.
        label = " ".join(_heading_text(inline.children or []).split())
        heading = ArticleSection(identifier=identifier, label=label)
        headings.append(heading)
        if token.tag == "h2":
            sections.append(heading)
        # Append a separate link so authored links inside headings never nest.
        link = Token("link_open", "a", 1)
        link.attrSet("href", f"#{identifier}")
        link.attrSet("class", "heading-anchor")
        link.attrSet("aria-label", f"Link to section: {label}")
        # A drawn icon keeps section controls out of copied/imported heading text.
        marker = _html_inline(
            '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" focusable="false">'
            '<path d="M4 9h16M3 15h16M10 3 8 21M16 3l-2 18"/></svg>'
        )
        inline.children = [
            _html_inline(f'<span id="{text_identifier}">'),
            *(inline.children or []),
            _html_inline("</span>"),
            link,
            marker,
            Token("link_close", "a", -1),
        ]
    return tuple(headings), tuple(sections)


def _absolute_destination(destination: str) -> str:
    if destination.startswith("/") and not destination.startswith("//"):
        return METADATA.site_url + destination
    return destination


def _search_words(tokens: Sequence[Token]) -> Iterator[str]:
    """Yield the text readers see, without link or image destinations."""
    for token in tokens:
        if token.children:
            # Inline content and image alt text; heading anchors add only html_inline markup.
            yield from _search_words(token.children)
        elif token.type in {"text", "code_inline"}:
            yield token.content
        elif token.type in {"fence", "code_block"}:
            yield token.info
            yield token.content


@dataclass(frozen=True, slots=True)
class _RenderedMarkdown:
    html: str
    headings: tuple[ArticleSection, ...]
    sections: tuple[ArticleSection, ...]
    media: tuple[tuple[str, str], ...]
    search_text: str
    # The Markdown export: the source with root-relative link destinations made absolute.
    markdown: str


def _render_markdown(markdown: str) -> _RenderedMarkdown:
    """Parse the body once and derive the page HTML, search text, and Markdown export."""
    environment: EnvType = {}
    tokens = _ARTICLE_MARKDOWN.parse(markdown, environment)
    headings, sections = _normalize_headings(tokens)
    rendered = _ARTICLE_MARKDOWN.renderer.render(tokens, _ARTICLE_MARKDOWN.options, environment)
    # Read sources and alt text from the Markdown tokens after `_image_rule` set the
    # final alt: caption folding later empties a figure's HTML alt on purpose.
    media = tuple(
        (str(child.attrGet("src") or ""), str(child.attrGet("alt") or ""))
        for token in tokens
        if token.type == "inline"
        for child in token.children or ()
        if child.type == "image"
    )
    return _RenderedMarkdown(
        # Strikethrough uses the semantic HTML5 element that published pages carry.
        html=rendered.replace("<s>", "<del>").replace("</s>", "</del>"),
        headings=headings,
        sections=sections,
        media=media,
        search_text=" ".join(_search_words(tokens)),
        # Rewrite after rendering: the inline rewriter updates the footnote counters in `environment`.
        markdown=rewrite_markdown_links(markdown, _absolute_destination, tokens, environment),
    )


def _caption_text(fragment: str) -> str:
    unescaped = html.unescape(_HTML_TAG.sub("", fragment))
    return " ".join(unescaped.replace("\ufeff", " ").split())


def _fold_captions(body: str) -> str:
    def replace(match: re.Match[str]) -> str:
        link, source, alt, extra, caption = match.groups()
        if not _caption_text(alt) or _caption_text(caption) != _caption_text(alt):
            return match.group(0)
        return f'<figure><a {link}><img src="{source}" alt=""{extra}></a><figcaption>{caption}</figcaption></figure>'

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


def _asset_exists(static_dir: Path, source: str, static_files: Mapping[str, Path] | None = None) -> bool:
    if static_files is not None:
        return source in static_files
    return _asset_path(static_dir, source).is_file()


def _validate_body_media(
    static_dir: Path, media: Sequence[tuple[str, str]], static_files: Mapping[str, Path] | None = None
) -> None:
    """Reject body images and videos that cannot render: CSP allows only local media."""
    for source, alt in media:
        if not source.startswith(_MEDIA_PREFIX):
            raise ArticleError(f"body media {source!r} must be a file under {_MEDIA_PREFIX}")
        if not _asset_exists(static_dir, source, static_files):
            raise ArticleError(f"missing body media {source!r}")
        if not alt.strip():
            raise ArticleError(f"body media {source!r} needs alt text")


def _image_size(static_dir: Path, source: str, known: Mapping[str, tuple[int, int]] | None = None) -> tuple[int, int]:
    path = _asset_path(static_dir, source)
    # The image build records dimensions so a cold start need not read lazily fetched media.
    if known and (dimensions := known.get(source)):
        return dimensions
    try:
        return image_dimensions(path)
    except (OSError, ValueError) as error:
        raise ArticleError(f"decode body image {source.removeprefix('/')!r}: {error}") from error


def _video_size(
    static_dir: Path, source: str, known: Mapping[str, tuple[int, int]] | None = None
) -> tuple[int, int] | None:
    path = _asset_path(static_dir, source)
    if known and (dimensions := known.get(source)):
        return dimensions
    try:
        return video_dimensions(path)
    except OSError:
        return None


def _source_set(
    static_dir: Path, source: str, source_width: int, static_files: Mapping[str, Path] | None = None
) -> tuple[str, str]:
    path = PurePosixPath(source)
    candidates: list[str] = []
    for width in DERIVATIVE_WIDTHS:
        if width >= source_width:
            continue
        derivative = str(path.with_name(f"{path.stem}-{width}.webp"))
        if _asset_exists(static_dir, derivative, static_files):
            candidates.append(f"{derivative} {width}w")
    if not candidates:
        return "", ""
    candidates.append(f"{source} {source_width}w")
    return ", ".join(candidates), FIGURE_SIZES


def enhance_body_images(
    body: str,
    static_dir: Path,
    image_sizes: Mapping[str, tuple[int, int]] | None = None,
    static_files: Mapping[str, Path] | None = None,
) -> str:
    def replace_video(match: re.Match[str]) -> str:
        source, alt = match.group(1), match.group(2)
        dimensions = _video_size(static_dir, source, image_sizes)
        size_attrs = f' width="{dimensions[0]}" height="{dimensions[1]}"' if dimensions else ""
        # Start playback via data-autoplay in JS only when prefers-reduced-motion is not active.
        return (
            f'<video{size_attrs} muted loop playsinline data-autoplay controls aria-label="{alt}">'
            f'<source src="{source}" type="video/mp4">Your browser does not support embedded video.</video>'
        )

    body = _VIDEO.sub(replace_video, body)
    body = _FIGURE.sub(
        r'<figure><a href="\2" target="_blank" rel="noopener" aria-label="\3 (opens the full-resolution image in a new tab)">\1</a></figure>',
        body,
    )
    body = _fold_captions(body)
    position = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal position
        source = match.group(1)
        width, height = _image_size(static_dir, source, image_sizes)
        srcset, sizes = _source_set(static_dir, source, width, static_files)
        # The first figure may be visible, but text can push it far below the fold.
        # Let the browser prioritize it instead of competing with fonts and CSS.
        loading = "" if position == 0 else ' loading="lazy"'
        position += 1
        responsive = f' srcset="{srcset}" sizes="{sizes}"' if srcset else ""
        return f'<img{loading} decoding="async" width="{width}" height="{height}"{responsive} src="{source}"'

    return _IMAGE.sub(replace, body)


def parse_article(
    name: str,
    data: bytes,
    static_dir: Path = Path("static"),
    image_sizes: Mapping[str, tuple[int, int]] | None = None,
    static_files: Mapping[str, Path] | None = None,
) -> Article:
    try:
        header, markdown_bytes = split_frontmatter(data)
        metadata = _read_frontmatter(header)
        title = _string(metadata, "title", required=True)
        description = _string(metadata, "description", required=True)
        date_value = _string(metadata, "date", required=True)
        slug = _string(metadata, "slug", required=True)
        if not _SLUG.fullmatch(slug):
            raise ArticleError(f"invalid slug {slug!r}")
        # Search snippets, feeds, and link previews reuse the description verbatim.
        if description.rstrip().endswith(("…", "...")):
            raise ArticleError("description must end with a complete sentence, not an ellipsis")
        if Path(name).stem != slug:
            raise ArticleError(f"filename must match slug {slug!r}")

        raw_tags = metadata.get("tags", [])
        if not isinstance(raw_tags, list) or any(not isinstance(tag, str) for tag in raw_tags):
            raise ArticleError("tags must be an array of strings")
        tags = tuple(raw_tags)
        if not tags:
            raise ArticleError("at least one tag is required")
        for index, tag in enumerate(tags):
            if not is_tag(tag):
                raise ArticleError(f"unknown tag {tag!r} (allowed: {', '.join(tag_names())})")
            if tag in tags[:index]:
                raise ArticleError(f"duplicate tag {tag!r}")
        raw_draft = metadata.get("draft", False)
        if not isinstance(raw_draft, bool):
            raise ArticleError("draft must be a boolean")

        published = _parse_date("date", date_value)
        updated_value = _string(metadata, "updated")
        updated = _parse_date("updated", updated_value) if updated_value else published
        if updated < published:
            raise ArticleError("updated date must not precede publish date")
        image_path = _cover(static_dir, slug, static_files)
        card_image_path = _card_cover(static_dir, slug, static_files)
        markdown = markdown_bytes.decode("utf-8")
        rendered = _render_markdown(markdown)
        _validate_body_media(static_dir, rendered.media, static_files)
        # The body shows the cover with reviewed alt text; social cards and
        # JSON-LD reuse it, so one description serves every surface. The title covers a body without it.
        cover_prefix = f"{_MEDIA_PREFIX}{slug}/cover."
        cover_alt = next((alt for source, alt in rendered.media if source.startswith(cover_prefix)), "")
        body = enhance_body_images(rendered.html, static_dir, image_sizes, static_files)
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
            draft=raw_draft,
            url=article_url,
            image_url=METADATA.site_url + image_path,
            card_image_url=METADATA.site_url + card_image_path,
            image_alt=" ".join(cover_alt.split()) or title,
            reading_minutes=reading_minutes,
            markdown=rendered.markdown,
            search_text=rendered.search_text,
            html=body,
            headings=rendered.headings,
            sections=rendered.sections,
        )
    except ArticleError as error:
        # Every rejection above states only its cause; the file is named once, here.
        raise ArticleError(f'parse "{name}": {error}') from error
    except UnicodeDecodeError as error:
        raise ArticleError(f'parse "{name}": body must be UTF-8: {error}') from error


def load_articles(
    content_dir: Path = Path("content/articles"),
    static_dir: Path = Path("static"),
    image_sizes: Mapping[str, tuple[int, int]] | None = None,
    static_files: Mapping[str, Path] | None = None,
) -> ArticleCollection:
    names = tuple(sorted(content_dir.glob("*.md")))
    if not names:
        raise ArticleError(f'list articles: no files match "{content_dir}/*.md"')
    by_slug: dict[str, Article] = {}
    articles: list[Article] = []
    for path in names:
        # A file name must equal its slug, so two files never share one.
        article = parse_article(path.as_posix(), path.read_bytes(), static_dir, image_sizes, static_files)
        articles.append(article)
        by_slug[article.slug] = article
    articles.sort(key=lambda article: (-article.date.timestamp(), article.slug))
    return ArticleCollection(tuple(articles), MappingProxyType(by_slug))


def visible_articles(articles: Sequence[Article], include_drafts: bool = False) -> tuple[Article, ...]:
    return tuple(article for article in articles if include_drafts or not article.draft)


def article_summaries(articles: Sequence[Article]) -> tuple[ArticleSummary, ...]:
    return tuple(article.summary() for article in articles)
