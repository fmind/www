import re
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

import www.content as content_module
from www.content import (
    FIGURE_SIZES,
    ArticleError,
    article_summaries,
    load_articles,
    parse_article,
    visible_articles,
)
from www.tags import tag_names


def image(width: int = 4, height: int = 3) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height)).save(output, format="PNG")
    return output.getvalue()


def webp_image(width: int, height: int, kind: bytes) -> bytes:
    output = BytesIO()
    mode = "RGBA" if kind == b"VP8X" else "RGB"
    color = (2, 3, 4, 127) if mode == "RGBA" else (2, 3, 4)
    with Image.new(mode, (width, height), color) as source_image:
        source_image.save(output, format="WEBP", lossless=kind == b"VP8L")
    data = output.getvalue()
    assert data[12:16] == kind
    return data


def assets(root: Path, extension: str = ".webp") -> Path:
    directory = root / "static" / "img" / "articles" / "example"
    directory.mkdir(parents=True)
    (directory / f"cover{extension}").write_bytes(image())
    (directory / "cover-800.webp").write_bytes(image())
    (directory / "figure.png").write_bytes(image())
    return root / "static"


def source(body: str = "Body.", **metadata: str) -> bytes:
    values = {
        "title": '"Example"',
        "description": '"Example article"',
        "date": '"2026-08-01"',
        "tags": '["Agent"]',
        "slug": '"example"',
        **metadata,
    }
    header = "\n".join(f"{key} = {value}" for key, value in values.items())
    return f"+++\n{header}\n+++\n\n{body}\n".encode()


def test_parse_article_rejects_unknown_frontmatter_with_source_line(tmp_path: Path) -> None:
    data = source(surprise='"not allowed"')

    with pytest.raises(ArticleError, match=r"unknown key .surprise.*line 7"):
        parse_article("content/articles/example.md", data, assets(tmp_path))


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({"slug": '"Bad Slug"'}, "invalid slug"),
        ({"tags": '["Data Science"]'}, "unknown tag"),
        ({"canonical": '"http://example.com/x"'}, "absolute HTTPS"),
        ({"canonical": '"https://www.fmind.dev/articles/example/"'}, "must not point at this site"),
        ({"updated": '"2026-07-01"'}, "must not precede"),
    ],
)
def test_parse_article_rejects_invalid_metadata(tmp_path: Path, metadata: dict[str, str], message: str) -> None:
    with pytest.raises(ArticleError, match=message):
        parse_article("content/articles/example.md", source(**metadata), assets(tmp_path))


@pytest.mark.parametrize("value", ['"2026-9-6"', '"20260906"', '"2026-09-06T00:00:00"'])
def test_parse_article_rejects_noncanonical_dates(tmp_path: Path, value: str) -> None:
    with pytest.raises(ArticleError, match="expected YYYY-MM-DD"):
        parse_article("content/articles/example.md", source(date=value), assets(tmp_path))


@pytest.mark.parametrize(
    "value",
    [
        '"https://example.com/a b"',
        '"https://exa mple.com/path"',
        '"https://example.com:invalid/path"',
        '"https://example.com:70000/path"',
        '"https://[127.0.0.1]/path"',
        '"https://example.com\\\\path"',
        '"https://example.com/%invalid"',
        '"https://example.com/\\npath"',
    ],
)
def test_parse_article_rejects_malformed_absolute_urls(tmp_path: Path, value: str) -> None:
    with pytest.raises(ArticleError, match="absolute HTTPS"):
        parse_article(
            "content/articles/example.md",
            source(syndicated=value),
            assets(tmp_path),
        )


@pytest.mark.parametrize(
    "value",
    [
        '"https://www.fmind.dev/articles/example/"',
        '"https://WWW.FMIND.DEV/articles/example/"',
        '"https://www.fmind.dev./articles/example/"',
    ],
)
def test_parse_article_rejects_every_self_canonical_host(tmp_path: Path, value: str) -> None:
    with pytest.raises(ArticleError, match="must not point at this site"):
        parse_article(
            "content/articles/example.md",
            source(canonical=value),
            assets(tmp_path),
        )


