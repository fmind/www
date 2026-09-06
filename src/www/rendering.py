"""Strict package-local Jinja rendering for the six HTML page types."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from html.parser import HTMLParser
from typing import Final, cast

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

from www.assets import ApplicationAssets
from www.data import METADATA, article_filter_url
from www.models import PageMetadata
from www.sites import (
    format_count,
    format_decimal,
    format_number,
    format_usd,
    format_usd2,
    hosting_decision_copy,
    hosting_decision_title,
    task_cost_max,
)


class PageTemplate(StrEnum):
    """Closed page-template vocabulary used by the HTTP application."""

    HOME = "pages/home.html"
    ARTICLES = "pages/articles.html"
    ARTICLE = "pages/article.html"
    SITES = "pages/sites.html"
    LLM_SELF_HOSTING = "pages/llm-self-hosting.html"
    NOT_FOUND = "pages/404.html"


@dataclass(frozen=True, slots=True)
class NavLink:
    """One same-page homepage navigation link."""

    href: str
    label: str


NAV_LINKS: Final = (
    NavLink("/#about", "About"),
    NavLink("/#work-experience", "Work Experience"),
    NavLink("/#certifications", "Certifications"),
    NavLink("/#projects", "Projects"),
    NavLink("/#services", "Services"),
)

_RESERVED_CONTEXT: Final = frozenset(
    {"current_year", "metadata", "nav_links", "nonce", "page", "style_css"},
)
_SCRIPT_END = re.compile(r"</\s*script\b", re.IGNORECASE)
_STYLE_END = re.compile(r"</\s*style\b", re.IGNORECASE)
_UNSAFE_FRAGMENT_ELEMENTS: Final = frozenset({"base", "embed", "iframe", "link", "meta", "object", "script", "style"})
_UNSAFE_URL_PREFIXES: Final = ("data:", "javascript:", "vbscript:")
_URL_ATTRIBUTES: Final = frozenset({"action", "formaction", "href", "poster", "src", "xlink:href"})
_URL_IGNORED_CHARACTERS = re.compile(r"[\x00-\x20\x7f]+")


def _static_url_factory(asset_hashes: Mapping[str, str]) -> Callable[[str], str]:
    # Copy even immutable-looking inputs so a renderer can never observe a
    # later caller mutation or another application's asset load.
    hashes = dict(asset_hashes)

    def static_url(path: str) -> str:
        rooted = path if path.startswith("/") else f"/{path}"
        digest = hashes.get(rooted)
        return f"{rooted}?v={digest}" if digest else rooted

    return static_url


def create_environment(asset_hashes: Mapping[str, str]) -> Environment:
    """Create the locked-down Jinja environment shared by page renders."""
    environment = Environment(
        loader=PackageLoader("www", "templates"),
        autoescape=select_autoescape(
            enabled_extensions=("html",),
            default_for_string=True,
            default=True,
        ),
        undefined=StrictUndefined,
        auto_reload=False,
    )
    template_globals = cast(MutableMapping[str, object], environment.globals)
    template_globals.update(
        {
            "article_filter_url": article_filter_url,
            "format_count": format_count,
            "format_decimal": format_decimal,
            "format_go_float": _format_go_float,
            "format_number": format_number,
            "format_usd": format_usd,
            "format_usd2": format_usd2,
            "hosting_decision_copy": hosting_decision_copy,
            "hosting_decision_title": hosting_decision_title,
            "static_url": _static_url_factory(asset_hashes),
            "task_cost_max": task_cost_max,
        },
    )
    return environment


def _format_go_float(value: float, digits: int) -> str:
    """Match the fixed, ungrouped output of Go's direct ``fmt`` verbs."""
    return f"{value:.{digits}f}"


