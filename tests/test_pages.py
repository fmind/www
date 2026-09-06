"""Page metadata keeps discovery and indexing rules explicit."""

import json

from www.data import METADATA, SITE_PAGES, get_structured_data
from www.models import ArticleIndexView
from www.pages import (
    article_index_metadata,
    home_metadata,
    not_found_metadata,
    site_page_metadata,
    site_structured_data,
)


def test_search_metadata_is_noindex_and_preloads_first_result() -> None:
    from www.content import load_articles

    first = load_articles().all[0]
    metadata = article_index_metadata(ArticleIndexView(query="agents", results=(first,)), get_structured_data())

    assert metadata.no_index
    assert metadata.canonical == f"{METADATA.site_url}/articles/"
    assert metadata.preload_image == first.card_image_path()
    assert metadata.title.startswith("Search: agents")


def test_home_and_not_found_metadata_have_opposite_indexing() -> None:
    structured = get_structured_data()

    assert home_metadata(structured).is_home
    assert not_found_metadata(structured).no_index


def test_site_metadata_is_a_web_application_and_disables_smooth_scroll() -> None:
    page = SITE_PAGES[0]
    structured = json.loads(site_structured_data(page))
    metadata = site_page_metadata(page, site_structured_data(page))

    assert structured["@type"] == "WebApplication"
    assert structured["url"] == page.url
    assert metadata.instant_scroll
