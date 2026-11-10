"""CommonMark-aware link and image rewriting for Markdown exports."""

from markdown_it import MarkdownIt
from markdown_it.utils import EnvType
from mdit_py_plugins.footnote import footnote_plugin

from www.markdown import _quote_link_title, rewrite_markdown_links


def _rewrite(markdown: str) -> str:
    parser = MarkdownIt("commonmark", {"html": False}).use(footnote_plugin)
    parser.enable("table")
    env: EnvType = {}
    tokens = parser.parse(markdown, env)
    return rewrite_markdown_links(
        markdown,
        lambda url: f"https://www.fmind.dev{url}" if url.startswith("/") and not url.startswith("//") else url,
        tokens,
        env,
    )


def test_empty_and_unchanged_markdown_round_trip_verbatim() -> None:
    assert _rewrite("") == ""
    source = "Plain prose with [external](https://example.com) and `[/code](/ignored)`.\n"
    assert _rewrite(source) == source


def test_inline_angle_bracket_and_reference_links_preserve_surrounding_syntax() -> None:
    source = (
        'Read [angle]( </articles/one/> ) and [plain](/articles/two/ "Title").\n\n'
        "Reference [untitled][ref1] and [titled][ref2] and ![cover [v2]](/static/cover.webp).\n\n"
        "[ref1]: /sites/\n"
        '[ref2]: /privacy "Say \\"hi\\" and \\path"\n'
    )
    rewritten = _rewrite(source)

    assert "[angle]( <https://www.fmind.dev/articles/one/> )" in rewritten
    assert '[plain](https://www.fmind.dev/articles/two/ "Title")' in rewritten
    assert "[untitled](https://www.fmind.dev/sites/)" in rewritten
    assert '[titled](https://www.fmind.dev/privacy "Say \\"hi\\" and \\path")' in rewritten
    assert "![cover [v2]](https://www.fmind.dev/static/cover.webp)" in rewritten


def test_quote_link_title_escapes_only_unescaped_double_quotes() -> None:
    assert _quote_link_title('plain "quoted" \\"already\\" \\\\"after-slash') == (
        'plain \\"quoted\\" \\"already\\" \\\\\\"after-slash'
    )


def test_table_cells_and_unmatched_backticks_stay_isolated_per_block() -> None:
    source = (
        "Paragraph with unmatched `backtick\n\n"
        "Next block [works](/agents) and //cdn.example/keep.\n\n"
        "| A | B |\n"
        "| - | - |\n"
        "| [One](/connect) | [Two](/news/) |\n"
    )
    rewritten = _rewrite(source)

    assert "[works](https://www.fmind.dev/agents)" in rewritten
    assert "| [One](https://www.fmind.dev/connect) | [Two](https://www.fmind.dev/news/) |" in rewritten
