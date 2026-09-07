"""Strict Jinja rendering preserves the server-owned trust boundaries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest
from jinja2 import PackageLoader, StrictUndefined, UndefinedError

from www.assets import ApplicationAssets
from www.content import load_articles, visible_articles
from www.data import (
    BADGES,
    BIOGRAPHY,
    EXPERIENCES,
    EXPERTISE,
    LEADERSHIP,
    OPEN_SOURCE,
    SITE_PAGES,
    SPECIALIZATIONS,
    YOUTUBE_SERIES,
    get_services,
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


def application_assets(
    *,
    style_css: str = "body{}",
    hashes: dict[str, str] | None = None,
) -> ApplicationAssets:
    return ApplicationAssets(root_files={}, hashes=hashes or {}, inline_styles=style_css)


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
        "format_go_float",
        "format_number",
        "format_usd",
        "format_usd2",
        "hosting_decision_copy",
        "hosting_decision_title",
        "static_url",
        "task_cost_max",
    } <= environment.globals.keys()


def test_go_float_formatting_preserves_direct_template_output() -> None:
    formatter = cast(Callable[[float, int], str], create_environment({}).globals["format_go_float"])

    assert formatter(31.049999999999997, 1) == "31.0"
    assert formatter(2242.5, 0) == "2242"
    assert formatter(34.5, 0) == "34"
    assert formatter(3220.0, 0) == "3220"


def test_renderer_fails_closed_at_markup_and_context_boundaries() -> None:
    structured_data = get_structured_data()
    page = home_metadata(structured_data)

    with pytest.raises(ValueError, match="stylesheet must not close its style element"):
        Renderer(application_assets(style_css="body{}</style><script>alert(1)</script>"))

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
    with pytest.raises(ValueError, match="article_html must not contain script or style elements"):
        renderer.render(
            PageTemplate.ARTICLE,
            page=page,
            nonce="nonce",
            context={"article_html": "<p>safe</p></script><script>alert(1)</script>"},
        )
    with pytest.raises(ValueError, match="biography_html must not contain script or style elements"):
        renderer.render(
            PageTemplate.HOME,
            page=page,
            nonce="nonce",
            context={"biography_html": ("<strong>safe</strong></style>",)},
        )
    with pytest.raises(ValueError, match="nonce must not be empty"):
        renderer.render(PageTemplate.NOT_FOUND, page=not_found_metadata(structured_data), nonce="")
    with pytest.raises(ValueError, match="structured_data must be valid JSON"):
        renderer.render(PageTemplate.NOT_FOUND, page=replace(page, structured_data="{"), nonce="nonce")
    with pytest.raises(ValueError, match="structured_data must not close its script element"):
        renderer.render(
            PageTemplate.NOT_FOUND,
            page=replace(page, structured_data='{"unsafe":"</script>"}'),
            nonce="nonce",
        )
    with pytest.raises(ValueError, match="reserved render context"):
        renderer.render(PageTemplate.NOT_FOUND, page=page, nonce="nonce", context={"metadata": object()})
    with pytest.raises(UndefinedError):
        renderer.render(PageTemplate.HOME, page=page, nonce="nonce")


@pytest.mark.parametrize(
    ("article_html", "message"),
    [
        ("<SCRIPT>alert(1)</SCRIPT>", "script or style elements"),
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
            page=not_found_metadata(get_structured_data()),
            nonce="nonce",
            context={"article_html": article_html},
        )


def test_renderer_escapes_page_metadata_and_preserves_reviewed_markup() -> None:
    renderer = Renderer(application_assets(style_css="body>main{display:block}"))
    page = replace(not_found_metadata(get_structured_data()), title="<unsafe>")

    rendered = renderer.render(PageTemplate.NOT_FOUND, page=page, nonce="request-nonce")

    assert "<title>&lt;unsafe&gt;</title>" in rendered
    assert '<style nonce="request-nonce">body>main{display:block}</style>' in rendered
    assert '<script type="application/ld+json">{"@context":' in rendered


def test_renderer_keeps_asset_snapshots_isolated_and_refreshes_the_footer_year() -> None:
    years = iter((datetime(2026, 12, 31, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC)))
    first = Renderer(
        application_assets(hashes={"/static/img/favicons/favicon-32x32.png": "first"}),
        clock=lambda: next(years),
    )
    second = Renderer(application_assets(hashes={"/static/img/favicons/favicon-32x32.png": "second"}))
    page = not_found_metadata(get_structured_data())

    first_render = first.render(PageTemplate.NOT_FOUND, page=page, nonce="nonce")
    second_render = second.render(PageTemplate.NOT_FOUND, page=page, nonce="nonce")
    rollover_render = first.render(PageTemplate.NOT_FOUND, page=page, nonce="nonce")

    assert "favicon-32x32.png?v=first" in first_render
    assert "favicon-32x32.png?v=second" in second_render
    assert "favicon-32x32.png?v=first" in rollover_render
    assert "© 2026" in first_render
    assert "© 2027" in rollover_render


def test_renderer_renders_all_six_pages_with_real_domain_contexts() -> None:
    renderer = Renderer(application_assets())
    articles = visible_articles(load_articles().all)
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
                "articles": articles,
                "biography_html": tuple(markdown_to_html(paragraph) for paragraph in BIOGRAPHY),
                "expertise": EXPERTISE,
                "experiences": EXPERIENCES,
                "leadership": LEADERSHIP,
                "badges": BADGES,
                "specializations": SPECIALIZATIONS,
                "open_source": OPEN_SOURCE,
                "youtube_series": YOUTUBE_SERIES,
                "services": get_services(),
            },
        ),
        PageTemplate.ARTICLES: renderer.render(
            PageTemplate.ARTICLES,
            page=article_index_metadata(index, shared_structured_data),
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
            page=site_index_metadata(shared_structured_data),
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
            page=not_found_metadata(shared_structured_data),
            nonce=nonce,
        ),
    }

    markers = {
        PageTemplate.HOME: '<section class="py-16 md:py-24 bg-base-100 overflow-hidden px-4" id="about">',
        PageTemplate.ARTICLES: '<h1 class="text-4xl md:text-6xl font-heading font-black text-balance">Articles</h1>',
        PageTemplate.ARTICLE: f'<h1 class="font-heading text-4xl md:text-6xl font-black leading-tight text-balance mt-6">{article.title}</h1>',
        PageTemplate.SITES: '<h1 class="text-4xl md:text-6xl font-heading font-black text-balance">Sites</h1>',
        PageTemplate.LLM_SELF_HOSTING: "When does self-hosting an LLM pay off?",
        PageTemplate.NOT_FOUND: '<h1 class="text-9xl font-black text-primary font-heading animate-bounce">404</h1>',
    }
    for template, html in rendered.items():
        assert html.startswith("<!DOCTYPE html>")
        assert html.count(f'nonce="{nonce}"') == 3
        assert "{{" not in html
        assert markers[template] in html


def test_startup_markup_is_validated_once_but_unknown_markup_remains_guarded(monkeypatch: pytest.MonkeyPatch) -> None:
    from www import rendering

    page = not_found_metadata(get_structured_data())
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
        assert 'nonce="first"' in first
        assert 'nonce="second"' in second

    with pytest.raises(ValueError, match="unsafe attribute"):
        renderer.render(
            PageTemplate.NOT_FOUND,
            page=page,
            nonce="third",
            context={"article_html": '<p onclick="bad()">unregistered</p>'},
        )
    with pytest.raises(ValueError, match="script or style"):
        Renderer(application_assets(), article_html=("<script>bad()</script>",))
