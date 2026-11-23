"""The prose component: author-written markdown with artifact-backed
variables.

``core.markdown`` renders one block of report prose — methodology,
conclusions, a narrative around the numbers.  The words are the
report author's, in a strict subset of markdown; the values inside
``{{ }}`` resolve from one JSON artifact the pipeline wrote.

The component's laws:

* *Values are text, never markup.*  The template parses first;
  variables substitute inside the already-tokenized text, code, and
  fence content, html-escaped as they land — a value carrying
  ``*stars*`` or ``<tags>`` renders as the characters it is.  No
  re-parse exists, so no value can inject presentation.
* *The subset is fenced by teaching, not silence.*  The engine is
  markdown-it-py (raw HTML tokenized so it can be refused by token
  type; tables tokenized so they teach rather than rendering as
  pipe-text); the walk emits an allowlist of token types and every
  other construct teaches with the move — tables belong to
  ``core.table``, figures to figure components, links and raw HTML
  are not part of the prose vocabulary.
* *Scalar values render; structure teaches.*  Strings, numbers, and
  booleans (as JSON literals) substitute; a variable resolving to
  null, a list, or an object names the variable and its kind.
* *Honest data, as everywhere.*  A missing artifact is an
  ``unavailable`` notice carrying the store's message; a variable
  the declared artifact does not carry is a broken contract and
  teaches; the parameter vocabulary is closed
  (:func:`_parse_spec`).

Headings demote one level — ``##`` renders ``<h3>`` — because the
card's own title is the section's heading: ``#`` teaches, and prose
headings run ``'##'`` through ``'####'``.
"""

import html
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.deflist import deflist_plugin

from ..artifact_store import JsonValue
from ..components import (
    ComponentParameters,
    PlacementInfo,
    RenderedComponent,
    reject_unknown_parameters,
)
from ..context import RenderContext
from ..errors import ArtifactUnavailableError
from ..manifest.artifact import ArtifactFormat
from .markdown_variables import MARKDOWN_VARIABLE_RE
from .parameters import _optional_text, _required_text

_MD: Final[MarkdownIt] = MarkdownIt("js-default", {"html": True}).use(deflist_plugin)
"""The prose engine: markdown-it-py with raw HTML tokenized (so the
walk refuses it by token type, never by pattern-matching text), the
table rule on (so a table teaches instead of silently rendering as
pipe-text), and the deflist plugin on (so a term-and-description
block renders as the definition list it is — reference prose about
data, not a data table)."""

_MARKDOWN_PARAMETERS: Final[frozenset[str]] = frozenset({"artifact", "text"})
"""core.markdown's accepted parameter vocabulary."""

_VARIABLE: Final[re.Pattern[str]] = MARKDOWN_VARIABLE_RE
"""A template variable: ``{{ name }}`` or ``{{name}}``, dotted paths
included — resolving against the artifact's top-level object."""

_HEADING_TAGS: Final[frozenset[str]] = frozenset({"h2", "h3", "h4"})
"""Prose headings as written: ``##`` through ``####``."""

_H1_TEACHING: Final[str] = (
    "core.markdown: '#' headings are not part of the prose vocabulary — "
    "the card's title is this section's heading; write prose sections "
    "at '##'"
)
_DEEP_TEACHING: Final[str] = (
    "core.markdown: prose headings run '##' through '####' — deeper "
    "structure belongs in separate prose cards"
)
_LINK_TEACHING: Final[str] = (
    "core.markdown: links are not part of the prose vocabulary — the "
    "framework owns navigation"
)
_IMAGE_TEACHING: Final[str] = (
    "core.markdown: images are not part of the prose vocabulary — "
    "figures belong to figure components (core.chart, or a plugin's)"
)
_TABLE_TEACHING: Final[str] = (
    "core.markdown: tables are not part of the prose vocabulary — "
    "place the data with core.table instead"
)
_HTML_TEACHING: Final[str] = (
    "core.markdown: raw HTML is not part of the prose vocabulary"
)

_INLINE_PASSTHROUGH: Final[dict[str, str]] = {
    "strong_open": "<strong>",
    "strong_close": "</strong>",
    "em_open": "<em>",
    "em_close": "</em>",
    "hardbreak": "<br>",
}
"""The inline subset that maps token type to fixed markup."""

_INLINE_TEACHINGS: Final[dict[str, str]] = {
    "link_open": _LINK_TEACHING,
    "link_close": _LINK_TEACHING,
    "image": _IMAGE_TEACHING,
    "html_inline": _HTML_TEACHING,
}
"""The inline constructs that teach, by token type."""

