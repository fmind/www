"""Page metadata keeps discovery and indexing rules explicit."""

import json

import pytest

from www.assets import ApplicationAssets
from www.content import ArticleCollection
from www.data import BADGES, METADATA, SITE_PAGES, get_structured_data
from www.models import ArticleIndexView, PageMetadata
from www.news import NEWS_FEED_PATH, parse_edition
from www.pages import (
    agents_metadata,
    article_index_metadata,
    connect_metadata,
    home_metadata,
    news_edition_metadata,
    news_index_metadata,
    not_found_metadata,
    privacy_metadata,
    scan_metadata,
    site_index_metadata,
    site_page_metadata,
    site_structured_data,
)


def test_search_and_tag_metadata_titles_and_indexing(
    snapshots: tuple[ApplicationAssets, ArticleCollection],
) -> None:
    first = snapshots[1].all[0]
    searching = article_index_metadata(ArticleIndexView(query="agents", results=(first,)))
    tagged_search = article_index_metadata(ArticleIndexView(active_tag="Agent", query="agents", results=(first,)))
    tagged = article_index_metadata(ArticleIndexView(active_tag="Agent"))

    assert searching.no_index
    assert searching.canonical == f"{METADATA.site_url}/articles/"
    assert searching.preload_image == first.card_image_path()
    assert searching.title == f"Search: agents | Articles | {METADATA.name} ({METADATA.alternate_name})"
    assert tagged_search.no_index
    assert tagged_search.title == f"Search: agents (Agent) | Articles | {METADATA.name} ({METADATA.alternate_name})"
    assert not tagged.no_index
    assert tagged.canonical == f"{METADATA.site_url}/articles/"
    assert tagged.title == f"Agent Articles | {METADATA.name} ({METADATA.alternate_name})"


def test_home_and_not_found_metadata_have_opposite_indexing() -> None:
    structured = get_structured_data()

    assert home_metadata(structured).is_home
    assert not_found_metadata().no_index
    assert not_found_metadata().canonical == ""
    assert not_found_metadata().structured_data == "", "a missing page must not claim to be the profile"


def test_person_claims_only_active_credentials() -> None:
    person = next(node for node in json.loads(get_structured_data())["@graph"] if node["@type"] == "Person")

    # The home page labels the other badges "Past credential".
    assert [credential["url"] for credential in person["hasCredential"]] == [
        badge.url for badge in BADGES if badge.active
    ]


def test_news_edition_metadata_is_noindex_without_structured_data() -> None:
    edition = parse_edition("2026-11-03", "- [Title](https://example.com/a): About a.\n")
    metadata = news_edition_metadata(edition)

    assert metadata.no_index
    assert metadata.structured_data == "", "a noindex edition needs no JSON-LD graph"
    assert (metadata.title, metadata.canonical) == ("News: November 3, 2026 | Fmind", edition.url)
    assert (metadata.feed_path, metadata.feed_title) == (NEWS_FEED_PATH, "Fmind news")
    assert metadata.image_url == news_index_metadata().image_url
    # The indexed /news/ page keeps its graph.
    assert json.loads(news_index_metadata().structured_data)["@graph"][-1]["@type"] == "CollectionPage"


@pytest.mark.parametrize(
    ("metadata", "page_type", "has_breadcrumb"),
    [
        (article_index_metadata(ArticleIndexView()), "CollectionPage", True),
        (news_index_metadata(), "CollectionPage", True),
        (site_index_metadata(), "CollectionPage", True),
        (connect_metadata(), "ContactPage", True),
        (scan_metadata(), "ContactPage", False),
        (agents_metadata(), "WebPage", True),
        (privacy_metadata(), "WebPage", True),
    ],
)
def test_hosted_pages_describe_themselves_in_json_ld(
    metadata: PageMetadata,
    page_type: str,
    has_breadcrumb: bool,
) -> None:
    graph = json.loads(metadata.structured_data)["@graph"]
    page = graph[-1]
    expected_types = ["Person", "WebSite", *(["BreadcrumbList"] if has_breadcrumb else []), page_type]
    assert [node["@type"] for node in graph] == expected_types
    assert page["url"] == metadata.canonical
    assert page["@id"] == f"{metadata.canonical}#webpage"
    assert page["inLanguage"] == "en"
    assert page["primaryImageOfPage"]["width"] == 1200
    assert page["primaryImageOfPage"]["height"] == 630
    assert page["isPartOf"] == {"@id": f"{METADATA.site_url}/#website"}
    if has_breadcrumb:
        assert page["breadcrumb"] == {"@id": f"{metadata.canonical}#breadcrumb"}
        breadcrumb = graph[-2]
        assert breadcrumb["@id"] == f"{metadata.canonical}#breadcrumb"
        assert breadcrumb["itemListElement"][0]["item"] == f"{METADATA.site_url}/"
        assert breadcrumb["itemListElement"][-1]["item"] == metadata.canonical
    else:
        assert "breadcrumb" not in page
    assert "ProfilePage" not in metadata.structured_data


def test_site_metadata_is_a_web_application_and_disables_smooth_scroll() -> None:
    page = SITE_PAGES[0]
    structured = json.loads(site_structured_data(page))
    metadata = site_page_metadata(page, site_structured_data(page))

    nodes = {node["@id"]: node for node in structured["@graph"]}
    application = nodes[f"{page.url}#application"]
    assert application["@type"] == "WebApplication"
    assert application["url"] == page.url
    assert application["inLanguage"] == "en"
    assert application["audience"] == {"@type": "Audience", "audienceType": page.audience}
    # The tool joins the site graph: a free offer authored by the shared Person entity.
    assert application["author"] == {"@id": f"{METADATA.site_url}/#person"}
    assert application["offers"] == {"@type": "Offer", "price": 0, "priceCurrency": "USD"}
    assert nodes[f"{page.url}#webpage"]["mainEntity"] == {"@id": f"{page.url}#application"}
    assert nodes[f"{page.url}#webpage"]["isPartOf"] == {"@id": f"{METADATA.site_url}/#website"}
    assert nodes[f"{page.url}#webpage"]["breadcrumb"] == {"@id": f"{page.url}#breadcrumb"}
    breadcrumb = nodes[f"{page.url}#breadcrumb"]
    assert [item["item"] for item in breadcrumb["itemListElement"]] == [
        f"{METADATA.site_url}/",
        f"{METADATA.site_url}/sites/",
        page.url,
    ]
    assert f"{METADATA.site_url}/#person" in nodes
    assert metadata.instant_scroll
