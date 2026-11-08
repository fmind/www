"""Strict Jinja rendering preserves the server-owned trust boundaries."""

import json
import re
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from urllib.parse import urlsplit

import pytest
from jinja2 import PackageLoader, StrictUndefined, UndefinedError
from litestar import Litestar
from litestar.testing import TestClient

from www import content, rendering
from www.assets import ApplicationAssets
from www.content import ArticleCollection, visible_articles
from www.data import (
    BADGES,
    BIOGRAPHY,
    EXPERIENCES,
    EXPERTISE,
    LEADERSHIP,
    OPEN_SOURCE,
    SERVICES,
    SITE_PAGES,
    SPECIALIZATIONS,
    YOUTUBE_SERIES,
    get_structured_data,
    markdown_to_html,
)
from www.pages import (
    article_index_metadata,
    article_metadata,
    home_metadata,
    not_found_metadata,
    site_index_metadata,
    site_page_metadata,
    site_structured_data,
)
from www.publications import article_index_data, related_articles
from www.rendering import PageTemplate, Renderer, create_environment
from www.search import SearchIndex
from www.sites.calculator import build_llm_self_hosting_view
from www.sites.formatting import format_decimal


def application_assets(
    *,
    stylesheet: str = "body{}",
    hashes: dict[str, str] | None = None,
) -> ApplicationAssets:
    return ApplicationAssets(root_files={}, hashes=hashes or {}, stylesheet=stylesheet)


def test_environment_is_package_local_strict_and_autoescaped() -> None:
    environment = create_environment({})

    assert isinstance(environment.loader, PackageLoader)
    assert environment.undefined is StrictUndefined
    assert callable(environment.autoescape)
    assert environment.autoescape("pages/home.html")
    assert environment.autoescape(None)
    assert {
        "article_filter_url",
        "format_count",
        "format_decimal",
        "format_input",
        "format_ungrouped",
        "format_number",
        "format_usd",
        "format_usd2",
        "hosting_decision_copy",
        "hosting_decision_title",
        "static_url",
        "task_cost_max",
    } <= environment.globals.keys()


def test_input_echo_keeps_visitor_decimals() -> None:
    formatter = cast(Callable[[float], str], create_environment({}).globals["format_input"])

    # Assumption copy repeats what the visitor typed; whole-number rounding turned 0.1 into 0.
    assert [formatter(value) for value in (12.5, 0.1, 80.0, 1500.0, 33.333)] == ["12.5", "0.1", "80", "1,500", "33.33"]


def test_ungrouped_formatting_rounds_like_format_decimal() -> None:
    formatter = cast(Callable[[float, int], str], create_environment({}).globals["format_ungrouped"])

    # One metric must read the same in every card, so both helpers round half away from zero.
    for value, digits in ((12.25, 1), (2242.5, 0), (34.5, 0), (31.049999999999997, 1), (0.125, 2)):
        assert formatter(value, digits) == format_decimal(value, digits).replace(",", "")
    assert formatter(12.25, 1) == "12.3"
    assert formatter(2242.5, 0) == "2243"
    # Float noise for 31.05 rounds up in both helpers rather than to Python's half-even 31.0.
    assert formatter(31.049999999999997, 1) == "31.1"
    # SVG widths and form values need plain numbers, never thousands separators.
    assert formatter(1234567.891, 2) == "1234567.89"


def test_renderer_fails_closed_at_markup_and_context_boundaries() -> None:
    structured_data = get_structured_data()
    page = home_metadata(structured_data)

    renderer = Renderer(application_assets())
    with pytest.raises(TypeError, match="article_html must be a string"):
        renderer.render(
            PageTemplate.ARTICLE,
            page=page,
            nonce="nonce",
            context={"article_html": b"<p>not text</p>"},
        )
    with pytest.raises(TypeError, match="biography_html items must be strings"):
        renderer.render(
            PageTemplate.HOME,
            page=page,
            nonce="nonce",
            context={"biography_html": ("<strong>safe</strong>", b"unsafe")},
        )
    with pytest.raises(ValueError, match="article_html must not contain <script> elements"):
        renderer.render(
            PageTemplate.ARTICLE,
            page=page,
            nonce="nonce",
            context={"article_html": "<p>safe</p></script><script>alert(1)</script>"},
        )
    with pytest.raises(ValueError, match="biography_html must not contain <style> elements"):
        renderer.render(
            PageTemplate.HOME,
            page=page,
            nonce="nonce",
            context={"biography_html": ("<strong>safe</strong></style>",)},
        )
    with pytest.raises(ValueError, match="nonce must not be empty"):
        renderer.render(PageTemplate.NOT_FOUND, page=not_found_metadata(), nonce="")
    with pytest.raises(ValueError, match="structured_data must be valid JSON"):
        renderer.render(PageTemplate.NOT_FOUND, page=replace(page, structured_data="{"), nonce="nonce")
    with pytest.raises(ValueError, match="reserved render context"):
        renderer.render(PageTemplate.NOT_FOUND, page=page, nonce="nonce", context={"metadata": object()})
    with pytest.raises(UndefinedError):
        renderer.render(PageTemplate.HOME, page=page, nonce="nonce")


