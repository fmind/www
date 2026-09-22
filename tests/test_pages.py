"""Page metadata keeps discovery and indexing rules explicit."""

import json

import pytest

from www.data import METADATA, SITE_PAGES, get_structured_data
from www.models import ArticleIndexView, PageMetadata
from www.pages import (
    agents_metadata,
    article_index_metadata,
    connect_metadata,
    home_metadata,
    not_found_metadata,
    privacy_metadata,
    scan_metadata,
    site_index_metadata,
    site_page_metadata,
    site_structured_data,
)


def test_search_metadata_is_noindex_and_preloads_first_result() -> None:
    from www.content import load_articles

    first = load_articles().all[0]
    metadata = article_index_metadata(ArticleIndexView(query="agents", results=(first,)))

    assert metadata.no_index
    assert metadata.canonical == f"{METADATA.site_url}/articles/"
    assert metadata.preload_image == first.card_image_path()
    assert metadata.title.startswith("Search: agents")


def test_home_and_not_found_metadata_have_opposite_indexing() -> None:
    structured = get_structured_data()

    assert home_metadata(structured).is_home
    assert not_found_metadata().no_index
    assert not_found_metadata().structured_data == "", "a missing page must not claim to be the profile"


@pytest.mark.parametrize(
    ("metadata", "page_type"),
    [
        (article_index_metadata(ArticleIndexView()), "CollectionPage"),
        (site_index_metadata(), "CollectionPage"),
        (connect_metadata(), "ContactPage"),
        (scan_metadata(), "ContactPage"),
        (agents_metadata(), "WebPage"),
        (privacy_metadata(), "WebPage"),
    ],
)
def test_hosted_pages_describe_themselves_in_json_ld(metadata: PageMetadata, page_type: str) -> None:
    graph = json.loads(metadata.structured_data)["@graph"]
    page = graph[-1]
    assert [node["@type"] for node in graph] == ["Person", "WebSite", page_type]
    assert page["url"] == metadata.canonical
    assert page["@id"] == f"{metadata.canonical}#webpage"
    assert page["isPartOf"] == {"@id": f"{METADATA.site_url}/#website"}
    assert "ProfilePage" not in metadata.structured_data


def test_site_metadata_is_a_web_application_and_disables_smooth_scroll() -> None:
    page = SITE_PAGES[0]
    structured = json.loads(site_structured_data(page))
    metadata = site_page_metadata(page, site_structured_data(page))

    assert structured["@type"] == "WebApplication"
    assert structured["url"] == page.url
    assert metadata.instant_scroll
