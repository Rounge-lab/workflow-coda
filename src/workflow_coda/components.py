"""The component and plugin contracts for report building.

Every report plugin codes against the types in this module: plugin identity
(:class:`PluginMetadata`), component declarations (:class:`ReportComponent`),
the typed outcome of a render call (:class:`RenderedComponent` with
:class:`ComponentStatus`), and the transport type for per-component
configuration (:data:`ComponentParameters`).

The division of responsibility is the one the roadmap records:

* Plugins own component *content*.  A render call returns a
  :class:`RenderedComponent` whose ``html`` is the component body.
  The framework wraps a ``CARD`` component in the shared card chrome
  and title; a ``TILE`` component painted its own card, and the
  framework contributes only the ``data-component`` wrapper —
  available through ``chrome``.  Unavailable outcomes render through
  the framework's notice vocabulary in both modes.
* Degradation is data, not error.  Missing inputs are an ``unavailable``
  outcome with an explanatory message; plugin *bugs* are exceptions,
  which the report builder collects into the diagnostics section.
* Configuration is transport.  Layouts supply
  :data:`ComponentParameters`; each plugin reads and validates the keys
  it cares about, and the framework interprets none of them.  Plugins
  that want a closed vocabulary can call
  :func:`reject_unknown_parameters` to teach unknown keys — typos, and
  placement keys nested by accident — at the parse boundary.
* Plugins may ship page chrome.  A component's optional ``css`` and
  ``js`` declarations are inlined into the report exactly once, and
  only when one of its placements rendered — enhancement-only
  script, framework-owned ``coda-*`` names with plugin rules
  namespaced under ``coda-<plugin_id>-``, and both guarded at
  declaration against the sequences that would break out of their
  inline blocks.

These are in-memory contracts rather than deserialized artifacts, so they
follow :class:`workflow_coda.context.RenderContext` in being frozen,
slotted, keyword-only dataclasses whose invariants are enforced at
construction.  The manifest and theme, which *are* deserialized from
files, are strict pydantic models — that is the line between the two
families.  A contract violation fails at the call site with an
explanatory ``ValueError``, which the report builder reports as a plugin
failure.
"""

import difflib
import html
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, Protocol, Self

from .artifact_store import JsonValue
from .context import RenderContext
from .text import has_visible_text

_PLUGIN_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*$")
"""Shape of a valid plugin id: lowercase snake_case."""

COMPONENT_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"
)
"""Shape of a valid component id: ``<plugin_id>.<component_name>`` — the
contract shared by component declarations and layout placements."""

FIGURE_DIV_CLASS: Final[str] = "coda-figure"
"""The class :meth:`RenderedComponent.from_figure` wraps its embedded
figure in: the framework's figure marker.  The report renderer keys
Plotly.js inlining on it — the only html marker the framework scans
component content for."""


class ComponentStatus(Enum):
    """The outcome of a component render call.

    ``OK``
        The component rendered content.
    ``UNAVAILABLE``
        The component's inputs are missing (an artifact declared
        ``failed`` or ``missing``, or a condition such as too few
        samples); the message explains what and why.
    ``SKIPPED``
        The plugin intentionally produced no component for this
        placement; nothing is rendered.

    Values are lowercase strings because they surface in diagnostics
    text and as status classes on the rendered card in later milestones.
    """

    OK = "ok"
    UNAVAILABLE = "unavailable"
    SKIPPED = "skipped"


class SupportsToHtml(Protocol):
    """An object that serializes itself to an HTML fragment, shaped like a
    Plotly figure's ``to_html`` method.

    The framework never imports Plotly; it accepts any figure object
    whose ``to_html`` accepts ``full_html`` and ``include_plotlyjs``
    keyword arguments and returns a string.
    """

    def to_html(
        self,
        *,
        full_html: bool,
        include_plotlyjs: bool,
        config: dict[str, Any] | None = None,
    ) -> str: ...


type ComponentParameters = Mapping[str, JsonValue]
"""Per-component configuration, supplied by the layout.

Transport only: values arrive exactly as the layout file wrote them, and
each plugin reads and validates the keys it cares about.  The framework
interprets none of them.
"""


PLACEMENT_KEYS: Final[frozenset[str]] = frozenset(
    {"id", "title", "parameters", "on_missing", "on_unavailable"}
)
"""The placement grammar's own keys — mirrored from
:class:`workflow_coda.layout.ComponentPlacement` (defined there,
mirrored here to keep the import graph acyclic; a pinning test
holds the mirror honest).  These are the keys a layout author is
likeliest to nest inside a component's ``parameters:`` block by
accident."""


