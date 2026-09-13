import re

import pytest

from www.highlighting import guess_language, highlight_code, highlight_css


def test_guess_language_for_archive_shapes() -> None:
    cases = {
        "import abc\n\ndef split(data):\n    return data\n": "python",
        "agent_class: LlmAgent\nmodel: gemini-2.5-flash\ninstruction: |\n  import this\n": "yaml",
        "POST /mcp HTTP/1.1\nContent-Type: application/json\n": "http",
        '{\n  "jsonrpc": "2.0"\n}\n': "json",
        "pip install bromate\nuv run bromate --help\n": "bash",
        "$ mise run test\nDONE\n": "console",
        "FROM python:3.14\nRUN uv sync\n": "dockerfile",
        '@app.post("/")\nasync def index() -> dict:\n    return {}\n': "python",
        "adk web --a2a --port 8001\n": "bash",
        ".agents/docs/\n├── INDEX.md\n└── cloud-run/\n": "",
    }

    for code, language in cases.items():
        assert guess_language(code) == language


def test_highlighted_markup_is_class_based_and_css_is_minified() -> None:
    markup = highlight_code('def hello() -> str:\n    return "world"\n', "python")
    css = highlight_css()

    assert markup.startswith('<pre class="chroma"><code>')
    assert '<span class="k">def</span>' in markup
    assert "style=" not in markup
    assert ".chroma .k" in css
    assert "\n" not in css


def test_agentgateway_yaml_matches_frozen_chroma_markup() -> None:
    code = "authorization:\n  rules:\n    - require: 'jwt.aud == \"my-service\"'\n"

    assert highlight_code(code, "yaml") == (
        '<pre class="chroma"><code>'
        '<span class="line"><span class="cl"><span class="nt">authorization</span>'
        '<span class="p">:</span><span class="w">\n</span></span></span>'
        '<span class="line"><span class="cl"><span class="w">  </span>'
        '<span class="nt">rules</span><span class="p">:</span><span class="w">\n</span></span></span>'
        '<span class="line"><span class="cl"><span class="w">    </span>- '
        '<span class="nt">require</span><span class="p">:</span><span class="w"> </span>'
        '<span class="s1">&#39;jwt.aud == &#34;my-service&#34;&#39;</span>'
        '<span class="w">\n</span></span></span></code></pre>'
    )


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
    assert ".chroma { color: #202124; background-color: #ffffff;" in css
    assert ".chroma ::selection { color: inherit; background-color: #d2e3fc" in css
