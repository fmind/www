"""CommonMark-aware, source-preserving link rewriting for Markdown responses."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from markdown_it import MarkdownIt
from markdown_it.rules_inline.image import image as image_rule
from markdown_it.rules_inline.link import link as link_rule
from markdown_it.rules_inline.state_inline import StateInline
from markdown_it.token import Token

LinkRewriter = Callable[[str], str]


def _parser() -> MarkdownIt:
    """Return a fresh parser so per-call rule instrumentation is isolated."""
    return MarkdownIt("commonmark")


def _string_attr(token: Token, name: str) -> str:
    """Read the string attributes Markdown-It assigns to link tokens."""
    value = token.attrGet(name)
    return value if isinstance(value, str) else ""


@dataclass(frozen=True, slots=True)
class _Edit:
    start: int
    end: int
    replacement: str


def _reference_suffix(target: str, title: str) -> str:
    suffix = "](" + target
    if title:
        suffix += ' "' + _quote_link_title(title) + '"'
    return suffix + ")"


def _quote_link_title(title: str) -> str:
    """Escape unescaped double quotes while retaining authored backslashes."""
    quoted: list[str] = []
    escaped = False
    for character in title:
        if character == '"' and not escaped:
            quoted.append("\\")
        quoted.append(character)
        escaped = character == "\\" and not escaped
    return "".join(quoted)


def _inline_destination_edit(
    state: StateInline,
    label_end: int,
    target: str,
) -> _Edit | None:
    position = label_end + 2  # skip ](
    while position < state.posMax and (state.src[position].isspace()):
        position += 1
    parsed = state.md.helpers.parseLinkDestination(state.src, position, state.posMax)
    if not parsed.ok:
        return None
    if state.src[position] == "<":
        return _Edit(position + 1, parsed.pos - 1, target)
    return _Edit(position, parsed.pos, target)


class _InlineRewriter:
    """One instrumented inline parser per document, reused for each inline segment.

    Building a parser costs more than parsing a short segment, and articles hold
    thousands of segments that are rewritten at startup. Edits and the current
    segment reset per parse, so segments of one document never share state.
    """

    def __init__(self, rewrite: LinkRewriter) -> None:
        self._rewrite = rewrite
        self._segment = ""
        self._edits: list[_Edit] = []
        self._markdown = _parser()
        self._markdown.inline.ruler.at("link", self._track(link_rule, "[", "link_open", "href"))
        self._markdown.inline.ruler.at("image", self._track(image_rule, "![", "image", "src"))

    def _track(
        self, rule: Callable[[StateInline, bool], bool], marker: str, token_type: str, attribute: str
    ) -> Callable[[StateInline, bool], bool]:
        def tracked(state: StateInline, silent: bool) -> bool:
            segment = self._segment
            old_position = state.pos
            # parseLinkLabel requires `[`: probing arbitrary punctuation spends
            # the parser's nesting budget before later links are reached.
            if not state.src.startswith(marker, old_position):
                return False
            label_end = state.md.helpers.parseLinkLabel(state, old_position + len(marker) - 1, marker == "[")
            token_count = len(state.tokens)
            matched = rule(state, silent)
            # Image alt text is parsed recursively with substring-local offsets.
            if not matched or silent or state.src is not segment:
                return matched
            token = next(
                (candidate for candidate in state.tokens[token_count:] if candidate.type == token_type),
                None,
            )
            if token is None:
                return matched
            source = _string_attr(token, attribute)
            target = self._rewrite(source)
            if target == source:
                return matched
            if label_end >= 0 and label_end + 1 < len(segment) and segment[label_end + 1] == "(":
                edit = _inline_destination_edit(state, label_end, target)
                if edit is not None:
                    self._edits.append(edit)
            else:
                self._edits.append(_Edit(label_end, state.pos, _reference_suffix(target, _string_attr(token, "title"))))
            return matched

        return tracked

    def edits(self, segment: str, env: dict[str, object]) -> list[_Edit]:
        self._segment, self._edits = segment, []
        tokens: list[Token] = []
        self._markdown.inline.parse(segment, self._markdown, env, tokens)
        return self._edits


def rewrite_markdown_links(text: str, rewrite: LinkRewriter) -> str:
    """Rewrite parsed link destinations without changing prose or code source."""
    if not text:
        return text
    env: dict[str, object] = {}
    tokens = _parser().parse(text, env)
    offsets = [0, *(index + 1 for index, character in enumerate(text) if character == "\n"), len(text)]

    inline = _InlineRewriter(rewrite)
    edits: list[_Edit] = []
    for token in tokens:
        if token.type != "inline" or token.map is None:
            continue
        # Inline syntax cannot cross block boundaries. Parsing one larger span
        # lets an unmatched backtick hide real links in a later paragraph.
        start, end = (offsets[line] for line in token.map)
        edits.extend(
            _Edit(start + edit.start, start + edit.end, edit.replacement) for edit in inline.edits(text[start:end], env)
        )

    for edit in sorted(edits, key=lambda item: item.start, reverse=True):
        text = text[: edit.start] + edit.replacement + text[edit.end :]
    return text