def reject_unknown_parameters(
    component_id: str,
    parameters: ComponentParameters,
    accepted: frozenset[str],
) -> None:
    """Reject parameter keys outside *accepted* with one teaching error.

    Parameters are transport — a plugin reads its own keys and the
    framework interprets none — but silence is not strictness: an
    unknown key in a hand-authored layout is either a typo or a
    placement key nested one level too deep, and both are authoring
    mistakes a plugin can teach here, at the parse boundary, before
    any data is touched.  A placement key (:data:`PLACEMENT_KEYS`)
    teaches the move — out of ``parameters:``, next to ``id``; any
    other unknown key teaches the accepted vocabulary, with a
    closest-match suggestion when one is close.

    Plugins call this first thing in their parameter parse; it
    raises, or returns ``None`` when every key is accepted.
    """
    unknown = sorted(key for key in parameters if key not in accepted)
    if not unknown:
        return
    findings: list[str] = []
    for key in unknown:
        if key in PLACEMENT_KEYS:
            findings.append(
                f"{key!r} is a placement key, not a component parameter "
                f"— move it out of 'parameters:' to the placement level, "
                f"next to 'id'"
            )
            continue
        close = difflib.get_close_matches(key, accepted, n=1)
        hint = f" (did you mean {close[0]!r}?)" if close else ""
        findings.append(f"unknown parameter {key!r}{hint}")
    accepted_names = ", ".join(f"{key!r}" for key in sorted(accepted))
    raise ValueError(
        f"{component_id}: {', '.join(findings)} — the accepted parameters "
        f"are: {accepted_names}"
    )


@dataclass(frozen=True, slots=True)
class PlacementInfo:
    """The placement's facts, handed to every render call.

    A placement's *resolved title* — the layout's own name for this
    instance, or the component declaration's default when the layout
    doesn't name it — is builder-resolved data, not a parameter: the
    parameters transport is the layout's key-value payload, and the
    framework interprets none of it.  A ``TILE`` component paints this
    title itself; for a ``CARD`` component it is the card heading the
    framework renders.
    """

    title: str
    """The resolved instance title; see the class docstring."""


type ComponentRenderer = Callable[
    [RenderContext, PlacementInfo, ComponentParameters], RenderedComponent
]
"""A component's render callable: the report context, the placement's
resolved facts, and the component's layout parameters in, one typed
outcome out."""