@pytest.mark.parametrize(
    ("article_html", "message"),
    [
        ("<SCRIPT>alert(1)</SCRIPT>", "must not contain <script> elements"),
        ('<iframe src="/x"></iframe>', "must not contain <iframe> elements"),
        ('<link rel="stylesheet" href="/x.css">', "must not contain <link> elements"),
        ('<svg><a><set attributeName="href" to="javascript:alert(1)"/></a></svg>', "must not contain <set> elements"),
        (
            '<svg><animate attributeName="href" values="javascript:alert(1)"/></svg>',
            "must not contain <animate> elements",
        ),
        ('<img src="/safe.png" onerror="alert(1)">', "unsafe attribute"),
        ('<a href="java&#x0a;script:alert(1)">unsafe</a>', "unsafe URL"),
        ('<img srcset="/safe.png 1x, data:text/html,unsafe 2x">', "unsafe URL"),
        ("<!doctype html><p>unsafe</p>", "document declarations"),
        ("<?xml version='1.0'?><p>unsafe</p>", "processing instructions"),
    ],
)
def test_renderer_rejects_active_content_in_validated_html(article_html: str, message: str) -> None:
    renderer = Renderer(application_assets())

    with pytest.raises(ValueError, match=message):
        renderer.render(
            PageTemplate.ARTICLE,
            page=not_found_metadata(),
            nonce="nonce",
            context={"article_html": article_html},
        )


def test_renderer_escapes_page_metadata_and_preserves_reviewed_markup() -> None:
    assets = application_assets(stylesheet="body>main{display:block}")
    renderer = Renderer(assets)
    page = replace(not_found_metadata(), title="<unsafe>", structured_data=get_structured_data())

    rendered = renderer.render(PageTemplate.NOT_FOUND, page=page, nonce="request-nonce")

    assert "<title>&lt;unsafe&gt;</title>" in rendered
    assert f'<link rel="stylesheet" href="/styles.css?v={assets.stylesheet_digest}"/>' in rendered
    assert "<style" not in rendered
    assert '<script type="application/ld+json">{"@context":' in rendered


@pytest.mark.parametrize("text", ["</script><script>alert(1)</script>", "<!--<script>", "</SCRIPT >"])
def test_json_ld_strings_cannot_end_or_swallow_their_script_element(text: str) -> None:
    structured_data = json.dumps({"headline": text})
    page = replace(not_found_metadata(), structured_data=structured_data)

    rendered = Renderer(application_assets()).render(PageTemplate.NOT_FOUND, page=page, nonce="nonce")

    start = rendered.index('<script type="application/ld+json">') + len('<script type="application/ld+json">')
    end = rendered.index("</script>", start)
    element = rendered[start:end]
    # The element holds no "<" at all, decodes to the same data, and the page body survives it.
    assert "<" not in element
    assert json.loads(element) == {"headline": text}
    assert 'id="main-content"' in rendered[end:]


def test_pages_without_structured_data_omit_the_json_ld_element() -> None:
    rendered = Renderer(application_assets()).render(PageTemplate.NOT_FOUND, page=not_found_metadata(), nonce="n")

    assert "application/ld+json" not in rendered


def test_renderer_keeps_asset_snapshots_isolated_and_refreshes_the_footer_year() -> None:
    years = iter((datetime(2026, 12, 31, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC)))
    first = Renderer(
        application_assets(hashes={"/static/img/favicons/favicon-32x32.png": "first"}),
        clock=lambda: next(years),
    )
    second = Renderer(application_assets(hashes={"/static/img/favicons/favicon-32x32.png": "second"}))
    page = not_found_metadata()

    first_render = first.render(PageTemplate.NOT_FOUND, page=page, nonce="nonce")
    second_render = second.render(PageTemplate.NOT_FOUND, page=page, nonce="nonce")
    rollover_render = first.render(PageTemplate.NOT_FOUND, page=page, nonce="nonce")

    assert "favicon-32x32.png?v=first" in first_render
    assert "favicon-32x32.png?v=second" in second_render
    assert "favicon-32x32.png?v=first" in rollover_render
    assert "© 2026" in first_render
    assert "© 2027" in rollover_render