def test_parse_article_allows_a_host_that_only_prefixes_the_site_name(tmp_path: Path) -> None:
    item = parse_article(
        "content/articles/example.md",
        source(canonical='"https://www.fmind.dev.example/original"'),
        assets(tmp_path),
    )

    assert item.canonical == "https://www.fmind.dev.example/original"


def test_published_content_uses_every_tag_and_defines_its_color() -> None:
    used_tags = {tag for article in load_articles().all for tag in article.tags}
    names = tag_names()
    expected_tags = set(names)
    stylesheet = Path("assets/css/input.css").read_text(encoding="utf-8")

    assert len(names) == len(expected_tags)
    assert used_tags == expected_tags
    assert {tag for tag in expected_tags if f"[data-tag='{tag}']" in stylesheet} == expected_tags


def test_parse_article_renders_safe_extended_markdown_and_normalizes_headings(
    tmp_path: Path,
) -> None:
    body = """### Heading

#### Detail

Text with ~~old~~ syntax and a footnote.[^1]

<script>alert("unsafe")</script>

[^1]: Detail.
"""
    item = parse_article("content/articles/example.md", source(body), assets(tmp_path))

    assert '<h2 id="heading">' in item.html
    assert '<h3 id="detail">' in item.html
    assert "<del>old</del>" in item.html
    assert "footnote" in item.html
    assert "<script>" not in item.html
    assert item.reading_minutes >= 1


def test_heading_ids_preserve_the_published_goldmark_byte_contract(tmp_path: Path) -> None:
    body = """## Lockfile Decay & The Vulnerability Clock

## Moving\N{NO-BREAK SPACE}Forward

## 🛠️ Experience from the Field

## Profile - Médéric Hurier

## Duplicate

## Duplicate
"""
    item = parse_article("content/articles/example.md", source(body), assets(tmp_path))

    assert 'id="lockfile-decay--the-vulnerability-clock"' in item.html
    assert 'id="movingforward"' in item.html
    assert 'id="-experience-from-the-field"' in item.html
    assert 'id="profile---mdric-hurier"' in item.html
    assert 'id="duplicate"' in item.html
    assert 'id="duplicate-1"' in item.html


def test_image_alt_keeps_escapes_and_goldmark_typography(tmp_path: Path) -> None:
    item = parse_article(
        "content/articles/example.md",
        source(r"![Throughput from Lin Sun's C\# file\_name](/static/img/articles/example/figure.png)"),
        assets(tmp_path),
    )

    assert 'alt="Throughput from Lin Sun\N{RIGHT SINGLE QUOTATION MARK}s C# file_name"' in item.html


def test_goldmark_three_backslashes_keep_two_without_a_hard_break(tmp_path: Path) -> None:
    body = """> gh api --method POST -H \"Accept: application/vnd.github+json\" \\\\\\
> \N{NO-BREAK SPACE}\"/repos/$owner/$repo/rulesets\" --input=\".github/rulesets/main.json\" \\|\\| echo \"Failed to install rul
"""
    item = parse_article("content/articles/example.md", source(body), assets(tmp_path))

    assert "<br>" not in item.html
    assert (
        "gh api \N{EN DASH}method POST -H \N{LEFT DOUBLE QUOTATION MARK}Accept: "
        "application/vnd.github+json\N{RIGHT DOUBLE QUOTATION MARK} \\\\\n"
        "\N{NO-BREAK SPACE}\N{LEFT DOUBLE QUOTATION MARK}/repos/$owner/$repo/rulesets"
        "\N{RIGHT DOUBLE QUOTATION MARK} \N{EN DASH}input=&quot;.github/rulesets/main.json&quot; || "
        "echo \N{LEFT DOUBLE QUOTATION MARK}Failed to install rul"
    ) in item.html