class Renderer:
    """Render complete pages while keeping every raw-HTML decision explicit."""

    __slots__ = ("_clock", "_environment", "_style_css")

    def __init__(
        self,
        assets: ApplicationAssets,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._environment = create_environment(assets.hashes)
        self._style_css = _trusted_stylesheet(assets.inline_styles)
        self._clock = clock or _utc_now

    def render(
        self,
        template: PageTemplate,
        *,
        page: PageMetadata,
        nonce: str,
        context: Mapping[str, object] | None = None,
    ) -> str:
        """Render one complete document with request and page-specific context."""
        if not nonce:
            msg = "nonce must not be empty"
            raise ValueError(msg)

        page_context = dict(context or {})
        conflicts = _RESERVED_CONTEXT.intersection(page_context)
        if conflicts:
            msg = f"reserved render context: {', '.join(sorted(conflicts))}"
            raise ValueError(msg)
        _trust_html_context(page_context)

        # These strings come from validated startup-owned generators. Every
        # audited raw conversion remains confined to this module.
        trusted_page = replace(page, structured_data=_trusted_json_ld(page.structured_data))
        page_context.update(
            current_year=self._clock().year,
            metadata=METADATA,
            nav_links=NAV_LINKS,
            nonce=nonce,
            page=trusted_page,
            style_css=self._style_css,
        )
        return self._environment.get_template(template.value).render(page_context)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class _TrustedFragmentParser(HTMLParser):
    """Reject active HTML constructs outside the Markdown renderers' contract."""

    def __init__(self, boundary: str) -> None:
        super().__init__(convert_charrefs=True)
        self._boundary = boundary

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._validate_element(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._validate_element(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in _UNSAFE_FRAGMENT_ELEMENTS:
            self._reject("must not contain script or style elements")

    def handle_decl(self, decl: str) -> None:
        del decl
        self._reject("must not contain document declarations")

    def handle_pi(self, data: str) -> None:
        del data
        self._reject("must not contain processing instructions")

    def _validate_element(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in _UNSAFE_FRAGMENT_ELEMENTS:
            self._reject("must not contain script or style elements")
        for name, value in attrs:
            normalized_name = name.casefold()
            if normalized_name.startswith("on") or normalized_name in {"srcdoc", "style"}:
                self._reject(f"contains unsafe attribute {name!r}")
            if value is None:
                continue
            if normalized_name in _URL_ATTRIBUTES and _unsafe_url(value):
                self._reject(f"contains unsafe URL in {name!r}")
            if normalized_name == "srcset" and any(
                _unsafe_url(part.strip().split(" ", 1)[0]) for part in value.split(",")
            ):
                self._reject("contains unsafe URL in 'srcset'")

    def _reject(self, reason: str) -> None:
        msg = f"{self._boundary} {reason}"
        raise ValueError(msg)


def _unsafe_url(value: str) -> bool:
    normalized = _URL_IGNORED_CHARACTERS.sub("", value).casefold()
    return normalized.startswith(_UNSAFE_URL_PREFIXES)


def _trusted_html(value: object, boundary: str) -> Markup:
    if type(value) is not str:
        msg = f"{boundary} must be a string"
        raise TypeError(msg)
    parser = _TrustedFragmentParser(boundary)
    parser.feed(value)
    parser.close()
    return Markup(value)  # noqa: S704


def _trust_html_context(context: MutableMapping[str, object]) -> None:
    article_html = context.get("article_html")
    if article_html is not None:
        context["article_html"] = _trusted_html(article_html, "article_html")

    biography_html = context.get("biography_html")
    if biography_html is None:
        return
    if isinstance(biography_html, (str, bytes)) or not isinstance(biography_html, Sequence):
        msg = "biography_html must be a sequence of strings"
        raise TypeError(msg)
    if any(type(item) is not str for item in biography_html):
        msg = "biography_html items must be strings"
        raise TypeError(msg)
    context["biography_html"] = tuple(_trusted_html(item, "biography_html") for item in biography_html)


def _trusted_stylesheet(value: object) -> Markup:
    if type(value) is not str:
        msg = "stylesheet must be a string"
        raise TypeError(msg)
    if _STYLE_END.search(value):
        msg = "stylesheet must not close its style element"
        raise ValueError(msg)
    return Markup(value)  # noqa: S704


def _trusted_json_ld(value: object) -> Markup:
    if type(value) is not str:
        msg = "structured_data must be a string"
        raise TypeError(msg)
    try:
        json.loads(value)
    except json.JSONDecodeError as error:
        msg = "structured_data must be valid JSON"
        raise ValueError(msg) from error
    if _SCRIPT_END.search(value):
        msg = "structured_data must not close its script element"
        raise ValueError(msg)
    # JSON parsing and the closing-tag guard above make this the reviewed
    # JSON-LD boundary; escaping it would turn JSON quotes into HTML entities.
    return Markup(value)  # noqa: S704
