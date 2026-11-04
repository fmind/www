"""News editions: parsing, validation, exports, and the /news routes."""

from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest
from litestar import Litestar
from litestar.testing import TestClient

from www.data import METADATA
from www.news import (
    FEED_EDITION_LIMIT,
    NewsError,
    NewsIndex,
    adjacent_editions,
    canonicalize_url,
    load_news,
    parse_edition,
    render_news_feed,
    render_news_markdown,
    split_news_index,
)

type AppClient = TestClient[Any]

ATOM = {"a": "http://www.w3.org/2005/Atom"}
LINE = "- [{title}](https://example.com/{path}): {description}"


def edition_text(*paths: str) -> str:
    """A valid edition: the first three links are the highlights, the rest go under More."""
    lines = [LINE.format(title=f"Title {path}", path=path, description=f"About {path}.") for path in paths]
    more = ["", "## More", "", *lines[3:]] if len(lines) > 3 else []
    return "\n".join(["## Highlights", "", *lines[:3], *more]) + "\n"


def write_editions(directory: Path, editions: dict[str, str]) -> Path:
    directory.mkdir(exist_ok=True)
    for slug, text in editions.items():
        (directory / f"{slug}.md").write_text(text, encoding="utf-8")
    return directory


def test_parse_edition_reads_titles_with_colons_and_skips_blank_lines() -> None:
    text = "\n## Highlights\n\n- [GDPx: Measuring models](https://example.com/a?x=1): Benchmarks: 11 domains.\n\n"

    edition = parse_edition("2026-11-03", text)

    assert edition.date == date(2026, 11, 3)
    assert edition.title == "November 3, 2026"
    assert edition.url == f"{METADATA.site_url}/news/2026-11-03/"
    assert edition.markdown_path() == "/news/2026-11-03.md"
    [item] = edition.items
    assert (item.title, item.url, item.description) == (
        "GDPx: Measuring models",
        "https://example.com/a?x=1",
        "Benchmarks: 11 domains.",
    )
    assert item.domain == "example.com"
    assert edition.description.startswith("1 curated link on ")
    assert (edition.highlights, edition.more) == ((item,), ())


def test_parse_edition_splits_highlights_from_more() -> None:
    edition = parse_edition("2026-11-03", edition_text("a", "b", "c", "d", "e"))

    assert [item.title for item in edition.highlights] == ["Title a", "Title b", "Title c"]
    assert [item.title for item in edition.more] == ["Title d", "Title e"]
    assert edition.items == edition.highlights + edition.more


def test_parse_edition_keeps_parentheses_in_urls() -> None:
    text = "## Highlights\n- [Wiki](https://example.com/Foo_(bar)): About (it)."

    [item] = parse_edition("2026-11-03", text).items

    assert (item.url, item.description) == ("https://example.com/Foo_(bar)", "About (it).")


def test_parse_edition_names_special_editions_by_topic() -> None:
    edition = parse_edition("2026-04-23-google-next", edition_text("a", "b"))

    assert edition.topic == "Google Next"
    assert edition.title == "Google Next: April 23, 2026"
    assert edition.description.startswith("2 curated links on ")


