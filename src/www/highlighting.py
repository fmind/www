"""Server-side, class-based syntax highlighting with the Tokyo Night palette."""

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

# Chroma 2.27's generated Tokyo Night stylesheet is part of the frozen page
# bytes. Keeping its ordered rules as data is both smaller and more reviewable
# than emulating a second style inheritance engine on top of Pygments.
_CHROMA_CSS_RULES: Final = (
    ("Background", ".bg", "color: #c0caf5; background-color: #1a1b26;"),
    ("PreWrapper", ".chroma", "color: #c0caf5; background-color: #1a1b26; -webkit-text-size-adjust: none;"),
    ("Error", ".chroma .err", "color: #f7768e"),
    ("LineLink", ".chroma .lnlinks", "outline: none; text-decoration: none; color: inherit"),
    ("LineTableTD", ".chroma .lntd", "vertical-align: top; padding: 0; margin: 0; border: 0;"),
    ("LineTable", ".chroma .lntable", "border-spacing: 0; padding: 0; margin: 0; border: 0;"),
    ("LineHighlight", ".chroma .hl", "background-color: #414868"),
    (
        "LineNumbersTable",
        ".chroma .lnt",
        (
            "white-space: pre; -webkit-user-select: none; user-select: none; margin-right: 0.4em; "
            "padding: 0 0.4em 0 0.4em;color: #a9b1d6"
        ),
    ),
    (
        "LineNumbers",
        ".chroma .ln",
        (
            "white-space: pre; -webkit-user-select: none; user-select: none; margin-right: 0.4em; "
            "padding: 0 0.4em 0 0.4em;color: #a9b1d6"
        ),
    ),
    ("Line", ".chroma .line", "display: flex;"),
    ("Keyword", ".chroma .k", "color: #bb9af7"),
    ("KeywordConstant", ".chroma .kc", "color: #e0af68"),
    ("KeywordDeclaration", ".chroma .kd", "color: #9d7cd8"),
    ("KeywordNamespace", ".chroma .kn", "color: #7dcfff"),
    ("KeywordPseudo", ".chroma .kp", "color: #bb9af7"),
    ("KeywordReserved", ".chroma .kr", "color: #bb9af7"),
    ("KeywordType", ".chroma .kt", "color: #41a6b5"),
    ("NameAttribute", ".chroma .na", "color: #7aa2f7"),
    ("NameClass", ".chroma .nc", "color: #ff9e64"),
    ("NameConstant", ".chroma .no", "color: #ff9e64"),
    ("NameDecorator", ".chroma .nd", "color: #7aa2f7; font-weight: bold"),
    ("NameEntity", ".chroma .ni", "color: #7dcfff"),
    ("NameException", ".chroma .ne", "color: #e0af68"),
    ("NameLabel", ".chroma .nl", "color: #9ece6a"),
    ("NameNamespace", ".chroma .nn", "color: #e0af68"),
    ("NameProperty", ".chroma .py", "color: #e0af68"),
    ("NameTag", ".chroma .nt", "color: #bb9af7"),
    ("NameBuiltin", ".chroma .nb", "color: #9ece6a"),
    ("NameBuiltinPseudo", ".chroma .bp", "color: #9ece6a"),
    ("NameFunction", ".chroma .nf", "color: #7aa2f7"),
    ("NameFunctionMagic", ".chroma .fm", "color: #7aa2f7"),
    ("LiteralString", ".chroma .s", "color: #9ece6a"),
    ("LiteralStringAffix", ".chroma .sa", "color: #9d7cd8"),
    ("LiteralStringBacktick", ".chroma .sb", "color: #9ece6a"),
    ("LiteralStringChar", ".chroma .sc", "color: #9ece6a"),
    ("LiteralStringDelimiter", ".chroma .dl", "color: #7aa2f7"),
    ("LiteralStringDoc", ".chroma .sd", "color: #7c86b4"),
    ("LiteralStringDouble", ".chroma .s2", "color: #9ece6a"),
    ("LiteralStringEscape", ".chroma .se", "color: #7aa2f7"),
    ("LiteralStringHeredoc", ".chroma .sh", "color: #7c86b4"),
    ("LiteralStringInterpol", ".chroma .si", "color: #9ece6a"),
    ("LiteralStringOther", ".chroma .sx", "color: #9ece6a"),
    ("LiteralStringRegex", ".chroma .sr", "color: #7dcfff"),
    ("LiteralStringSingle", ".chroma .s1", "color: #9ece6a"),
    ("LiteralStringSymbol", ".chroma .ss", "color: #9ece6a"),
    ("LiteralNumber", ".chroma .m", "color: #e0af68"),
    ("LiteralNumberBin", ".chroma .mb", "color: #e0af68"),
    ("LiteralNumberFloat", ".chroma .mf", "color: #e0af68"),
    ("LiteralNumberHex", ".chroma .mh", "color: #e0af68"),
    ("LiteralNumberInteger", ".chroma .mi", "color: #e0af68"),
    ("LiteralNumberIntegerLong", ".chroma .il", "color: #e0af68"),
    ("LiteralNumberOct", ".chroma .mo", "color: #e0af68"),
    ("Operator", ".chroma .o", "color: #9ece6a; font-weight: bold"),
    ("OperatorWord", ".chroma .ow", "color: #9ece6a; font-weight: bold"),
    ("OperatorReserved", ".chroma .or", "color: #9ece6a; font-weight: bold"),
    ("Comment", ".chroma .c", "color: #7c86b4"),
    ("CommentHashbang", ".chroma .ch", "color: #7c86b4"),
    ("CommentMultiline", ".chroma .cm", "color: #7c86b4"),
    ("CommentSingle", ".chroma .c1", "color: #7c86b4"),
    ("CommentSpecial", ".chroma .cs", "color: #7c86b4"),
    ("CommentPreproc", ".chroma .cp", "color: #7c86b4"),
    ("CommentPreprocFile", ".chroma .cpf", "color: #7c86b4"),
    ("GenericDeleted", ".chroma .gd", "color: #f7768e"),
    ("GenericEmph", ".chroma .ge", "font-style: italic"),
    ("GenericError", ".chroma .gr", "color: #f7768e"),
    ("GenericHeading", ".chroma .gh", "color: #e0af68; font-weight: bold"),
    ("GenericInserted", ".chroma .gi", "color: #9ece6a; background-color: #15161e"),
    ("GenericStrong", ".chroma .gs", "font-weight: bold"),
    ("GenericSubheading", ".chroma .gu", "color: #e0af68; font-weight: bold"),
    ("GenericTraceback", ".chroma .gt", "color: #f7768e"),
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