def test_images_get_figures_dimensions_responsive_ladder_and_loading(tmp_path: Path) -> None:
    static = assets(tmp_path)
    directory = static / "img" / "articles" / "example"
    (directory / "cover.webp").write_bytes(image(2074, 1138))
    (directory / "cover-1280.webp").write_bytes(image())
    (directory / "figure.png").write_bytes(image(400, 300))
    body = """![cover](/static/img/articles/example/cover.webp)

![figure](/static/img/articles/example/figure.png)
"""

    item = parse_article("content/articles/example.md", source(body), static)

    assert '<figure><a href="/static/img/articles/example/cover.webp"' in item.html
    assert '<img fetchpriority="high" decoding="async" width="2074" height="1138"' in item.html
    assert (
        'srcset="/static/img/articles/example/cover-800.webp 800w, '
        "/static/img/articles/example/cover-1280.webp 1280w, "
        '/static/img/articles/example/cover.webp 2074w"' in item.html
    )
    assert f'sizes="{FIGURE_SIZES}"' in item.html
    assert '<img loading="lazy" decoding="async" width="400" height="300"' in item.html
    assert item.cover_srcset.endswith("cover.webp 2074w")
    assert item.cover_sizes == FIGURE_SIZES


@pytest.mark.parametrize("kind", [b"VP8 ", b"VP8L", b"VP8X"])
def test_webp_dimensions_use_bounded_headers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: bytes,
) -> None:
    path = tmp_path / "image.webp"
    path.write_bytes(webp_image(37, 19, kind))

    def unexpected_pillow_decode(_path: Path) -> None:
        pytest.fail("valid WebP dimensions must not require a complete Pillow decode")

    monkeypatch.setattr(content_module.Image, "open", unexpected_pillow_decode)

    # The optimization is intentionally private; this proves integration skips Pillow.
    assert content_module._image_size(tmp_path, "/static/image.webp") == (37, 19)  # noqa: SLF001


def test_webp_dimensions_reject_malformed_riff_and_chunk_bounds(tmp_path: Path) -> None:
    extended = webp_image(37, 19, b"VP8X")
    declared_size = bytearray(extended)
    declared_size[4:8] = (len(extended) - 9).to_bytes(4, "little")
    first_chunk = bytearray(extended)
    first_chunk[16:20] = len(extended).to_bytes(4, "little")
    later_chunk = bytearray(extended)
    later_chunk[34:38] = len(extended).to_bytes(4, "little")
    oversized_canvas = bytearray(extended)
    oversized_canvas[24:30] = b"\xff" * 6

    lossy = webp_image(37, 19, b"VP8 ")
    inter_frame = bytearray(lossy)
    inter_frame[20] |= 1
    malformed_start = bytearray(lossy)
    malformed_start[23:26] = b"bad"
    zero_canvas = bytearray(lossy)
    zero_canvas[26:30] = b"\0" * 4

    lossless = bytearray(webp_image(37, 19, b"VP8L"))
    lossless[24] |= 0xE0

    nonzero_padding = bytearray(extended)
    nonzero_padding.extend(b"JUNK\x01\0\0\0x\x01")
    nonzero_padding[4:8] = (len(nonzero_padding) - 8).to_bytes(4, "little")
    short_chunk_header = b"RIFF\x08\0\0\0WEBPVP8 "
    unknown_dimension_chunk = bytearray(lossy)
    unknown_dimension_chunk[12:16] = b"JUNK"

    for name, data in {
        "declared-size.webp": declared_size,
        "first-chunk.webp": first_chunk,
        "inter-frame.webp": inter_frame,
        "later-chunk.webp": later_chunk,
        "lossless-version.webp": lossless,
        "malformed-start.webp": malformed_start,
        "nonzero-padding.webp": nonzero_padding,
        "oversized-canvas.webp": oversized_canvas,
        "short-chunk-header.webp": short_chunk_header,
        "truncated.webp": extended[:-1],
        "unknown-dimension-chunk.webp": unknown_dimension_chunk,
        "zero-canvas.webp": zero_canvas,
    }.items():
        path = tmp_path / name
        path.write_bytes(data)
        assert content_module._webp_size(path) is None, name  # noqa: SLF001


def test_unrecognized_body_image_keeps_contextual_article_error(tmp_path: Path) -> None:
    static = assets(tmp_path)
    (static / "img" / "articles" / "example" / "figure.png").write_bytes(b"not an image")

    with pytest.raises(ArticleError, match=r"decode body image 'static/img/articles/example/figure\.png'"):
        parse_article(
            "content/articles/example.md",
            source("![figure](/static/img/articles/example/figure.png)"),
            static,
        )


