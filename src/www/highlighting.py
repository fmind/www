"""Server-side, class-based syntax highlighting with the Fmind light palette."""

from __future__ import annotations

import re
from html import escape
from typing import Final

from pygments.lexer import Lexer
from pygments.lexers import get_lexer_by_name
from pygments.lexers.special import TextLexer
from pygments.token import (
    STANDARD_TYPES,
    Operator,
    Punctuation,
    String,
    Text,
    Whitespace,
    _TokenType,
)
from pygments.util import ClassNotFound

# Pygments and Chroma share most short token names, but Pygments also invents
# names for arbitrary descendants. Chroma instead walks to the nearest type in
# its fixed table, so constrain the adapter to that stable public HTML contract.
_CHROMA_CLASSES: Final = frozenset(
    {
        "bp",
        "c",
        "c1",
        "ch",
        "cm",
        "cp",
        "cpf",
        "cs",
        "err",
        "fm",
        "g",
        "gd",
        "ge",
        "gh",
        "gi",
        "gl",
        "go",
        "gp",
        "gr",
        "gs",
        "gt",
        "gu",
        "il",
        "k",
        "kc",
        "kd",
        "kn",
        "kp",
        "kr",
        "kt",
        "l",
        "ld",
        "m",
        "mb",
        "mf",
        "mh",
        "mi",
        "mo",
        "n",
        "na",
        "nb",
        "nc",
        "nd",
        "ne",
        "nf",
        "ni",
        "nl",
        "nn",
        "no",
        "nt",
        "nv",
        "nx",
        "o",
        "ow",
        "p",
        "py",
        "s",
        "s1",
        "s2",
        "sa",
        "sb",
        "sc",
        "sd",
        "se",
        "sh",
        "si",
        "sr",
        "ss",
        "sx",
        "vc",
        "vg",
        "vi",
        "vm",
        "w",
        "x",
    }
)