@pytest.mark.parametrize(
    ("slug", "text", "message"),
    [
        ("news", edition_text("a"), "file name must be YYYY-MM-DD"),
        ("2026-02-30", edition_text("a"), "is not a calendar date"),
        ("2026-11-03-Topic", edition_text("a"), "file name must be YYYY-MM-DD"),
        ("2026-11-03", "", "edition has no links"),
        ("2026-11-03", "## Highlights\n", "edition has no links"),
        ("2026-11-03", "- [Title](https://example.com/a): No section.", "2026-11-03:1: start the edition with"),
        ("2026-11-03", "## Highlights\n- [Title](https://example.com/a) Missing colon", "2026-11-03:2: expected"),
        ("2026-11-03", "## Highlights\n- [Title](http://example.com/a): Plain HTTP", "2026-11-03:2: expected"),
        ("2026-11-03", "## Highlights\n- [A [B]](https://example.com/a): Brackets.", "2026-11-03:2: expected"),
        ("2026-11-03", "## Highlights\n- Title: https://example.com/a - Old format", "2026-11-03:2: expected"),
        ("2026-11-03", edition_text("a") + "\nnot a link", "2026-11-03:5: expected"),
        ("2026-11-03", "## More\n" + LINE.format(title="A", path="a", description="B."), "2026-11-03:1: unexpected"),
        ("2026-11-03", "# News\n" + edition_text("a"), "2026-11-03:1: unexpected heading"),
        ("2026-11-03", edition_text("a", "b", "c", "d") + "## More\n", "2026-11-03:10: unexpected heading"),
        (
            "2026-11-03",
            edition_text("a", "b", "c").replace(
                "## Highlights\n", "## Highlights\n" + LINE.format(title="D", path="d", description="E.") + "\n"
            ),
            "holds 3 links",
        ),
        (
            "2026-11-03",
            edition_text("a", "b") + "## More\n" + LINE.format(title="C", path="c", description="D."),
            "holds 3 links",
        ),
        ("2026-11-03", edition_text("a", "b", "c") + "## More\n", "'## More' has no links"),
        (
            "2026-11-03",
            "## Highlights\n" + LINE.format(title="A", path="a", description="word " * 31),
            "2026-11-03:2: description has 31 words; keep it to 30",
        ),
        ("2026-11-03", "+++\n" + edition_text("a"), "no closing '\\+\\+\\+' line"),
        ("2026-11-03", '+++\nupdated = "2026-11-04"\ndraft = true\n+++\n' + edition_text("a"), "holds only updated"),
        ("2026-11-03", "+++\nupdated = 2026-11-04\n+++\n" + edition_text("a"), "holds only updated"),
        ("2026-11-03", "+++\nupdated = \n+++\n" + edition_text("a"), "holds only updated"),
        ("2026-11-03", '+++\nupdated = "2026-02-30"\n+++\n' + edition_text("a"), "not a calendar date"),
        ("2026-11-03", '+++\nupdated = "2026-11-02"\n+++\n' + edition_text("a"), "precedes the edition date"),
        ("2026-11-03", '+++\nupdated = "2026-11-04"\n+++\n## Highlights\nbad', "2026-11-03:5: expected"),
    ],
)
def test_parse_edition_rejects_invalid_files(slug: str, text: str, message: str) -> None:
    with pytest.raises(NewsError, match=message):
        parse_edition(slug, text)


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("https://example.com/post/?utm_source=x&id=7&fbclid=1#top", "https://example.com/post?id=7"),
        ("http://mobile.twitter.com/user/status/1?s=20", "https://x.com/user/status/1"),
        ("https://youtu.be/abc123?si=share", "https://www.youtube.com/watch?v=abc123"),
        ("https://www.youtube.com/live/abc123?feature=share", "https://www.youtube.com/watch?v=abc123"),
        ("https://m.youtube.com/watch?v=abc123&t=42", "https://www.youtube.com/watch?v=abc123"),
        ("https://www.youtube.com/@channel", "https://www.youtube.com/@channel"),
        ("https://arxiv.org/pdf/2601.00001v2.pdf", "https://arxiv.org/abs/2601.00001v2"),
    ],
)
def test_canonicalize_url_normalizes_hosts_and_strips_trackers(raw: str, canonical: str) -> None:
    assert canonicalize_url(raw) == canonical


@pytest.mark.parametrize("raw", ["ftp://example.com/file", "javascript:alert(1)", "example.com/no-scheme"])
def test_canonicalize_url_rejects_non_web_urls(raw: str) -> None:
    with pytest.raises(NewsError, match="unsupported or invalid URL"):
        canonicalize_url(raw)


def test_load_news_sorts_newest_first_and_rejects_republished_links(tmp_path: Path) -> None:
    directory = write_editions(
        tmp_path / "news",
        {"2026-11-02": edition_text("a"), "2026-11-03": edition_text("b"), "2026-11-02-event": edition_text("c")},
    )

    assert [edition.slug for edition in load_news(directory)] == ["2026-11-03", "2026-11-02-event", "2026-11-02"]

    (directory / "2026-11-04.md").write_text(
        "## Highlights\n- [Again](https://example.com/a/?utm_medium=mail): Same link.\n", encoding="utf-8"
    )
    with pytest.raises(
        NewsError, match=r"2026-11-04:1: duplicate link https://example.com/a \(already in 2026-11-02:1\)"
    ):
        load_news(directory)