def test_real_webp_dimensions_match_pillow() -> None:
    paths = sorted(Path("static/img/articles").rglob("*.webp"))

    assert len(paths) == 743
    for path in paths:
        with Image.open(path) as source_image:
            expected = source_image.size
        assert content_module._webp_size(path) == expected, path  # noqa: SLF001


def test_body_image_path_cannot_escape_static_tree(tmp_path: Path) -> None:
    static = assets(tmp_path)
    outside = tmp_path / "outside.png"
    outside.write_bytes(image(37, 19))
    body = "![escape](/static/img/articles/example/../../../../outside.png)"

    with pytest.raises(ArticleError, match="escapes the static asset tree"):
        parse_article("content/articles/example.md", source(body), static)


@pytest.mark.parametrize(
    ("alt", "paragraph", "caption"),
    [
        ("Relationship between agents", "Relationship between agents", True),
        (
            "Agent Docs — https://example.com/docs",
            "Agent Docs — [https://example.com/docs](https://example.com/docs)",
            True,
        ),
        ("Source: App", "This is the opening paragraph.", False),
    ],
)
def test_repeated_alt_paragraph_is_folded_into_caption(tmp_path: Path, alt: str, paragraph: str, caption: bool) -> None:
    item = parse_article(
        "content/articles/example.md",
        source(f"![{alt}](/static/img/articles/example/figure.png)\n\n{paragraph}"),
        assets(tmp_path),
    )

    assert ("<figcaption>" in item.html) is caption
    if caption:
        assert 'alt=""' in item.html


def test_inline_images_stay_inline_and_explicit_mp4_becomes_video(tmp_path: Path) -> None:
    static = assets(tmp_path)
    directory = static / "img" / "articles" / "example"
    (directory / "icon.png").write_bytes(image(16, 16))
    body = """See ![icon](/static/img/articles/example/icon.png) inline.

![editor demo](/static/img/articles/example/demo.mp4)
"""

    item = parse_article("content/articles/example.md", source(body), static)

    assert item.html.count("<figure>") == 0
    assert '<img fetchpriority="high" decoding="async" width="16" height="16"' in item.html
    assert "<video muted loop playsinline autoplay controls" in item.html
    assert 'aria-label="editor demo"' in item.html


def test_load_articles_sorts_and_filters_drafts(tmp_path: Path) -> None:
    static = assets(tmp_path)
    content = tmp_path / "content"
    content.mkdir()
    (content / "example.md").write_bytes(source(draft="true"))

    second_dir = static / "img" / "articles" / "second"
    second_dir.mkdir()
    (second_dir / "cover.webp").write_bytes(image())
    (second_dir / "cover-800.webp").write_bytes(image())
    second = source(slug='"second"', date='"2026-09-01"').replace(b"Example article", b"Second article")
    (content / "second.md").write_bytes(second)

    collection = load_articles(content, static)

    assert tuple(item.slug for item in collection.all) == ("second", "example")
    assert tuple(item.slug for item in visible_articles(collection.all)) == ("second",)
    assert len(visible_articles(collection.all, include_drafts=True)) == 2
    assert article_summaries(collection.all)[0].slug == "second"


def test_real_archive_loads_and_has_no_public_drafts() -> None:
    collection = load_articles()

    assert len(collection.all) == 59
    assert all(item.html.strip() and item.reading_minutes >= 1 for item in collection.all)
    assert not any(item.draft for item in collection.all)
    assert sum(item.html.count("<figure>") for item in collection.all) == 301
    assert sum(item.html.count("<figcaption>") for item in collection.all) == 248
    assert sum(item.html.count('<pre class="chroma">') for item in collection.all) == 154
    assert not any(re.search(r"<a\b[^>]*>\s*</a>", item.html) for item in collection.all)

    for item in collection.all:
        previous_level = 1  # The article template supplies the page's h1.
        for raw_level in re.findall(r"<h([2-6])\b", item.html):
            level = int(raw_level)
            assert level <= previous_level + 1, f"{item.slug}: h{previous_level} followed by h{level}"
            previous_level = level
