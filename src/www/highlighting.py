"""Server-side, class-based syntax highlighting with the Fmind light palette."""

from html import escape
from typing import Final

from pygments.lexer import Lexer
from pygments.lexers import get_lexer_by_name
from pygments.lexers.special import TextLexer
from pygments.token import STANDARD_TYPES, Operator, _TokenType
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
    ("PreWrapper", ".chroma", "color: #202124; background-color: #ffffff; -webkit-text-size-adjust: none"),
    ("Error", ".chroma .err", "color: #a50e0e; font-weight: bold"),
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


def _lexer(language: str) -> Lexer:
    if not language:
        return TextLexer(stripnl=False, ensurenl=False)
    try:
        return get_lexer_by_name(language, stripnl=False, ensurenl=False)
    except ClassNotFound:
        return TextLexer(stripnl=False, ensurenl=False)


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


def _format_tokens(tokens: list[tuple[_TokenType, str]]) -> str:
    # Focusable so keyboard users can scroll long lines sideways (axe scrollable-region-focusable).
    rendered: list[str] = ['<pre class="chroma" tabindex="0"><code>']
    for line in _split_lines(_coalesce(tokens)):
        rendered.append('<span class="line"><span class="cl">')
        for token_type, value in line:
            escaped = escape(value, quote=False)
            class_name = _token_class(token_type)
            if class_name:
                rendered.append(f'<span class="{class_name}">{escaped}</span>')
            else:
                rendered.append(escaped)
        rendered.append("</span></span>")
    rendered.append("</code></pre>")
    return "".join(rendered)


def highlight_code(code: str, language: str = "") -> str:
    # Unlabeled fences and indented blocks render as plain text; the article skill requires a language.
    lexer = _lexer(language)
    return _format_tokens(list(lexer.get_tokens(code)))


def highlight_css() -> str:
    return _CHROMA_CSS
