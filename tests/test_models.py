from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from www.data import BIOGRAPHY, METADATA, SITE_PAGES, article_filter_url, get_structured_data, markdown_to_html
from www.models import Article, ArticleIndexView, Tag
from www.tags import TAGS, is_tag, sort_tags, tag_names, validate_tag_vocabulary


def article() -> Article:
    return Article(
        title="Example",
        description="Description",
        slug="example",
        canonical="https://medium.example/example",
        syndicated="https://medium.example/example",
        url=f"{METADATA.site_url}/articles/example/",
        image_url=f"{METADATA.site_url}/static/img/articles/example/cover.webp",
        card_image_url=f"{METADATA.site_url}/static/img/articles/example/cover-800.webp",
        image_alt="Cover",
        tags=("Agent", "LLM"),
        reading_minutes=7,
        date=datetime(2026, 1, 1, tzinfo=UTC),
        updated=datetime(2026, 2, 2, tzinfo=UTC),
        html="<p>body</p>",
    )


def test_article_summary_and_paths_preserve_discovery_contract() -> None:
    item = article()

    assert item.summary().title == item.title
    assert item.summary().image_url == item.image_url
    assert item.image_path() == "/static/img/articles/example/cover.webp"
    assert item.card_image_path() == "/static/img/articles/example/cover-800.webp"
    assert item.markdown_path() == "/articles/example.md"
    assert item.markdown_url() == f"{METADATA.site_url}/articles/example.md"
    assert item.canonical_url() == item.canonical
    assert item.modified_date() == item.updated


def test_article_fallbacks_and_foreign_images() -> None:
    item = Article(
        date=datetime(2026, 1, 1, tzinfo=UTC),
        image_url="https://cdn.example/cover.webp",
        card_image_url="https://cdn.example/cover-800.webp",
        url="https://example.test/article/",
    )

    assert item.modified_date() == item.date
    assert item.canonical_url() == item.url
    assert item.image_path() == item.image_url
    assert item.card_image_path() == item.card_image_url


def test_domain_models_are_frozen_and_search_view_switches_on_query() -> None:
    item = article()
    with pytest.raises(FrozenInstanceError):
        cast(Any, item).title = "Changed"

    assert ArticleIndexView(query="agents").searching()
    assert not ArticleIndexView(active_tag="Agent").searching()


def test_closed_tag_vocabulary_and_site_relation_are_stable() -> None:
    assert tag_names() == tuple(tag.name for tag in TAGS)
    assert is_tag("Agent")
    assert not is_tag("agent")
    assert sort_tags(("zeta", "Guide", "Agent", "alpha", "LLM")) == (
        "Agent",
        "LLM",
        "Guide",
        "alpha",
        "zeta",
    )
    assert SITE_PAGES[0].relates_to("the-affordable-ai-agents")


@pytest.mark.parametrize(
    ("tag", "message"),
    [
        (Tag("", "Description."), "tag name must not be empty"),
        (Tag("   ", "Description."), "tag name must not be empty"),
        (Tag(" Agent", "Description."), "tag name must be trimmed"),
        (Tag("Agent", ""), "tag description must not be empty"),
        (Tag("Agent", "\t"), "tag description must not be empty"),
        (Tag("Agent", "Description. "), "tag description must be trimmed"),
    ],
)
def test_tag_vocabulary_rejects_blank_or_untrimmed_fields(tag: Tag, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_tag_vocabulary((tag,))


def test_tag_vocabulary_rejects_duplicate_names_hidden_by_set_equality() -> None:
    tags = (
        Tag("Agent", "First description."),
        Tag("Agent", "Second description."),
    )

    assert {tag.name for tag in tags} == {"Agent"}
    with pytest.raises(ValueError, match="duplicate tag name: 'Agent'"):
        validate_tag_vocabulary(tags)


def test_template_helpers_keep_safe_markdown_filters_and_json_ld() -> None:
    assert markdown_to_html("A **bold** value") == "A <strong>bold</strong> value"
    assert markdown_to_html("<script>alert('unsafe')</script>") == "<!-- raw HTML omitted -->"
    assert all(
        markdown_to_html(paragraph).count("<strong>") == markdown_to_html(paragraph).count("</strong>")
        for paragraph in BIOGRAPHY
    )
    assert article_filter_url("Agent", "model serving") == "/articles/?tag=Agent&q=model+serving"

    structured = get_structured_data(article())
    assert '"mainEntityOfPage":"https://medium.example/example"' in structured
    assert '"dateModified":"2026-02-02"' in structured