def test_load_news_names_unreadable_files(tmp_path: Path) -> None:
    directory = tmp_path / "news"
    directory.mkdir()
    (directory / "2026-11-03.md").write_bytes(b"\xff\xfe")

    with pytest.raises(NewsError, match="cannot read edition"):
        load_news(directory)


def test_load_news_rejects_files_that_are_not_markdown_editions(tmp_path: Path) -> None:
    directory = write_editions(tmp_path / "news", {"2026-11-03": edition_text("a")})
    (directory / "2026-11-04.txt").write_text(edition_text("b"), encoding="utf-8")

    with pytest.raises(NewsError, match=r"must be a YYYY-MM-DD\.md Markdown file"):
        load_news(directory)


def test_published_editions_are_valid() -> None:
    editions = load_news()

    assert editions, "content/news must hold at least one edition"
    assert len({edition.slug for edition in editions}) == len(editions)


def test_news_index_splits_by_the_latest_editions_week() -> None:
    slugs = ("2026-11-03", "2026-10-30", "2026-10-28-cloud", "2026-10-28", "2026-10-27", "2026-09-30")
    editions = tuple(parse_edition(slug, edition_text(slug)) for slug in slugs)

    index = split_news_index(editions)

    assert index.latest == editions[0]
    # The week counts back from the latest edition's date, not from today, and keeps special editions.
    assert [edition.slug for edition in index.recent] == ["2026-10-30", "2026-10-28-cloud", "2026-10-28"]
    assert [(month, [edition.slug for edition in group]) for month, group in index.archive] == [
        ("October 2026", ["2026-10-27"]),
        ("September 2026", ["2026-09-30"]),
    ]
    assert split_news_index(()) == NewsIndex(None, (), ())


def test_adjacent_editions_link_older_and_newer() -> None:
    editions = tuple(parse_edition(slug, edition_text(slug)) for slug in ("2026-11-03", "2026-11-02", "2026-11-01"))

    neighbours = adjacent_editions(editions)

    assert neighbours["2026-11-03"] == (editions[1], None)
    assert neighbours["2026-11-02"] == (editions[2], editions[0])
    assert neighbours["2026-11-01"] == (None, editions[1])


def test_markdown_export_adds_metadata_to_the_edition_source() -> None:
    source = edition_text("a", "b", "c", "d")
    edition = parse_edition("2026-11-03", source)

    markdown = render_news_markdown(edition)

    assert markdown.startswith("# News: November 3, 2026\n")
    assert f"- URL: {METADATA.site_url}/news/2026-11-03/\n\n## Highlights\n" in markdown
    assert markdown.endswith(source)


def test_corrected_edition_moves_its_feed_and_export_update_time() -> None:
    body = edition_text("a")
    corrected = parse_edition("2026-11-02", f'+++\nupdated = "2026-11-05"\n+++\n\n{body}')
    latest = parse_edition("2026-11-03", edition_text("b"))

    assert (corrected.updated, latest.updated) == (date(2026, 11, 5), date(2026, 11, 3))
    markdown = render_news_markdown(corrected)
    assert "- Published: 2026-11-02\n- Updated: 2026-11-05\n" in markdown
    assert markdown.endswith(body)
    assert "+++" not in markdown
    assert "- Updated:" not in render_news_markdown(latest)
    feed = ElementTree.fromstring(render_news_feed((latest, corrected)))  # noqa: S314 - trusted serializer output
    assert feed.findtext("a:updated", namespaces=ATOM) == "2026-11-05T00:00:00Z"
    entries = feed.findall("a:entry", ATOM)
    assert [entry.findtext("a:updated", namespaces=ATOM) for entry in entries] == [
        "2026-11-03T00:00:00Z",
        "2026-11-05T00:00:00Z",
    ]
    assert entries[1].findtext("a:published", namespaces=ATOM) == "2026-11-02T00:00:00Z"