# Keep the existing token-class contract with native Fmind styles. Roles follow
# fmind/theme's checks/palette.yaml and themes/ptpython/fmind.py; no sibling checkout
# or second style inheritance engine is needed to build the website.
_CHROMA_CSS_RULES: Final = (
    ("Background", ".bg", "color: #202124; background-color: #ffffff"),
    ("PreWrapper", ".chroma", "color: #202124; background-color: #ffffff; -webkit-text-size-adjust: none"),
    ("Error", ".chroma .err", "color: #a50e0e; font-weight: bold"),
    ("LineLink", ".chroma .lnlinks", "outline: none; text-decoration: none; color: inherit"),
    ("LineTableTD", ".chroma .lntd", "vertical-align: top; padding: 0; margin: 0; border: 0"),
    ("LineTable", ".chroma .lntable", "border-spacing: 0; padding: 0; margin: 0; border: 0"),
    ("LineHighlight", ".chroma .hl", "background-color: #f1f3f4"),
    (
        "LineNumbersTable",
        ".chroma .lnt",
        (
            "white-space: pre; -webkit-user-select: none; user-select: none; margin-right: 0.4em; "
            "padding: 0 0.4em 0 0.4em;color: #595d62"
        ),
    ),
    (
        "LineNumbers",
        ".chroma .ln",
        (
            "white-space: pre; -webkit-user-select: none; user-select: none; margin-right: 0.4em; "
            "padding: 0 0.4em 0 0.4em;color: #595d62"
        ),
    ),
    ("Selection", ".chroma ::selection", "color: inherit; background-color: #d2e3fc"),
    ("GenericOutput", ".chroma .go", "color: #595d62"),
    ("GenericPrompt", ".chroma .gp", "color: #174ea6"),
    ("Line", ".chroma .line", "display: flex"),
    ("Keyword", ".chroma .k", "color: #174ea6; font-weight: bold"),
    ("KeywordConstant", ".chroma .kc", "color: #934900; font-weight: bold"),
    ("KeywordDeclaration", ".chroma .kd", "color: #174ea6; font-weight: bold"),
    ("KeywordNamespace", ".chroma .kn", "color: #174ea6; font-weight: bold"),
    ("KeywordPseudo", ".chroma .kp", "color: #174ea6; font-weight: bold"),
    ("KeywordReserved", ".chroma .kr", "color: #174ea6; font-weight: bold"),
    ("KeywordType", ".chroma .kt", "color: #681da8"),
    ("NameAttribute", ".chroma .na", "color: #202124"),
    ("NameClass", ".chroma .nc", "color: #681da8"),
    ("NameConstant", ".chroma .no", "color: #934900; font-weight: bold"),
    ("NameDecorator", ".chroma .nd", "color: #681da8"),
    ("NameEntity", ".chroma .ni", "color: #202124"),
    ("NameException", ".chroma .ne", "color: #a50e0e; font-weight: bold"),
    ("NameLabel", ".chroma .nl", "color: #202124"),
    ("NameNamespace", ".chroma .nn", "color: #681da8"),
    ("NameProperty", ".chroma .py", "color: #202124"),
    ("NameTag", ".chroma .nt", "color: #174ea6; font-weight: bold"),
    ("NameBuiltin", ".chroma .nb", "color: #681da8"),
    ("NameBuiltinPseudo", ".chroma .bp", "color: #681da8"),
    ("NameFunction", ".chroma .nf", "color: #174ea6"),
    ("NameFunctionMagic", ".chroma .fm", "color: #174ea6"),
    ("LiteralString", ".chroma .s", "color: #0d652d"),
    ("LiteralStringAffix", ".chroma .sa", "color: #0d652d"),
    ("LiteralStringBacktick", ".chroma .sb", "color: #0d652d"),
    ("LiteralStringChar", ".chroma .sc", "color: #0d652d"),
    ("LiteralStringDelimiter", ".chroma .dl", "color: #0d652d"),
    ("LiteralStringDoc", ".chroma .sd", "color: #0d652d"),
    ("LiteralStringDouble", ".chroma .s2", "color: #0d652d"),
    ("LiteralStringEscape", ".chroma .se", "color: #174ea6"),
    ("LiteralStringHeredoc", ".chroma .sh", "color: #0d652d"),
    ("LiteralStringInterpol", ".chroma .si", "color: #174ea6"),
    ("LiteralStringOther", ".chroma .sx", "color: #0d652d"),
    ("LiteralStringRegex", ".chroma .sr", "color: #174ea6"),
    ("LiteralStringSingle", ".chroma .s1", "color: #0d652d"),
    ("LiteralStringSymbol", ".chroma .ss", "color: #0d652d"),
    ("LiteralNumber", ".chroma .m", "color: #934900"),
    ("LiteralNumberBin", ".chroma .mb", "color: #934900"),
    ("LiteralNumberFloat", ".chroma .mf", "color: #934900"),
    ("LiteralNumberHex", ".chroma .mh", "color: #934900"),
    ("LiteralNumberInteger", ".chroma .mi", "color: #934900"),
    ("LiteralNumberIntegerLong", ".chroma .il", "color: #934900"),
    ("LiteralNumberOct", ".chroma .mo", "color: #934900"),
    ("Operator", ".chroma .o", "color: #202124"),
    ("OperatorWord", ".chroma .ow", "color: #174ea6; font-weight: bold"),
    ("OperatorReserved", ".chroma .or", "color: #174ea6; font-weight: bold"),
    ("Comment", ".chroma .c", "color: #595d62"),
    ("CommentHashbang", ".chroma .ch", "color: #595d62"),
    ("CommentMultiline", ".chroma .cm", "color: #595d62"),
    ("CommentSingle", ".chroma .c1", "color: #595d62"),
    ("CommentSpecial", ".chroma .cs", "color: #595d62"),
    ("CommentPreproc", ".chroma .cp", "color: #681da8"),
    ("CommentPreprocFile", ".chroma .cpf", "color: #681da8"),
    ("GenericDeleted", ".chroma .gd", "color: #a50e0e; background-color: #fad2cf"),
    ("GenericEmph", ".chroma .ge", "color: #681da8"),
    ("GenericError", ".chroma .gr", "color: #a50e0e; font-weight: bold"),
    ("GenericHeading", ".chroma .gh", "color: #174ea6"),
    ("GenericInserted", ".chroma .gi", "color: #0d652d; background-color: #ceead6"),
    ("GenericStrong", ".chroma .gs", "font-weight: bold"),
    ("GenericSubheading", ".chroma .gu", "color: #174ea6; font-weight: bold"),
    ("GenericTraceback", ".chroma .gt", "color: #a50e0e"),
    ("GenericUnderline", ".chroma .gl", "text-decoration: underline"),
)
_CHROMA_CSS: Final = "".join(
    f"/* {comment} */ {selector} {{ {declarations} }}" for comment, selector, declarations in _CHROMA_CSS_RULES
)

_YAML_QUOTED_SCALAR = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')


