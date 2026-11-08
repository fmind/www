from datetime import UTC, datetime
from xml.etree import ElementTree

from www.data import METADATA, YOUTUBE_SERIES
from www.models import Article
from www.publications import (
    ATOM_FULL_CONTENT_LIMIT,
    absolute_article_html,
    article_markdown_index,
    related_article_index,
    related_articles,
    render_article_markdown,
    render_atom_feed,
    render_llms_full,
    render_llms_txt,
    render_sitemap,
)


def article(
    slug: str,
    day: int,
    *tags: str,
    updated: datetime | None = None,
) -> Article:
    return Article(
        slug=slug,
        title=slug.title(),
        description="Summary",
        date=datetime(2026, 1, day, tzinfo=UTC),
        updated=updated or datetime(2026, 1, day, tzinfo=UTC),
        tags=tags,
        url=f"{METADATA.site_url}/articles/{slug}/",
        card_image_url=f"{METADATA.site_url}/static/img/articles/{slug}/cover-800.webp",
        markdown="Body with [root](https://www.fmind.dev/articles/).",
        html='<p><a href="/articles/">Body</a><img src="/static/x.webp"></p>',
        reading_minutes=3,
    )


SITEMAP = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def test_sitemap_lists_every_article_with_its_updated_date() -> None:
    native = article("native", 2, updated=datetime(2026, 2, 3, tzinfo=UTC))
    other = article("other", 1)
    body = render_sitemap((native, other), datetime(2026, 3, 4, tzinfo=UTC))
    urls = {
        element.findtext("s:loc", namespaces=SITEMAP): element.findtext("s:lastmod", namespaces=SITEMAP)
        for element in ElementTree.fromstring(body).iterfind("s:url", SITEMAP)  # noqa: S314 - trusted serializer output
    }

    assert urls[native.url] == "2026-02-03"
    assert urls[other.url] == "2026-01-01"
    # Archive indexes change with their newest entry; other pages carry no guessed date.
    assert urls[f"{METADATA.site_url}/articles/"] == "2026-02-03"
    assert urls[f"{METADATA.site_url}/news/"] == "2026-03-04"
    assert urls[f"{METADATA.site_url}/"] is None
    assert render_sitemap((native, other)).count("<lastmod>") == 3


def test_atom_feed_limits_full_content_and_absolutizes_assets() -> None:
    articles = tuple(
        article(
            f"article-{index}",
            ATOM_FULL_CONTENT_LIMIT + 2 - index,
            "Agent",
            updated=datetime(2026, 2, 3, tzinfo=UTC) if index == 0 else None,
        )
        for index in range(ATOM_FULL_CONTENT_LIMIT + 2)
    )
    body = render_atom_feed(articles)

    assert body.count('<content type="html">') == ATOM_FULL_CONTENT_LIMIT
    assert "\n  <entry>\n    <title>" in body
    assert f"<icon>{METADATA.site_url}/logo.png</icon>" in body
    assert 'xmlns:media="http://search.yahoo.com/mrss/"' in body
    thumbnails = [
        element.get("url")
        for element in ElementTree.fromstring(body).iter("{http://search.yahoo.com/mrss/}thumbnail")  # noqa: S314
    ]
    assert thumbnails == [item.card_image_url for item in articles]
    assert "<updated>2026-02-03T00:00:00Z</updated>" in body
    assert f"{METADATA.site_url}/static/x.webp" in body
    ElementTree.fromstring(body)  # noqa: S314 - parses trusted local serializer output


def test_llms_and_article_markdown_surfaces_preserve_citation_metadata() -> None:
    item = article(
        "example",
        1,
        "Agent",
        updated=datetime(2026, 2, 1, tzinfo=UTC),
    )
    index = render_llms_txt((item,))
    full = render_llms_full(index, (item,), article_markdown_index((item,)))
    markdown = render_article_markdown(item)

    assert "## Machine-readable portfolio" in index
    assert f"- [MCP discovery]({METADATA.site_url}/.well-known/mcp/server-card.json): " in index
    channels = index.split("## Channels\n", 1)[1].split("\n## ", 1)[0]
    for social in METADATA.socials:
        assert f"- [{social.name}]({social.url})" in channels
    for playlist in YOUTUBE_SERIES:
        assert f"- [{playlist.title}]({playlist.url}): {playlist.description}" in channels
    assert f"[Markdown]({item.markdown_url()})" in index
    # llmstxt.org list items are "[name](url): notes" so parsers keep each note.
    assert f"- [{item.title}]({item.url}): {item.description} (" in index
    assert " — " not in index.split("## Sites\n", 1)[1]
    assert "## Full articles" in full
    assert markdown in full
    assert "- Author: [Médéric Hurier (Fmind)](https://www.fmind.dev/)" in markdown
    assert "- Updated: 2026-02-01" in markdown
    assert f"- URL: {item.url}" in markdown
    assert f"\n\n{item.markdown}\n" in markdown
    assert article_markdown_index((item,))[item.slug] == markdown


def test_related_articles_rank_shared_tags_then_collection_order() -> None:
    articles = (
        article("newest-unrelated", 5, "Cloud"),
        article("one-shared", 4, "Agent"),
        article("current", 3, "Agent", "MLOps"),
        article("two-shared", 2, "Agent", "MLOps"),
        article("older-unrelated", 1, "Security"),
    )

    assert [item.slug for item in related_articles(articles[2], articles)] == [
        "two-shared",
        "one-shared",
        "newest-unrelated",
    ]
    index = related_article_index(articles)
    assert set(index) == {item.slug for item in articles}
    assert all(item.slug not in {related.slug for related in index[item.slug]} for item in articles)


def test_absolute_article_html_only_rewrites_root_relative_urls() -> None:
    body = (
        '<a href="/x"><img src="/y" srcset="/y-800.webp 800w, /y-1280.webp 1280w"></a>'
        '<a href="https://example.com">x</a><img src="//cdn.example/z" srcset="//cdn.example/z 1x">'
    )
    rendered = absolute_article_html(body)

    assert f'href="{METADATA.site_url}/x"' in rendered
    assert f'src="{METADATA.site_url}/y"' in rendered
    assert f'srcset="{METADATA.site_url}/y-800.webp 800w, {METADATA.site_url}/y-1280.webp 1280w"' in rendered
    assert 'href="https://example.com"' in rendered
    assert 'src="//cdn.example/z" srcset="//cdn.example/z 1x"' in rendered


def test_atom_section_links_target_the_article() -> None:
    from dataclasses import replace

    item = replace(article("example", 1, "Agent"), html='<h2 id="section">Section<a href="#section">#</a></h2>')
    feed = ElementTree.fromstring(render_atom_feed((item,)))  # noqa: S314 - trusted serializer output
    content = feed.find("{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}content")
    assert content is not None
    assert content.text is not None
    assert f'href="{item.url}#section"' in content.text


def test_atom_entries_carry_their_tags_as_categories() -> None:
    feed = ElementTree.fromstring(render_atom_feed((article("tagged", 1, "Agent", "MLOps"),)))  # noqa: S314
    atom = "{http://www.w3.org/2005/Atom}"
    categories = feed.findall(f"{atom}entry/{atom}category")

    assert [category.get("term") for category in categories] == ["Agent", "MLOps"]
    assert {category.get("scheme") for category in categories} == {f"{METADATA.site_url}/articles/?tag="}