def test_feed_has_one_escaped_entry_per_recent_edition() -> None:
    hostile = (
        "## Highlights\n- [<script>alert(1)</script>](https://example.com/x?a=1&b=2): Uses <b>markup</b> & entities."
    )
    editions = tuple(
        parse_edition(
            f"2026-{month:02d}-{day:02d}", hostile if (month, day) == (12, 31) else edition_text(f"{month}-{day}")
        )
        for month in (12, 11)
        for day in range(31, 0, -1)
        if (month, day) != (11, 31)
    )

    feed = ElementTree.fromstring(render_news_feed(editions))  # noqa: S314 - trusted serializer output

    entries = feed.findall("a:entry", ATOM)
    assert len(entries) == FEED_EDITION_LIMIT
    assert feed.findtext("a:updated", namespaces=ATOM) == "2026-12-31T00:00:00Z"
    first = entries[0]
    assert first.findtext("a:title", namespaces=ATOM) == "News: December 31, 2026"
    assert first.findtext("a:id", namespaces=ATOM) == f"{METADATA.site_url}/news/2026-12-31/"
    content = first.findtext("a:content", namespaces=ATOM) or ""
    assert content.startswith("<h2>Highlights</h2><ul><li>")
    assert "<h2>More</h2>" not in content
    assert '<a href="https://example.com/x?a=1&amp;b=2">&lt;script&gt;alert(1)&lt;/script&gt;</a>' in content
    assert "Uses &lt;b&gt;markup&lt;/b&gt; &amp; entities." in content


def test_feed_without_editions_is_still_valid() -> None:
    feed = ElementTree.fromstring(render_news_feed(()))  # noqa: S314 - trusted serializer output

    assert feed.findall("a:entry", ATOM) == []
    assert feed.findtext("a:updated", namespaces=ATOM) == "1970-01-01T00:00:00Z"


@pytest.fixture(scope="module")
def news_client(make_app: Callable[..., Litestar], tmp_path_factory: pytest.TempPathFactory) -> Iterator[AppClient]:
    directory = write_editions(
        tmp_path_factory.mktemp("news"),
        {
            "2026-10-08-cloud-next": edition_text("special"),
            "2026-10-20": edition_text("older"),
            "2026-10-30": edition_text("old"),
            "2026-11-02": "## Highlights\n- [<img src=x onerror=alert(1)>](https://example.com/evil): <b>Bold</b> claim.",
            "2026-11-03": edition_text("new-1", "new-2", "new-3", "new-4"),
        },
    )
    with TestClient(make_app(news=load_news(directory))) as client:
        yield client


def test_news_index_shows_latest_edition_past_week_and_archive(news_client: AppClient) -> None:
    assert news_client.get("/news", follow_redirects=False).headers["location"] == "/news/"

    response = news_client.get("/news/")

    assert response.status_code == 200
    page = response.text
    assert 'href="https://example.com/new-1">Title new-1</a>' in page
    assert 'href="https://example.com/new-4">Title new-4</a>' in page
    # One ranked list of cards without section headings.
    assert ">Highlights<" not in page
    assert ">More<" not in page
    latest = page[page.index('aria-label="Links of November 3, 2026"') : page.index(">Past week</h2>")]
    assert latest.count('<li class="card') == 4
    assert latest.index("Title new-3") < latest.index("Title new-4")
    assert page.count('href="/news/2026-11-03/"') == 1
    week = page[page.index(">Past week</h2>") : page.index(">Archive</h2>")]
    # Each card is one link to its edition and says how many links the edition holds.
    assert 'class="after:absolute after:inset-0 after:rounded-[inherit]" href="/news/2026-11-02/"' in week
    assert 'href="/news/2026-10-30/"' in week
    assert "See all 1 link →" in week
    assert "Title old" in week
    assert "&lt;img src=x onerror=alert(1)&gt;" in week
    archive = page[page.index(">Archive</h2>") :]
    assert ">October 2026</h3>" in archive
    # One line per day: the date and how many links the edition holds.
    assert (
        'href="/news/2026-10-20/"><time datetime="2026-10-20">Tue, October 20</time></a> '
        '<span class="text-sm text-base-content/65">· 1 link</span>'
    ) in archive
    assert (
        'href="/news/2026-10-08-cloud-next/"><time datetime="2026-10-08">Thu, October 8</time> · Cloud Next</a>'
        in archive
    )
    assert "Title older" not in archive
    assert f'href="{METADATA.site_url}/news/feed.xml" title="Fmind news"' in page
    assert f'{METADATA.site_url}/articles/feed.xml" title="Fmind articles"' not in page
    assert 'href="/news/feed.xml" type="application/atom+xml"' in page