_LANGUAGE_MARKERS = (
    (re.compile(r"^(GET|POST|PUT|PATCH|DELETE|HEAD) /\S*( HTTP/\d|\n[A-Za-z][\w-]*: )", re.MULTILINE), "http"),
    (re.compile(r"^\s*<(!DOCTYPE|html|head|body|script|template|div)\b", re.MULTILINE), "html"),
    (re.compile(r"^FROM \S+", re.MULTILINE), "dockerfile"),
    (re.compile(r'^\s*[{\[][\s\S]*"\s*:'), "json"),
    (re.compile(r"\A(?:#[^\n]*\n)*[a-z][\w.-]*:(\s|$)[\s\S]*^[a-z][\w.-]*:(\s|$)", re.MULTILINE), "yaml"),
    (re.compile(r"^\s*((async )?def \w+\s*\(|class \w+[\s(:]|from \S+ import |import \w+)", re.MULTILINE), "python"),
    (re.compile(r"^\s*@\w[\w.]*(\(|\s*$)", re.MULTILINE), "python"),
    (re.compile(r"\)\s*->\s*[\w\[\]., |]+:[ \t]*$", re.MULTILINE), "python"),
    (re.compile(r"^[ \t]*(for|while|elif|try|except|finally)\b[^\n]*:[ \t]*$", re.MULTILINE), "python"),
    (re.compile(r"^\s*[A-Za-z_]\w* = [A-Za-z_][\w.]*\(", re.MULTILINE), "python"),
    (re.compile(r"^(package \w+|func \w+\()", re.MULTILINE), "go"),
    (re.compile(r"^SELECT\s[\s\S]*\sFROM\s", re.IGNORECASE | re.MULTILINE), "sql"),
    (re.compile(r"^\[[\w.-]+\]$[\s\S]*^[\w.-]+ = ", re.MULTILINE), "toml"),
    (re.compile(r"^[\w.-]+ = [^\n(]+\n[\w.-]+ = [^\n(]+\n[\w.-]+ = ", re.MULTILINE), "toml"),
    (re.compile(r"^\[[a-z-]+[(\]]", re.MULTILINE), "justfile"),
    (re.compile(r'^[-\w]+( \w+="[^"]*")*:[ \t]*$\n[ \t]+\S[\s\S]*\{\{', re.MULTILINE), "justfile"),
    (re.compile(r"^\$ \S", re.MULTILINE), "console"),
    (
        re.compile(
            r"^(pip|uv|docker|kubectl|gcloud|git|curl|mise|npm|npx|poetry|python|make|export|cd|sudo|terraform) \S",
            re.MULTILINE,
        ),
        "bash",
    ),
    (re.compile(r"^[a-z][\w.-]+[^\n]* --[\w-]", re.MULTILINE), "bash"),
    (re.compile(r"^[ \t]*-[ \t]+[a-z][\w.-]*:(\s|$)", re.MULTILINE), "yaml"),
    (re.compile(r"^[a-z][\w.-]*:[ \t]*(#[^\n]*)?$\n[ \t]+\S", re.MULTILINE), "yaml"),
    (re.compile(r"^[\w.-]+==\d", re.MULTILINE), "text"),
    (re.compile(r"\A#{1,6} \S[\s\S]*^(#{1,6} |[ \t]*[-*] |\|)", re.MULTILINE), "markdown"),
    (re.compile(r"\A\|[^\n]*\|[ \t]*\n[ \t]*\|[-: |]+\|"), "markdown"),
    (re.compile(r"^[a-z][\w.-]*:(\s|$)[\s\S]*^[a-z][\w.-]*:(\s|$)", re.MULTILINE), "yaml"),
)


def guess_language(code: str) -> str:
    for marker, language in _LANGUAGE_MARKERS:
        if marker.search(code):
            return language
    return ""


def _lexer(language: str) -> Lexer:
    if not language:
        return TextLexer(stripnl=False, ensurenl=False)
    try:
        return get_lexer_by_name(language, stripnl=False, ensurenl=False)
    except ClassNotFound:
        return TextLexer(stripnl=False, ensurenl=False)


def _yaml_scalar_spans(code: str, tokens: list[tuple[int, _TokenType, str]]) -> tuple[tuple[int, int, _TokenType], ...]:
    spans: list[tuple[int, int, _TokenType]] = []
    token_index = 0
    for match in _YAML_QUOTED_SCALAR.finditer(code):
        while token_index + 1 < len(tokens) and tokens[token_index + 1][0] <= match.start():
            token_index += 1
        _, token_type, _ = tokens[token_index]
        # Chroma treats a complete quoted scalar as one string. Do not turn
        # quote-like text inside an already recognised comment into a string.
        if token_type in String:
            scalar_type = String.Double if match.group().startswith('"') else String.Single
            spans.append((match.start(), match.end(), scalar_type))
    return tuple(spans)


