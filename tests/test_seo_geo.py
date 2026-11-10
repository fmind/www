"""End-to-end SEO, GEO, structured data, and semantic accessibility contracts."""

import json
import re
from typing import Any

import pytest
from litestar.testing import TestClient

from www.assets import ApplicationAssets
from www.content import ArticleCollection, visible_articles
from www.data import METADATA, SITE_PAGES

type AppClient = TestClient[Any]


def _extract_json_ld(html: str) -> dict[str, Any]:
    matches = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    assert len(matches) == 1
    return json.loads(matches[0])


def _meta_property(html: str, name: str) -> list[str]:
    return re.findall(rf'<meta property="{re.escape(name)}" content="([^"]*)"/>', html)


def _meta_name(html: str, name: str) -> list[str]:
    return re.findall(rf'<meta name="{re.escape(name)}" content="([^"]*)"/>', html)


@pytest.mark.parametrize(
    ("path", "canonical", "feed_path"),
    [
        ("/", f"{METADATA.site_url}/", "/articles/feed.xml"),
        ("/articles/", f"{METADATA.site_url}/articles/", "/articles/feed.xml"),
        ("/news/", f"{METADATA.site_url}/news/", "/news/feed.xml"),
        ("/sites/", f"{METADATA.site_url}/sites/", "/articles/feed.xml"),
        ("/sites/llm-self-hosting/", f"{METADATA.site_url}/sites/llm-self-hosting/", "/articles/feed.xml"),
        (
            "/sites/llm-self-hosting/?requests=500&mode=advanced",
            f"{METADATA.site_url}/sites/llm-self-hosting/",
            "/articles/feed.xml",
        ),
        ("/sites/mcp-context-cost/", f"{METADATA.site_url}/sites/mcp-context-cost/", "/articles/feed.xml"),
        (
            "/sites/mcp-context-cost/?server=github&requests=250",
            f"{METADATA.site_url}/sites/mcp-context-cost/",
            "/articles/feed.xml",
        ),
        ("/agents", f"{METADATA.site_url}/agents", "/articles/feed.xml"),
        ("/connect", f"{METADATA.site_url}/connect", "/articles/feed.xml"),
        ("/privacy", f"{METADATA.site_url}/privacy", "/articles/feed.xml"),
    ],
)
def test_indexed_routes_publish_complete_seo_and_opengraph_metadata(
    client: AppClient,
    path: str,
    canonical: str,
    feed_path: str,
) -> None:
    response = client.get(path)
    assert response.status_code == 200, path
    html = response.text

    assert re.findall(r"<link rel=\"canonical\" href=\"([^\"]+)\"/>", html) == [canonical]
    assert _meta_name(html, "robots") == ["index, follow, max-image-preview:large"]
    assert _meta_property(html, "og:url") == [canonical]
    assert _meta_property(html, "og:image") == [f"{METADATA.site_url}/static/img/og-image.jpg"]
    assert _meta_property(html, "og:image:type") == ["image/jpeg"]
    assert _meta_property(html, "og:image:width") == ["1200"]
    assert _meta_property(html, "og:image:height") == ["630"]
    assert _meta_name(html, "twitter:card") == ["summary_large_image"]
    assert f'<link rel="alternate" type="application/atom+xml" href="{METADATA.site_url}{feed_path}"' in html
    assert '<link rel="alternate" type="application/json" href="/api/profile"' in html
    assert '<link rel="alternate" type="text/plain" href="/llms.txt"' in html
    assert (
        '<link rel="alternate" type="application/mcp-server-card+json" href="/.well-known/mcp/server-card.json"' in html
    )
    if path == "/news/":
        assert '<link rel="alternate" type="application/json" href="/api/news"' in html


def test_noindex_routes_omit_canonical_and_404_omits_misleading_og_url(client: AppClient) -> None:
    for path in ("/scan", "/articles/?q=agents", "/news/2026-11-06/", "/missing-route"):
        response = client.get(path)
        assert response.status_code == (404 if path == "/missing-route" else 200), path
        html = response.text
        assert _meta_name(html, "robots") == ["noindex, follow"], path
        assert '<link rel="canonical"' not in html, path
        if path == "/missing-route":
            assert _meta_property(html, "og:url") == []
            assert "application/ld+json" not in html
        elif path == "/scan":
            assert _meta_property(html, "og:url") == [f"{METADATA.site_url}/scan"]