def test_renderer_renders_all_six_pages_with_real_domain_contexts(
    snapshots: tuple[ApplicationAssets, ArticleCollection],
) -> None:
    renderer = Renderer(application_assets())
    articles = visible_articles(snapshots[1].all)
    article = articles[0]
    index = article_index_data(articles, SearchIndex(articles), "", "")
    site_page = SITE_PAGES[0]
    shared_structured_data = get_structured_data()
    nonce = "request-nonce"

    rendered = {
        PageTemplate.HOME: renderer.render(
            PageTemplate.HOME,
            page=home_metadata(shared_structured_data),
            nonce=nonce,
            context={
                "biography_html": tuple(markdown_to_html(paragraph) for paragraph in BIOGRAPHY),
                "expertise": EXPERTISE,
                "experiences": EXPERIENCES,
                "leadership": LEADERSHIP,
                "badges": BADGES,
                "specializations": SPECIALIZATIONS,
                "open_source": OPEN_SOURCE,
                "youtube_series": YOUTUBE_SERIES,
                "services": SERVICES,
            },
        ),
        PageTemplate.ARTICLES: renderer.render(
            PageTemplate.ARTICLES,
            page=article_index_metadata(index),
            nonce=nonce,
            context={"view": index},
        ),
        PageTemplate.ARTICLE: renderer.render(
            PageTemplate.ARTICLE,
            page=article_metadata(article, get_structured_data(article)),
            nonce=nonce,
            context={
                "article": article,
                "article_html": article.html,
                "related_articles": related_articles(article, articles),
                "related_site_pages": tuple(page for page in SITE_PAGES if article.slug in page.article_slugs),
            },
        ),
        PageTemplate.SITES: renderer.render(
            PageTemplate.SITES,
            page=site_index_metadata(),
            nonce=nonce,
            context={"site_pages": SITE_PAGES},
        ),
        PageTemplate.LLM_SELF_HOSTING: renderer.render(
            PageTemplate.LLM_SELF_HOSTING,
            page=site_page_metadata(site_page, site_structured_data(site_page)),
            nonce=nonce,
            context={
                "view": build_llm_self_hosting_view(),
                "related_articles": tuple(item for item in articles if item.slug in site_page.article_slugs),
            },
        ),
        PageTemplate.NOT_FOUND: renderer.render(
            PageTemplate.NOT_FOUND,
            page=not_found_metadata(),
            nonce=nonce,
        ),
    }

    markers = {
        PageTemplate.HOME: '<section class="py-16 md:py-24 bg-base-100 overflow-hidden px-4" id="about" tabindex="-1">',
        PageTemplate.ARTICLES: '<h1 class="text-4xl md:text-6xl font-heading font-bold text-balance">Articles</h1>',
        PageTemplate.ARTICLE: f'<h1 class="font-heading text-4xl md:text-6xl font-bold leading-tight text-balance mt-6">{article.title}</h1>',
        PageTemplate.SITES: '<h1 class="text-4xl md:text-6xl font-heading font-bold text-balance">Sites</h1>',
        PageTemplate.LLM_SELF_HOSTING: "What would self-hosting cost?",
        PageTemplate.NOT_FOUND: '<h1 class="text-9xl font-bold text-primary font-heading animate-bounce">404</h1>',
    }
    for template, html in rendered.items():
        assert html.startswith("<!DOCTYPE html>")
        # Every page carries the consent controller; three pages add their own interaction script.
        assert html.count(f'<script nonce="{nonce}">') == 1 + int(
            template in {PageTemplate.HOME, PageTemplate.ARTICLE, PageTemplate.LLM_SELF_HOSTING}
        )
        assert html.count('<link rel="stylesheet" href="/styles.css?v=') == 1
        assert "<style" not in html
        assert 'data-theme="light"' in html
        assert '<meta name="color-scheme" content="light"/>' in html
        assert "{{" not in html
        assert markers[template] in html
        # One server card URL everywhere: the well-known path the API catalog advertises.
        assert 'href="/mcp/server-card"' not in html
        assert 'href="/.well-known/mcp/server-card.json">MCP</a>' in html
    # Logos inside a link or card that already names the company or credential are decorative.
    home = rendered[PageTemplate.HOME]
    assert re.search(r'src="/static/img/(?:companies|certifications)/[^"]+" alt=""', home)
    assert not re.search(r'src="/static/img/(?:companies|certifications)/[^"]+" alt="[^"]', home)