def test_news_navigation_marks_the_section_current(news_client: AppClient) -> None:
    for path in ("/news/", "/news/2026-11-03/"):
        page = news_client.get(path).text
        nav = page[page.index('aria-label="Primary navigation"') :]
        nav = nav[: nav.index("</nav>")]
        assert ">News</a>" in nav, path
        current = "page" if path == "/news/" else "true"
        assert f'href="/news/" aria-current="{current}">News</a>' in nav, path


def test_news_edition_page_links_neighbours_and_markdown(news_client: AppClient) -> None:
    assert news_client.get("/news/2026-11-02", follow_redirects=False).headers["location"] == "/news/2026-11-02/"

    response = news_client.get("/news/2026-11-02/")

    assert response.status_code == 200
    assert "Accept" in response.headers["vary"].split(",")
    assert response.headers["link"] == '</news/2026-11-02.md>; rel="alternate"; type="text/markdown"'
    page = response.text
    assert "<title>News: November 2, 2026 | Fmind</title>" in page
    assert 'href="/news/2026-10-30/" rel="prev"' in page
    assert 'href="/news/2026-11-03/" rel="next"' in page
    # Editions stay out of search results; /news/ and the feed lead readers to them.
    assert '<meta name="robots" content="noindex, follow"/>' in page
    assert '<link rel="canonical"' not in page
    assert 'aria-label="Links of November 2, 2026"' in page
    assert ">Highlights<" not in page
    # Titles and descriptions are text, never markup.
    assert "<img src=x" not in page
    assert "&lt;img src=x onerror=alert(1)&gt;" in page
    assert "&lt;b&gt;Bold&lt;/b&gt; claim." in page


def test_news_edition_markdown_by_suffix_and_negotiation(news_client: AppClient) -> None:
    exported = news_client.get("/news/2026-11-03.md")
    negotiated = news_client.get("/news/2026-11-03/", headers={"accept": "text/markdown"})

    for response in (exported, negotiated):
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/markdown; charset=utf-8"
        assert response.headers["access-control-allow-origin"] == "*"
        assert response.headers["link"] == f'<{METADATA.site_url}/news/2026-11-03/>; rel="canonical"'
        assert response.text.startswith("# News: November 3, 2026\n")
        assert "\n## More\n" in response.text
        assert response.headers["x-robots-tag"] == "noindex"
    assert "Accept" in negotiated.headers["vary"].split(",")
    revalidated = news_client.get("/news/2026-11-03.md", headers={"if-none-match": exported.headers["etag"]})
    assert revalidated.status_code == 304


@pytest.mark.parametrize("path", ["/news/2026-01-01/", "/news/2026-01-01.md", "/news/2026-11-03/extra", "/news/x/y/z"])
def test_unknown_news_paths_are_not_found(news_client: AppClient, path: str) -> None:
    response = news_client.get(path)

    assert response.status_code == 404
    assert 'content="noindex, follow"' in response.text


def test_news_feed_route_serves_cached_atom(news_client: AppClient) -> None:
    response = news_client.get("/news/feed.xml")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/atom+xml; charset=utf-8"
    assert response.headers["cache-control"] == "public, max-age=3600, must-revalidate"
    feed = ElementTree.fromstring(response.content)  # noqa: S314 - trusted serializer output
    assert [entry.findtext("a:title", namespaces=ATOM) for entry in feed.findall("a:entry", ATOM)] == [
        "News: November 3, 2026",
        "News: November 2, 2026",
        "News: October 30, 2026",
        "News: October 20, 2026",
        "News: Cloud Next: October 8, 2026",
    ]
    assert news_client.get("/news/feed.xml", headers={"if-none-match": response.headers["etag"]}).status_code == 304


def test_sitemap_lists_the_news_index_but_not_editions(news_client: AppClient) -> None:
    sitemap = news_client.get("/sitemap.xml").text
    llms = news_client.get("/llms.txt").text

    assert f"<loc>{METADATA.site_url}/news/</loc>" in sitemap
    assert "/news/2026-" not in sitemap
    assert f"- [News feed]({METADATA.site_url}/news/feed.xml)" in llms


def test_news_index_without_editions(make_app: Callable[..., Litestar]) -> None:
    with TestClient(make_app(news=())) as client:
        response = client.get("/news/")

    assert response.status_code == 200
    assert "No news yet." in response.text
    assert "Past week" not in response.text
    assert "Archive" not in response.text