def test_article_pages_publish_blog_posting_breadcrumbs_and_cover_dimensions(
    client: AppClient,
    snapshots: tuple[ApplicationAssets, ArticleCollection],
) -> None:
    assets, collection = snapshots
    article = visible_articles(collection.all)[0]
    html = client.get(f"/articles/{article.slug}/").text

    cover_route = article.image_url.removeprefix(METADATA.site_url)
    expected_width, expected_height = assets.image_sizes[cover_route]
    assert _meta_property(html, "og:type") == ["article"]
    assert _meta_property(html, "og:url") == [article.url]
    assert _meta_property(html, "og:image") == [article.image_url]
    assert _meta_property(html, "og:image:width") == [str(expected_width)]
    assert _meta_property(html, "og:image:height") == [str(expected_height)]
    assert _meta_property(html, "og:image:type") != []

    graph = _extract_json_ld(html)["@graph"]
    by_type = {node["@type"]: node for node in graph}
    assert set(by_type) == {"Person", "WebSite", "BreadcrumbList", "BlogPosting"}

    posting = by_type["BlogPosting"]
    assert posting["@id"] == f"{article.url}#article"
    assert posting["author"] == {"@id": f"{METADATA.site_url}/#person"}
    assert posting["publisher"] == {"@id": f"{METADATA.site_url}/#person"}
    assert posting["isPartOf"] == {"@id": f"{METADATA.site_url}/#website"}
    assert posting["inLanguage"] == "en"
    assert posting["isAccessibleForFree"] is True
    assert posting["timeRequired"] == f"PT{article.reading_minutes}M"
    assert posting["articleSection"] == list(article.tags)
    assert posting["image"]["width"] == expected_width
    assert posting["image"]["height"] == expected_height

    breadcrumb = by_type["BreadcrumbList"]
    assert [item["item"] for item in breadcrumb["itemListElement"]] == [
        f"{METADATA.site_url}/",
        f"{METADATA.site_url}/articles/",
        article.url,
    ]


def test_decision_tools_connect_web_application_audience_and_breadcrumbs(client: AppClient) -> None:
    for site_page in SITE_PAGES:
        path = site_page.url.removeprefix(METADATA.site_url)
        html = client.get(path).text
        graph = _extract_json_ld(html)["@graph"]
        by_id = {node["@id"]: node for node in graph}

        webpage = by_id[f"{site_page.url}#webpage"]
        application = by_id[f"{site_page.url}#application"]
        breadcrumb = by_id[f"{site_page.url}#breadcrumb"]

        assert webpage["mainEntity"] == {"@id": application["@id"]}
        assert webpage["breadcrumb"] == {"@id": breadcrumb["@id"]}
        assert webpage["primaryImageOfPage"]["width"] == 1200
        assert webpage["primaryImageOfPage"]["height"] == 630
        assert application["author"] == {"@id": f"{METADATA.site_url}/#person"}
        assert application["audience"] == {"@type": "Audience", "audienceType": site_page.audience}
        assert [item["item"] for item in breadcrumb["itemListElement"]] == [
            f"{METADATA.site_url}/",
            f"{METADATA.site_url}/sites/",
            site_page.url,
        ]


def test_every_route_preserves_landmarks_single_h1_and_sticky_anchor_clearance(client: AppClient) -> None:
    routes = (
        "/",
        "/articles/",
        "/articles/?tag=Agent",
        "/articles/the-affordable-ai-agents/",
        "/news/",
        "/news/2026-11-06/",
        "/sites/",
        "/sites/llm-self-hosting/",
        "/sites/mcp-context-cost/",
        "/agents",
        "/connect",
        "/scan",
        "/privacy",
        "/missing-route",
    )
    for route in routes:
        html = client.get(route).text
        assert len(re.findall(r"<h1\b", html)) == 1, route
        assert 'href="#main-content"' in html, route
        assert '<main class="scroll-mt-24 ' in html, route
        assert 'id="main-content"' in html, route
        assert "<header" in html, route
        assert "<footer" in html, route

    agents_html = client.get("/agents").text
    assert "prose-headings:scroll-mt-24" in agents_html
    for anchor in ("mcp", "calculator", "mcp-context", "http", "skill", "data-boundaries"):
        assert f'id="{anchor}"' in agents_html

    article_html = client.get("/articles/the-affordable-ai-agents/").text
    assert "prefers-reduced-motion: reduce" in article_html


def test_article_metadata_resolves_manifest_dimensions_and_tolerates_missing_or_external_media(
    snapshots: tuple[ApplicationAssets, ArticleCollection],
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    from www import pages
    from www.data import get_structured_data
    from www.models import Article
    from www.pages import article_metadata

    sample = snapshots[1].all[0]

    def posting_image(candidate: Article) -> dict[str, Any]:
        enriched = json.loads(article_metadata(candidate, get_structured_data(candidate)).structured_data)
        posting = next(node for node in enriched["@graph"] if node["@type"] == "BlogPosting")
        return posting["image"]

    assert article_metadata(sample, "").structured_data == ""
    assert "width" not in posting_image(replace(sample, image_url="https://cdn.example.com/cover.webp"))
    assert "width" not in posting_image(
        replace(sample, image_url="https://www.fmind.dev/static/img/nonexistent-cover.webp")
    )

    manifest_ok = tmp_path / "manifest-ok.json"
    manifest_ok.write_text(
        json.dumps({"/static/img/synthetic.webp": {"hash": "12345678", "size": 100, "width": 1600, "height": 900}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(pages, "STATIC_MANIFEST", str(manifest_ok))
    synthetic_img = posting_image(replace(sample, image_url="https://www.fmind.dev/static/img/synthetic.webp"))
    assert synthetic_img["width"] == 1600
    assert synthetic_img["height"] == 900

    for bad_name, payload in (("corrupt.json", "{corrupt"), ("list.json", "[]")):
        bad_manifest = tmp_path / bad_name
        bad_manifest.write_text(payload, encoding="utf-8")
        monkeypatch.setattr(pages, "STATIC_MANIFEST", str(bad_manifest))
        assert "width" not in posting_image(
            replace(sample, image_url="https://www.fmind.dev/static/img/synthetic.webp")
        )
