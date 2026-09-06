from datetime import UTC, datetime
from xml.etree import ElementTree

import pytest

from www.data import METADATA
from www.models import Article
from www.publications import (
    ATOM_FULL_CONTENT_LIMIT,
    absolute_article_html,
    absolute_markdown_links,
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
    canonical: str = "",
    syndicated: str = "",
) -> Article:
    return Article(
        slug=slug,
        title=slug.title(),
        description="Summary",
        date=datetime(2026, 1, day, tzinfo=UTC),
        updated=updated or datetime(2026, 1, day, tzinfo=UTC),
        tags=tags,
        url=f"{METADATA.site_url}/articles/{slug}/",
        markdown="Body with [root](/articles/).",
        html='<p><a href="/articles/">Body</a><img src="/static/x.webp"></p>',
        reading_minutes=3,
        canonical=canonical,
        syndicated=syndicated,
    )


def test_sitemap_excludes_external_canonicals_and_uses_updated_date() -> None:
    native = article("native", 2, updated=datetime(2026, 2, 3, tzinfo=UTC))
    syndicated = article("syndicated", 1, canonical="https://medium.example/syndicated")
    body = render_sitemap((native, syndicated))

    assert native.url in body
    assert "<lastmod>2026-02-03</lastmod>" in body
    assert syndicated.url not in body
    ElementTree.fromstring(body)  # noqa: S314 - parses trusted local serializer output


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
    assert "<updated>2026-02-03T00:00:00Z</updated>" in body
    assert f"{METADATA.site_url}/static/x.webp" in body
    ElementTree.fromstring(body)  # noqa: S314 - parses trusted local serializer output


def test_llms_and_article_markdown_surfaces_preserve_citation_metadata() -> None:
    item = article(
        "example",
        1,
        "Agent",
        updated=datetime(2026, 2, 1, tzinfo=UTC),
        canonical="https://example.net/original",
        syndicated="https://medium.example/example",
    )
    index = render_llms_txt((item,))
    full = render_llms_full(index, (item,))
    markdown = render_article_markdown(item)

    assert "## Machine-readable portfolio" in index
    assert f"[Markdown]({item.markdown_url()})" in index
    assert "## Full articles" in full
    assert item.markdown in full
    assert "- Updated: 2026-02-01" in markdown
    assert "- Canonical: https://example.net/original" in markdown
    assert f"]({METADATA.site_url}/articles/)" in markdown
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
    body = '<a href="/x"><img src="/y"></a><a href="https://example.com">x</a>'
    rendered = absolute_article_html(body)

    assert f'href="{METADATA.site_url}/x"' in rendered
    assert f'src="{METADATA.site_url}/y"' in rendered
    assert 'href="https://example.com"' in rendered


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("[root](/articles/)", "[root](https://www.fmind.dev/articles/)"),
        ("[root](</articles/>)", "[root](<https://www.fmind.dev/articles/>)"),
        ("[root][r]\n\n[r]: /articles/\n", "[root](https://www.fmind.dev/articles/)\n\n[r]: /articles/\n"),
        ("![root](/static/cover.webp)", "![root](https://www.fmind.dev/static/cover.webp)"),
        ("[external](//example.org/path)", "[external](//example.org/path)"),
        ("`[literal](/keep/)`", "`[literal](/keep/)`"),
        ("```markdown\n[literal](/keep/)\n```", "```markdown\n[literal](/keep/)\n```"),
        ("    [literal](/keep/)\n", "    [literal](/keep/)\n"),
        ("`unclosed\n\n[root](/articles/)\n\n`", "`unclosed\n\n[root](https://www.fmind.dev/articles/)\n\n`"),
        (
            '![c]\n\n[c]: /cover.webp (Say "hi")\n',
            '![c](https://www.fmind.dev/cover.webp "Say \\"hi\\"")\n\n[c]: /cover.webp (Say "hi")\n',
        ),
        ("![![nested](/keep/)](/cover.webp)", "![![nested](/keep/)](https://www.fmind.dev/cover.webp)"),
        ("<script>\n[literal](/keep/)\n</script>\n", "<script>\n[literal](/keep/)\n</script>\n"),
        ("", ""),
    ],
)
def test_markdown_response_rewrites_only_rendered_links(source: str, expected: str) -> None:
    assert absolute_markdown_links(source) == expected
