"""The notice component: the author's stance card, in the framework's
notice family.

``core.notice`` renders one block of author prose with a stance —
a note, a success, a warning, a failure — as a card in the
framework's own notice vocabulary: the same ``coda-card--<level>``
family the degradation cards wear (an unavailable outcome is a
notice, a plugin bug a failure), so the author's judgments and the
framework's read as one language.  It is a ``TILE`` component: it
paints its own card, the resolved title included, as a native
``<details>`` disclosure whose ``<summary>`` is the card's header.

The component's laws:

* *The stance is the border.*  Levels map onto the theme's judgment
  tokens — note wears ``muted``, success ``success``, warning
  ``warning``, failure ``danger`` — through the shared card family
  classes, never through a color the author picks for a judgment.
  ``note`` alone makes no semantic claim, so it alone accepts
  ``color``: a theme token named by the author, rendered inline as
  the border's color — and never ``success``, ``warning``, or
  ``danger``, which would forge a status the author never judged.
* *The content is the prose subset.*  The body parses through
  core.markdown's walk — the same strict subset, the same
  teachings, definition lists included — shared the way the tabular
  grammar is shared between table and chart.  v1's text is static
  authorship: template variables teach toward core.markdown, which
  owns artifact-backed prose.
* *The collapse is native.*  ``collapsed`` sets the initial state
  only; the summary row is always the toggle, and the mechanism is
  the browser's own ``<details>`` — no script, keyboard and
  screen-reader behavior included, complete for the no-JS reader.
* *A notice reads no artifacts*, so it is never unavailable: its
  outcomes are ``ok`` or a teaching, the roster's smallest honest
  family.
"""

import html
from dataclasses import dataclass
from typing import Final

from ..components import (
    ComponentParameters,
    PlacementInfo,
    RenderedComponent,
    reject_unknown_parameters,
)
from ..context import RenderContext
from .markdown import _MD, _VARIABLE, _walk_block
from .parameters import (
    _optional_bool,
    _optional_one_of,
    _optional_text,
    _required_text,
)

_LEVELS: Final[frozenset[str]] = frozenset({"note", "success", "warning", "failure"})
"""The stances, mapped one-to-one onto the framework's card family
classes and the theme's judgment tokens."""

_RESERVED_COLOR_TOKENS: Final[frozenset[str]] = frozenset(
    {"success", "warning", "danger"}
)
"""Theme tokens a note may not wear: each belongs to a judgment
level, and a note wearing one would forge a status."""

_NOTICE_PARAMETERS: Final[frozenset[str]] = frozenset(
    {"level", "color", "collapsed", "text"}
)
"""core.notice's accepted parameter vocabulary."""


@dataclass(frozen=True, slots=True)
class _NoticeSpec:
    """One placement's parameters, parsed and shape-validated."""

    level: str
    color_name: str | None
    collapsed: bool
    text: str


def _parse_spec(parameters: ComponentParameters) -> _NoticeSpec:
    """Parse and shape-validate the placement's parameters, or teach.

    The shape half of the honest-data law: the closed vocabulary is
    checked first, and the level/color consistency rules fire here,
    before any theme is touched.  The variable check is content
    shape: v1's text is static, and a template variable is a
    vocabulary mistake with a named home.
    """
    reject_unknown_parameters("core.notice", parameters, _NOTICE_PARAMETERS)
    spec = _NoticeSpec(
        level=_optional_one_of(
            "core.notice", parameters, "level", _LEVELS, default="note"
        ),
        color_name=_optional_text("core.notice", parameters, "color"),
        collapsed=_optional_bool("core.notice", parameters, "collapsed", default=False),
        text=_required_text("core.notice", parameters, "text"),
    )
    if spec.color_name is not None and spec.level != "note":
        raise ValueError(
            "core.notice: parameter 'color' pairs with level 'note' — "
            "the judgment levels wear their own theme tokens; drop "
            "'color', or set level: note"
        )
    if spec.color_name in _RESERVED_COLOR_TOKENS:
        raise ValueError(
            "core.notice: 'color' may not name 'success', 'warning', or "
            "'danger' — a note wearing a judgment token would forge a "
            "status the author never judged; choose another theme token"
        )
    if _VARIABLE.search(spec.text) is not None:
        raise ValueError(
            "core.notice: the notice's text is static prose — template "
            "variables are not part of it; core.markdown resolves {{ }} "
            "variables from a declared JSON artifact, so place "
            "artifact-backed prose there, or write the values directly"
        )
    return spec


def _assemble_markup(
    spec: _NoticeSpec,
    title: str,
    border: str | None,
    body: str,
    dropdown_icon: str,
) -> str:
    """Emit the disclosure card: the summary row, the prose body.

    Pure string assembly — every decision is already made; the
    author-sourced title escapes here, and the body is the walk's
    output over the static text.
    """
    classes = f"coda-card coda-card--{spec.level} coda-notice"
    style = f' style="border-left-color: {border};"' if border is not None else ""
    open_attr = "" if spec.collapsed else " open"
    return (
        f'<details class="{classes}"{style}{open_attr}>'
        '<summary class="coda-notice__summary">'
        f'<span class="coda-notice__title">{html.escape(title)}</span>'
        f'<span class="coda-notice__dropdown">{dropdown_icon}</span>'
        "</summary>"
        f'<div class="coda-notice__body coda-prose">{body}</div>'
        "</details>"
    )


def render_notice(
    context: RenderContext,
    info: PlacementInfo,
    parameters: ComponentParameters,
) -> RenderedComponent:
    """Render one stance card: the level from the layout, the color
    from the theme (when the note names a token), the words through
    the prose subset — the whole card, the resolved title included,
    because the notice is a ``TILE`` component.

    The orchestrator only sequences: parse the placement's
    parameters (:func:`_parse_spec`), resolve the note's custom
    color against the theme when one is named, walk the text
    through the prose subset, and assemble the disclosure
    (:func:`_assemble_markup`) around the placement's resolved
    title.  A notice reads no artifacts, so no outcome exists but
    ``ok`` and the teachings.
    """
    spec = _parse_spec(parameters)
    border = (
        context.theme.css_color("core.notice", spec.color_name)
        if spec.color_name is not None
        else None
    )
    body = _walk_block(_MD.parse(spec.text), {}, "the notice")
    dropdown_icon = context.icons.load("core-dropdown").markup
    return RenderedComponent.from_html(
        _assemble_markup(spec, info.title, border, body, dropdown_icon)
    )
