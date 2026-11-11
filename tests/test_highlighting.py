import re

import pytest
from pygments.token import STANDARD_TYPES

from www.highlighting import highlight_code, highlight_css


def test_unlabeled_code_renders_as_plain_escaped_text() -> None:
    markup = highlight_code("import abc\nx = '<b>'\n")

    assert '<span class="k' not in markup
    assert "&lt;b&gt;" in markup


def test_highlighted_markup_is_class_based_and_css_is_minified() -> None:
    markup = highlight_code('def hello() -> str:\n    return "world"\n', "python")
    css = highlight_css()

    assert markup.startswith('<pre class="chroma" tabindex="0"><code>')
    assert '<span class="k">def</span>' in markup
    assert "style=" not in markup
    assert ".chroma .k" in css
    assert "\n" not in css


def test_only_tokens_with_their_own_style_get_a_span() -> None:
    # Names, operators, punctuation, and whitespace keep the block's base color, so they need no element.
    assert highlight_code("total = count + 1\n", "python") == (
        '<pre class="chroma" tabindex="0"><code><span class="line"><span class="cl">'
        'total = count + <span class="mi">1</span>\n</span></span></code></pre>'
    )


def test_every_token_rule_is_reachable_and_differs_from_the_base_style() -> None:
    css = highlight_css()
    base = re.search(r"\.chroma \{ (color: #[0-9a-f]{6});", css)
    rules = dict(re.findall(r"\.chroma \.([a-z0-9]+) \{ ([^}]*) \}", css))

    assert base
    assert rules.pop("line") == "display: flex"
    # A class Pygments never emits is a dead rule; one restating the base color only adds markup.
    assert set(rules) <= set(STANDARD_TYPES.values())
    assert base[1] not in rules.values()


def test_yaml_keys_and_quoted_scalars_are_colored_and_text_is_escaped() -> None:
    markup = highlight_code("rules:\n  - require: 'aud == \"<my-service>\" && ok'\n", "yaml")

    assert '<span class="nt">rules</span>' in markup
    assert '<span class="nt">require</span>' in markup
    # Quotes in element text need no entities; markup-significant characters do.
    assert '<span class="s">\'aud</span>' in markup
    assert '<span class="s">"&lt;my-service&gt;"</span>' in markup
    assert "&amp;&amp;" in markup


def _luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))


@pytest.mark.parametrize("surface", ["#ffffff", "#f1f3f4", "#d2e3fc", "#ceead6", "#fad2cf", "#feefc3"])
def test_fmind_syntax_is_readable_on_plain_highlighted_selected_and_diff_surfaces(surface: str) -> None:
    foregrounds = set(re.findall(r"(?<!-)color: (#[0-9a-f]{6})", highlight_css()))
    assert foregrounds
    for foreground in foregrounds:
        light, dark = sorted((_luminance(foreground), _luminance(surface)), reverse=True)
        assert (light + 0.05) / (dark + 0.05) >= 4.5, (foreground, surface)


def test_fmind_roles_reach_real_python_tokens() -> None:
    markup = highlight_code(
        'class Example:\n    # A comment\n    def run(self):\n        return print("hello", 42)\n', "python"
    )
    css = highlight_css()
    for token, color in {
        "k": "#174ea6",
        "nf": "#174ea6",
        "nc": "#681da8",
        "nb": "#681da8",
        "s2": "#0d652d",
        "mi": "#934900",
        "c1": "#595d62",
    }.items():
        assert f'class="{token}"' in markup
        assert re.search(r"\.chroma \." + token + r"\s*\{[^}]*color: " + color, css)
    assert ".chroma { color: #202124; background-color: #f1f3f4;" in css
    assert ".chroma ::selection { color: inherit; background-color: #d2e3fc" in css
    assert '<span class="na">href</span>' in highlight_code('<a href="x">y</a>\n', "html")
    assert re.search(r"\.chroma \.na\s*\{[^}]*color: #681da8", css)