def _split_overrides(
    tokens: list[tuple[int, _TokenType, str]],
    overrides: tuple[tuple[int, int, _TokenType], ...],
) -> list[tuple[int, _TokenType, str]]:
    if not overrides:
        return tokens
    output: list[tuple[int, _TokenType, str]] = []
    override_index = 0
    for position, token_type, value in tokens:
        token_end = position + len(value)
        cursor = position
        while override_index < len(overrides) and overrides[override_index][1] <= cursor:
            override_index += 1
        while override_index < len(overrides) and overrides[override_index][0] < token_end:
            start, end, replacement = overrides[override_index]
            if cursor < start:
                output.append((cursor, token_type, value[cursor - position : start - position]))
                cursor = start
            replacement_end = min(end, token_end)
            output.append((cursor, replacement, value[cursor - position : replacement_end - position]))
            cursor = replacement_end
            if end <= token_end:
                override_index += 1
            else:
                break
        if cursor < token_end:
            output.append((cursor, token_type, value[cursor - position :]))
    return output


def _yaml_compat_tokens(code: str, lexer: Lexer) -> list[tuple[_TokenType, str]]:
    positioned = list(lexer.get_tokens_unprocessed(code))
    positioned = _split_overrides(positioned, _yaml_scalar_spans(code, positioned))
    output: list[tuple[_TokenType, str]] = []
    merge_next_space = False
    for _, token_type, value in positioned:
        if token_type is Punctuation.Indicator and value == "-":
            output.append((Text, value))
            merge_next_space = True
            continue
        if merge_next_space and token_type is Whitespace and value.startswith(" "):
            output.append((Text, " "))
            value = value[1:]
        merge_next_space = False
        if value:
            output.append((token_type, value))
    return output


def _coalesce(tokens: list[tuple[_TokenType, str]]) -> list[tuple[_TokenType, str]]:
    output: list[tuple[_TokenType, str]] = []
    for token_type, value in tokens:
        if not value:
            continue
        if output and output[-1][0] is token_type and len(output[-1][1]) < 8192:
            previous_type, previous_value = output[-1]
            output[-1] = (previous_type, previous_value + value)
        else:
            output.append((token_type, value))
    return output


def _split_lines(tokens: list[tuple[_TokenType, str]]) -> list[list[tuple[_TokenType, str]]]:
    lines: list[list[tuple[_TokenType, str]]] = []
    line: list[tuple[_TokenType, str]] = []
    for token_type, value in tokens:
        while "\n" in value:
            head, value = value.split("\n", maxsplit=1)
            line.append((token_type, head + "\n"))
            lines.append(line)
            line = []
        if value:
            line.append((token_type, value))
    if line:
        lines.append(line)
    return lines


def _token_class(token_type: _TokenType) -> str:
    if token_type is Operator.Reserved:
        return "or"
    current: _TokenType | None = token_type
    while current is not None:
        name = STANDARD_TYPES.get(current, "")
        if name in _CHROMA_CLASSES:
            return name
        current = current.parent
    return ""


def _escape_token(value: str) -> str:
    # Go's html.EscapeString uses numeric entities for quotes; preserve those
    # bytes because highlighted code participates in the frozen page contract.
    return escape(value, quote=True).replace("&#x27;", "&#39;").replace("&quot;", "&#34;")


def _format_tokens(tokens: list[tuple[_TokenType, str]]) -> str:
    rendered: list[str] = ['<pre class="chroma"><code>']
    for line in _split_lines(_coalesce(tokens)):
        rendered.append('<span class="line"><span class="cl">')
        for token_type, value in line:
            escaped = _escape_token(value)
            class_name = _token_class(token_type)
            if class_name:
                rendered.append(f'<span class="{class_name}">{escaped}</span>')
            else:
                rendered.append(escaped)
        rendered.append("</span></span>")
    rendered.append("</code></pre>")
    return "".join(rendered)


def highlight_code(code: str, language: str = "") -> str:
    selected = language or guess_language(code)
    lexer = _lexer(selected)
    tokens = _yaml_compat_tokens(code, lexer) if selected in {"yaml", "yml"} else list(lexer.get_tokens(code))
    return _format_tokens(tokens)


def highlight_css() -> str:
    return _CHROMA_CSS


def plain_code(code: str) -> str:
    """Return CSP-safe plain code for callers that intentionally bypass Pygments."""
    return _format_tokens([(Text, code)])