_BLOCK_PASSTHROUGH: Final[frozenset[str]] = frozenset(
    {
        "paragraph_open",
        "paragraph_close",
        "bullet_list_open",
        "bullet_list_close",
        "ordered_list_open",
        "ordered_list_close",
        "list_item_open",
        "list_item_close",
        "blockquote_open",
        "blockquote_close",
        "dl_open",
        "dl_close",
        "dt_open",
        "dt_close",
        "dd_open",
        "dd_close",
    }
)
"""The paired containers: the parser's own tag rides through."""

_BLOCK_TEACHINGS: Final[dict[str, str]] = {
    "table_open": _TABLE_TEACHING,
    "html_block": _HTML_TEACHING,
}
"""The block constructs that teach, by token type."""


@dataclass(frozen=True, slots=True)
class _ProseSpec:
    """One placement's parameters, parsed and shape-validated."""

    artifact_type: str | None
    text: str


def _parse_spec(parameters: ComponentParameters) -> _ProseSpec:
    """Parse and shape-validate the placement's parameters, or teach.

    The shape half of the honest-data law: the closed vocabulary is
    checked first, and no data is touched here.
    """
    reject_unknown_parameters("core.markdown", parameters, _MARKDOWN_PARAMETERS)
    return _ProseSpec(
        artifact_type=_optional_text("core.markdown", parameters, "artifact"),
        text=_required_text("core.markdown", parameters, "text"),
    )


def _escape_text(raw: str) -> str:
    """Author text: '<' and '>' escaped, '&' rides — the author's
    entities (``&amp;``) stay entities, per CommonMark."""
    return raw.replace("<", "&lt;").replace(">", "&gt;")


def _escape_code(raw: str) -> str:
    """Code and fence content: fully escaped — code is literal
    characters, entities included."""
    return html.escape(raw, quote=False)


def _resolve(name: str, values: dict[str, JsonValue], label: str) -> str:
    """One variable's value, as raw text — the walk escapes it per context (text or
    code), the same treatment author text gets.

    Scalars render — strings verbatim, numbers as written, booleans
    as their JSON literals; structure teaches, naming the variable
    and its kind; a path the artifact does not carry teaches too:
    the prose promised a value the artifact does not hold.
    """
    node: JsonValue = values
    walked: list[str] = []
    for segment in name.split("."):
        if not isinstance(node, dict) or segment not in node:
            where = ".".join(walked) or "the top level"
            raise ValueError(
                f"core.markdown: variable {name!r} is missing from "
                f"artifact {label} (no {segment!r} under {where}) — the "
                f"prose promises a value the artifact does not carry"
            )
        walked.append(segment)
        node = node[segment]
    if isinstance(node, bool):
        return "true" if node else "false"
    if isinstance(node, (str, int, float)):
        return node if isinstance(node, str) else str(node)
    kind = (
        "null"
        if node is None
        else ("a list" if isinstance(node, list) else "an object")
    )
    raise ValueError(
        f"core.markdown: variable {name!r} resolved to {kind} — only "
        f"strings, numbers, and booleans render in prose"
    )


def _substitute(raw: str, values: dict[str, JsonValue], label: str) -> str:
    """Variables inside already-tokenized content → resolved values.

    The content arrives post-parse, so no substitution can ever be
    re-interpreted as markdown — the values-are-text law by
    construction.
    """

    def replace(match: re.Match[str]) -> str:
        return _resolve(match.group(1), values, label)

    return _VARIABLE.sub(replace, raw)


def _demote(tag: str) -> str:
    """One heading level down: ``h2`` → ``h3``."""
    return f"h{int(tag[1]) + 1}"


def _paired_tag(token: Token) -> str:
    """One paired container's tag — or nothing, when the parser
    marked the token hidden (tight lists' inner paragraphs)."""
    if token.hidden:
        return ""
    return f"<{token.tag}>" if token.nesting > 0 else f"</{token.tag}>"


def _open_heading(tag: str) -> str:
    """A prose heading's demoted opening tag, or its teaching."""
    if tag == "h1":
        raise ValueError(_H1_TEACHING)
    if tag not in _HEADING_TAGS:
        raise ValueError(_DEEP_TEACHING)
    return f"<{_demote(tag)}>"


def _copy_button(context: RenderContext) -> str:
    """Copy chrome for fenced code, hidden until scripting enhances it."""
    copy_icon = context.icons.load("core-copy").markup
    check_icon = context.icons.load("core-check").markup
    return (
        '<button type="button" class="coda-prose__copy"'
        ' aria-label="Copy code">'
        f'<span class="coda-prose__copy-icon">{copy_icon}</span>'
        f'<span class="coda-prose__copy-check">{check_icon}</span>'
        "</button>"
        '<span class="coda-prose__copy-feedback" aria-live="polite"></span>'
        '<span class="coda-prose__copy-status coda-prose__sr"'
        ' aria-live="polite"></span>'
    )


