import re
from hashlib import sha256

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


def test_generated_css_is_byte_identical_to_frozen_chroma() -> None:
    css = highlight_css()

    assert len(css.encode()) == 4226
    assert sha256(css.encode()).hexdigest() == "655ca49a220ca19b913c8a5bcd5ca67c09f89c90fc557b3f2b1e9b13a54820c3"


def test_tokyo_night_contrast_fixes_are_present() -> None:
    css = highlight_css()

    assert re.search(r"\.chroma \.c\s*\{[^}]*#7c86b4", css, re.IGNORECASE)
    assert re.search(r"\.chroma \.err\s*\{[^}]*#f7768e", css, re.IGNORECASE)