@dataclass(frozen=True, slots=True, kw_only=True)
class RenderedComponent:
    """The typed outcome of one component render call.

    ``status`` decides what the framework renders: ``OK`` wraps ``html`` in the
    component's chrome — the shared card for a ``CARD`` component, the plugin's own
    painted card for a ``TILE``; ``UNAVAILABLE`` renders ``message`` through the notice
    template; ``SKIPPED`` renders nothing.  The
    template renders framework values (title, message) with autoescaping;
    ``html`` content is the plugin's own responsibility.

    Construct through the helpers where possible:

    * :meth:`from_html` for hand-written HTML content.
    * :meth:`from_figure` for a Plotly-shaped figure, embedded correctly.
    * :meth:`unavailable` when inputs are missing, with an explanation.
    * :meth:`skipped` to produce no component.
    """

    status: ComponentStatus
    """What the outcome is; see :class:`ComponentStatus`."""

    html: str | None = None
    """The component's HTML body.  Required and non-empty for ``OK``,
    forbidden otherwise."""

    message: str | None = None
    """The explanation for an ``UNAVAILABLE`` outcome.  Required and
    non-empty for ``UNAVAILABLE``, forbidden otherwise."""

    def __post_init__(self) -> None:
        """Enforce the status/field invariants."""
        if not isinstance(self.status, ComponentStatus):
            raise ValueError(
                f"RenderedComponent status must be a ComponentStatus member, "
                f"got {self.status!r}"
            )
        if self.status is ComponentStatus.OK:
            self._validate_ok()
        elif self.status is ComponentStatus.UNAVAILABLE:
            self._validate_unavailable()
        elif self.status is ComponentStatus.SKIPPED:
            self._validate_skipped()

    def _validate_ok(self) -> None:
        """``OK`` requires visible html content and no message."""
        if self.html is None:
            raise ValueError(
                "an 'ok' RenderedComponent requires html content; "
                "use RenderedComponent.from_html() or from_figure()"
            )
        if not has_visible_text(self.html):
            raise ValueError(
                "RenderedComponent html must contain visible content; "
                "use RenderedComponent.skipped() to produce no component"
            )
        if self.message is not None:
            raise ValueError(
                "an 'ok' RenderedComponent takes no message; "
                "embed notes in the html content"
            )

    def _validate_unavailable(self) -> None:
        """``UNAVAILABLE`` requires a visible message and no html."""
        if self.message is None:
            raise ValueError(
                "an 'unavailable' RenderedComponent requires an "
                "explanation message; use RenderedComponent.unavailable()"
            )
        if not has_visible_text(self.message):
            raise ValueError("RenderedComponent message must contain visible text")
        if self.html is not None:
            raise ValueError(
                "an 'unavailable' RenderedComponent renders no html; "
                "use status 'ok' to render content"
            )

    def _validate_skipped(self) -> None:
        """``SKIPPED`` carries no content."""
        if self.html is not None or self.message is not None:
            raise ValueError(
                "a 'skipped' RenderedComponent carries no content; "
                "use RenderedComponent.unavailable() to explain a "
                "missing component"
            )

    @classmethod
    def from_html(cls, html: str) -> Self:
        """An ``OK`` component with hand-written HTML content."""
        return cls(status=ComponentStatus.OK, html=html)

    @classmethod
    def from_figure(
        cls, figure: SupportsToHtml, description: str | None = None
    ) -> Self:
        """An ``OK`` component embedding a Plotly-shaped figure.

        The embedding flags live here, not in every plugin: the figure is
        embedded as a bare ``<div>`` (the wrapper template owns the page
        chrome), without its own Plotly.js bundle (the report page loads
        Plotly.js exactly once), configured responsive (the plot resizes
        with its card as the window does), and wrapped in the framework's
        figure class — the marker the report renderer keys Plotly.js
        inlining on.  Getting any of these wrong in a plugin is the
        classic bug this constructor makes impossible.

        *description* is the figure's *accessibility label* — the text
        assistive technology announces instead of the plot's SVG, which
        screen readers cannot use.  Optional and deliberately separate
        from any visible caption the plot itself carries: the label
        answers "what is this" for non-sighted readers; the caption
        says what the author wants everyone to see next to the plot.
        When given, a one-line summary of chart type, subject and key
        finding — "Line chart: per-sample depth, all above 10×" — not
        a repetition of the component title; blank text is rejected.

        The framework cannot judge whether a *meaningful* label was
        written.  For components shipped with workflow-coda and its
        semi-official extensions, the description is **required** —
        that is the accessibility bar for framework-owned content,
        stated in the documentation; third-party plugins are trusted
        to write one, or not.
        """
        html_out = (
            f'<div class="{FIGURE_DIV_CLASS}" '
            + (
                f'role="img" aria-label="{html.escape(description, quote=True)}">'
                if description is not None
                else ">"
            )
            + figure.to_html(
                full_html=False,
                include_plotlyjs=False,
                config={"responsive": True},
            )
            + "</div>"
        )
        if description is not None and not has_visible_text(description):
            raise ValueError(
                "figure description must contain visible text — it is "
                "the text alternative readers using assistive "
                "technology get instead of the plot"
            )
        return cls(status=ComponentStatus.OK, html=html_out)

    @classmethod
    def unavailable(cls, message: str) -> Self:
        """An ``UNAVAILABLE`` outcome explaining what is missing and why.

        Expected missing data is a message, not an error; the framework
        renders it as a notice.
        """
        return cls(status=ComponentStatus.UNAVAILABLE, message=message)

    @classmethod
    def skipped(cls) -> Self:
        """A ``SKIPPED`` outcome: the plugin produces no component."""
        return cls(status=ComponentStatus.SKIPPED)


@dataclass(frozen=True, slots=True, kw_only=True)
class PluginMetadata:
    """Identity and compatibility for a report plugin.

    Constructed by the plugin itself and surfaced everywhere the plugin
    is named: registration, version gating, diagnostics, and component
    id prefixes.

    ``supported_schema_versions`` is the version gate: the report builder
    refuses to run a plugin whose set does not include the manifest's
    ``schema_version``, and the diagnostics section names both versions.
    The current manifest schema version is ``"0.2.0"``.
    """

    id: str
    """The plugin's id: lowercase snake_case, e.g. ``virmake``.  Component
    ids are prefixed with it (``<plugin_id>.<component_name>``)."""

    name: str
    """Human-readable plugin name, e.g. ``'VirMake report components'``."""

    version: str
    """The plugin's own version string."""

    description: str
    """One or two sentences on what the plugin provides."""

    supported_schema_versions: frozenset[str]
    """Manifest schema versions this plugin understands, e.g.
    ``frozenset({"0.2.0"})``.  Must be non-empty."""

    def __post_init__(self) -> None:
        """Enforce the id shape and non-empty text fields."""
        if _PLUGIN_ID_PATTERN.fullmatch(self.id) is None:
            raise ValueError(
                f"invalid plugin id {self.id!r}: must be lowercase "
                f"snake_case (letters, digits, underscores, starting "
                f"with a letter)"
            )
        for field_name in ("name", "version", "description"):
            if not has_visible_text(getattr(self, field_name)):
                raise ValueError(
                    f"plugin {self.id!r}: {field_name} must contain visible text"
                )
        if not self.supported_schema_versions:
            raise ValueError(
                f"plugin {self.id!r}: supported_schema_versions must name "
                f"at least one manifest schema version (currently '0.2.0')"
            )