def _walk_inline(
    children: Sequence[Token], values: dict[str, JsonValue], label: str
) -> str:
    """Render an inline token stream: the subset's inline vocabulary.

    The dispatch is four cases: the content-bearing tokens (text,
    code — the only kinds that substitute), the fixed markup
    (:data:`_INLINE_PASSTHROUGH`), the teachings
    (:data:`_INLINE_TEACHINGS`), and the default-deny else.
    """
    out: list[str] = []
    for child in children:
        kind = child.type
        if kind in ("text", "text_special"):
            out.append(_escape_text(_substitute(child.content, values, label)))
        elif kind == "code_inline":
            rendered = _escape_code(_substitute(child.content, values, label))
            out.append(f"<code>{rendered}</code>")
        elif kind == "softbreak":
            out.append("\n")
        elif kind == "entity":
            out.append(child.content)
        elif kind in _INLINE_PASSTHROUGH:
            out.append(_INLINE_PASSTHROUGH[kind])
        elif kind in _INLINE_TEACHINGS:
            raise ValueError(_INLINE_TEACHINGS[kind])
        else:
            raise ValueError(
                f"core.markdown: {kind} markup is not part of the prose vocabulary"
            )
    return "".join(out)


def _walk_block(
    tokens: Sequence[Token],
    values: dict[str, JsonValue],
    label: str,
    copy_button: str = "",
) -> str:
    """Render a block token stream: the subset's block vocabulary."""
    out: list[str] = []
    for token in tokens:
        kind = token.type
        if kind == "inline":
            out.append(_walk_inline(token.children or (), values, label))
        elif kind in _BLOCK_PASSTHROUGH:
            out.append(_paired_tag(token))
        elif kind == "heading_open":
            out.append(_open_heading(token.tag))
        elif kind == "heading_close":
            out.append(f"</{_demote(token.tag)}>")
        elif kind == "fence":
            rendered = _escape_code(_substitute(token.content, values, label))
            out.append(
                '<div class="coda-prose__code-block">'
                f"{copy_button}"
                f"<pre><code>{rendered}</code></pre>"
                "</div>"
            )
        elif kind == "hr":
            out.append("<hr>")
        elif kind in _BLOCK_TEACHINGS:
            raise ValueError(_BLOCK_TEACHINGS[kind])
        else:
            raise ValueError(
                f"core.markdown: {kind} blocks are not part of the prose vocabulary"
            )
    return "".join(out)


def render_markdown(
    context: RenderContext,
    info: PlacementInfo,
    parameters: ComponentParameters,
) -> RenderedComponent:
    """Render one prose card: the author's markdown, the artifact's
    values, the framework's card and title.

    The orchestrator only sequences: parse the parameters
    (:func:`_parse_spec`), require the declared artifact if any (a
    missing artifact is an unavailable notice, the store's message
    riding), then parse and walk the template with values
    substituting as text.  Checksum and read failures propagate:
    a corrupt artifact is the manifest lying, a plugin failure the
    builder reports — never a quiet notice.
    """
    spec = _parse_spec(parameters)
    values: dict[str, JsonValue] = {}
    label = "the artifact"
    if spec.artifact_type is not None:
        try:
            artifact = context.store.require(spec.artifact_type)
        except ArtifactUnavailableError as e:
            return RenderedComponent.unavailable(str(e))
        if artifact.declaration.format is not ArtifactFormat.JSON:
            raise ValueError(
                f"core.markdown: artifact {spec.artifact_type!r} has format "
                f"'{artifact.declaration.format}'; core.markdown reads JSON "
                f"artifacts — point 'artifact' at a JSON artifact"
            )
        payload = artifact.read_json()
        label = f"{artifact.declaration.id!r} ({spec.artifact_type})"
        if isinstance(payload, dict):
            values = payload
    if _VARIABLE.search(spec.text) is not None:
        if spec.artifact_type is None:
            raise ValueError(
                "core.markdown: the text declares template variables but "
                "no 'artifact' parameter names their source — declare "
                "the JSON artifact carrying the values"
            )
        if not values:
            raise ValueError(
                f"core.markdown: template variables resolve against the "
                f"artifact's top-level object, but artifact {label} is "
                f"not one"
            )
    tokens = _MD.parse(spec.text)
    copy_button = (
        _copy_button(context) if any(token.type == "fence" for token in tokens) else ""
    )
    body = _walk_block(tokens, values, label, copy_button)
    return RenderedComponent.from_html(f'<div class="coda-prose">{body}</div>')
