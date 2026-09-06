from datetime import UTC, datetime

from www.models import Article
from www.publications import article_index_data
from www.search import SEARCH_QUERY_LIMIT, SearchIndex, normalize_search_query


def article(slug: str, title: str, description: str, body: str, *tags: str) -> Article:
    return Article(
        slug=slug,
        title=title,
        description=description,
        markdown=body,
        tags=tags,
        date=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_search_ranks_boosted_fields_before_passing_body_mentions() -> None:
    index = SearchIndex(
        (
            article(
                "passing",
                "Unrelated notes",
                "Nothing to see",
                "A body that mentions kubeflow once. " + "filler words here. " * 100,
                "Cloud",
            ),
            article(
                "about",
                "Installing Kubeflow",
                "A guide to Kubeflow pipelines",
                "Body text.",
                "Cloud",
            ),
        )
    )

    assert [item.slug for item in index.search("kubeflow")] == ["about", "passing"]


def test_search_matches_body_case_and_plural_forms() -> None:
    index = SearchIndex(
        (
            article("agents", "Designing agents", "Architecture", "orchestration", "Agent"),
            article("terraform", "Other", "Topic", "terraform", "Cloud"),
        )
    )

    assert index.search("agent")[0].slug == "agents"
    assert index.search("AGENTS")[0].slug == "agents"
    assert index.search("ORCHESTRATION")[0].slug == "agents"
    assert index.search("terraform")[0].slug == "terraform"
    assert index.search("!!!") == ()


def test_normalize_search_query_trims_and_caps_unicode() -> None:
    assert normalize_search_query("  agents  ") == "agents"
    result = normalize_search_query("é" * (SEARCH_QUERY_LIMIT + 50))
    assert len(result) == SEARCH_QUERY_LIMIT
    assert "�" not in result


def test_article_index_composes_search_and_case_insensitive_tag() -> None:
    articles = (
        article("cloud", "Agents on Cloud Run", "Deploying agents", "Body", "Agent", "Cloud"),
        article("python", "Agents in Python", "Writing agents", "Body", "Agent", "Python"),
    )
    view = article_index_data(articles, SearchIndex(articles), "python", "agents")

    assert view.searching()
    assert view.active_tag == "Python"
    assert [item.slug for item in view.results] == ["python"]
    assert view.years == ()