class ComponentChrome(Enum):
    """Who paints a component's chrome.

    ``CARD``
        The plugin returns body html; the framework wraps it in the
        shared card chrome and renders the resolved title as the
        card heading.
    ``TILE``
        The plugin painted its own card — title, plate, corners —
        and the framework contributes only the
        ``data-component`` wrapper.
    """

    CARD = "card"
    TILE = "tile"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReportComponent:
    """A declared report component offered by a plugin.

    ``id`` is the component's globally unique address,
    ``<plugin_id>.<component_name>`` with exactly one dot — both halves
    lowercase snake_case, e.g. ``generic.provenance``.  Layouts reference
    components by this id.  The registry additionally checks that the id's
    prefix matches the declaring plugin's own id.
    A component may also declare page chrome — optional ``css`` and
    ``js`` contributions, inlined once per report when one of its
    placements renders; the field docstrings carry the namespacing
    and enhancement-only laws.
    """

    id: str
    """The component id, ``<plugin_id>.<component_name>``."""

    title: str
    """Human-readable card title, rendered by the wrapper template."""

    description: str | None = None
    """Optional one-line subtitle, rendered by the card template."""

    render: ComponentRenderer
    """The component's render callable.

    The report builder invokes it once per rendered report with the
    render context, the placement's resolved facts, and the
    component's layout parameters.  Pass the function itself, not a
    call result: ``render`` is the recipe, not the meal.
    """

    chrome: ComponentChrome = ComponentChrome.CARD
    """Who paints this component's chrome.  A ``CARD`` component
    returns body html and the framework wraps it in the card chrome;
    a ``TILE`` component paints its own card — title, plate,
    corners — and the framework contributes only the
    ``data-component`` wrapper.  Defaults to ``CARD``, so every
    existing declaration stands."""

    css: str | None = None
    """The component's stylesheet contribution, inlined once per
    report — under a ``/* <component id> */`` banner in the page's
    component style block — when at least one of its placements
    renders ``OK``.  Available to both chrome modes: a ``CARD``
    component's body may need classes too.  Rules namespace under
    ``coda-<plugin_id>-`` (the framework owns bare ``coda-*``), load
    nothing external (the page's CSP enforces self-containment at
    read time), and must not contain ``'</style'`` — rejected here,
    at declaration, because the sequence would terminate the inline
    block early."""

    js: str | None = None
    """The component's script contribution, inlined once per report —
    after the framework's own scripts, so the DOM is established —
    when at least one of its placements renders ``OK``.
    Enhancement-only: the no-JS reader must see the complete
    document, so script adds behavior and never gates content.  The
    framework dispatches ``coda:tab-shown`` on tab activation;
    subscribe rather than reaching into the panels.  Must not contain
    ``'</script'`` — rejected here, at declaration, because the
    sequence would terminate the inline block early."""

    def __post_init__(self) -> None:
        """Enforce the id shape and non-empty text fields."""
        if not callable(self.render):
            raise ValueError(
                f"component {self.id!r}: render must be a callable taking "
                f"(context, placement_info, parameters); got {self.render!r} "
                f"— pass the function itself, not a call result"
            )
        if COMPONENT_ID_PATTERN.fullmatch(self.id) is None:
            raise ValueError(
                f"invalid component id {self.id!r}: must be "
                f"'<plugin_id>.<component_name>', lowercase snake_case on "
                f"both sides of exactly one dot"
            )
        if not self.title:
            raise ValueError(f"component {self.id!r}: title must be non-empty")
        if not has_visible_text(self.title):
            raise ValueError(f"component {self.id!r}: title must contain visible text")
        if self.description is not None and not self.description:
            raise ValueError(
                f"component {self.id!r}: description must be non-empty when given"
            )
        if self.description is not None and not has_visible_text(self.description):
            raise ValueError(
                f"component {self.id!r}: description must contain visible "
                f"text when given"
            )
        if self.css is not None and not self.css.strip():
            raise ValueError(f"component {self.id!r}: css must not be blank when given")
        if self.js is not None and not self.js.strip():
            raise ValueError(f"component {self.id!r}: js must not be blank when given")
        if self.css is not None and "</style" in self.css.lower():
            raise ValueError(
                f"component {self.id!r}: css must not contain '</style' — "
                f"the sequence would terminate the report's inline style "
                f"block early; if it appears inside a string, escape "
                f"the '<' as '\\<'"
            )
        if self.js is not None and "</script" in self.js.lower():
            raise ValueError(
                f"component {self.id!r}: js must not contain '</script' — "
                f"the sequence would terminate the report's inline script "
                f"block early; if it appears inside a string literal, "
                f"escape it as '<\\/script'"
            )