def test_startup_markup_is_validated_once_but_unknown_markup_remains_guarded(monkeypatch: pytest.MonkeyPatch) -> None:
    from www import rendering

    page = not_found_metadata()
    renderer = Renderer(
        application_assets(), article_html=("<p>published</p>",), structured_data=(page.structured_data,)
    )

    def unexpected_validation(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("immutable markup was reparsed during a request")

    with monkeypatch.context() as patched:
        patched.setattr("www.rendering._TrustedFragmentParser.feed", unexpected_validation)
        patched.setattr(rendering.json, "loads", unexpected_validation)
        first = renderer.render(
            PageTemplate.NOT_FOUND, page=page, nonce="first", context={"article_html": "<p>published</p>"}
        )
        second = renderer.render(
            PageTemplate.NOT_FOUND, page=page, nonce="second", context={"article_html": "<p>published</p>"}
        )
        # Only the consent controller's nonce differs between renders of the 404 page.
        assert first.startswith("<!DOCTYPE html>")
        assert first.count('nonce="first"') == 1
        assert first.replace('nonce="first"', 'nonce="second"') == second

    with pytest.raises(ValueError, match="unsafe attribute"):
        renderer.render(
            PageTemplate.NOT_FOUND,
            page=page,
            nonce="third",
            context={"article_html": '<p onclick="bad()">unregistered</p>'},
        )
    with pytest.raises(ValueError, match="must not contain <script> elements"):
        Renderer(application_assets(), article_html=("<script>bad()</script>",))


@pytest.mark.parametrize("count", [0, 1, 2])
def test_article_section_navigation_requires_two_sections(
    count: int, snapshots: tuple[ApplicationAssets, ArticleCollection]
) -> None:
    article = next(item for item in visible_articles(snapshots[1].all) if len(item.sections) >= 2)
    article = replace(article, sections=article.sections[:count])
    renderer = Renderer(application_assets(), article_html=(article.html,))
    rendered = renderer.render(
        PageTemplate.ARTICLE,
        page=article_metadata(article, get_structured_data(article)),
        nonce="test-nonce",
        context={
            "article": article,
            "article_html": article.html,
            "related_articles": (),
            "related_site_pages": (),
        },
    )
    assert ('aria-label="On this page"' in rendered) is (count >= 2)


@pytest.fixture(scope="module")
def crawled_pages(make_app: Callable[[], Litestar]) -> tuple[dict[str, str], set[str]]:
    """Render every public HTML page once through the app, recording each static_url argument."""
    requested: set[str] = set()
    factory = rendering._static_url_factory  # noqa: SLF001

    def recording_factory(hashes: dict[str, str]) -> Callable[[str], str]:
        static_url = factory(hashes)

        def record(path: str) -> str:
            requested.add(path)
            return static_url(path)

        return record

    pages: dict[str, str] = {}
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(rendering, "_static_url_factory", recording_factory)
        with TestClient(make_app()) as client:
            sitemap = client.get("/sitemap.xml").text
            paths = [urlsplit(location).path for location in re.findall(r"<loc>([^<]+)</loc>", sitemap)]
            for path in [*paths, "/scan", "/missing-page"]:
                response = client.get(path)
                assert response.status_code == (404 if path == "/missing-page" else 200), path
                pages[path] = response.text
    return pages, requested


def test_every_static_url_names_a_hashed_asset(
    crawled_pages: tuple[dict[str, str], set[str]],
    snapshots: tuple[ApplicationAssets, ArticleCollection],
) -> None:
    pages, requested = crawled_pages
    hashes = snapshots[0].hashes

    # static_url falls back to an unversioned URL, so a typo or a deleted asset would ship a 404.
    assert len(pages) > 60
    assert requested
    assert sorted(path for path in requested if "/" + path.lstrip("/") not in hashes) == []


def test_every_page_keeps_ids_unique_and_article_template_ids_reserved(
    crawled_pages: tuple[dict[str, str], set[str]],
    snapshots: tuple[ApplicationAssets, ArticleCollection],
) -> None:
    pages, _ = crawled_pages
    articles = snapshots[1].by_slug

    for path, html in pages.items():
        identifiers = re.findall(r'\bid="([^"]+)"', html)
        assert len(identifiers) == len(set(identifiers)), path
        if path.startswith("/articles/") and path != "/articles/":
            article = articles[path.removeprefix("/articles/").strip("/")]
            assert article.html in html
            # Body headings de-duplicate against these ids, so the list must cover every template id.
            template_ids = set(re.findall(r'\bid="([^"]+)"', html.replace(article.html, "")))
            assert template_ids <= content._TEMPLATE_IDS, path  # noqa: SLF001
