"""The component and plugin contracts for report building.

Every report plugin codes against the types in this module: plugin identity
(:class:`PluginMetadata`), component declarations (:class:`ReportComponent`),
the typed outcome of a render call (:class:`RenderedComponent` with
:class:`ComponentStatus`), and the transport type for per-component
configuration (:data:`ComponentParameters`).

The division of responsibility is the one the roadmap records:

* Plugins own component *content*.  A render call returns a
  :class:`RenderedComponent` whose ``html`` is the component body; the
  framework wraps it in the shared card chrome and title, and renders
  unavailable outcomes through the notice template.
* Degradation is data, not error.  Missing inputs are an ``unavailable``
  outcome with an explanatory message; plugin *bugs* are exceptions,
  which the report builder collects into the diagnostics section.
* Configuration is transport.  Layouts supply
  :data:`ComponentParameters`; each plugin reads and validates the keys
  it cares about, and the framework interprets none of them.

These are in-memory contracts rather than deserialized artifacts, so they
follow :class:`workflow_coda.context.RenderContext` in being frozen,
slotted, keyword-only dataclasses whose invariants are enforced at
construction.  The manifest and theme, which *are* deserialized from
files, are strict pydantic models — that is the line between the two
families.  A contract violation fails at the call site with an
explanatory ``ValueError``, which the report builder reports as a plugin
failure.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Final, Protocol, Self

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
        self, full_html: bool = ..., include_plotlyjs: bool | str = ...
    ) -> str: ...


type ComponentParameters = Mapping[str, JsonValue]
"""Per-component configuration, supplied by the layout.

Transport only: values arrive exactly as the layout file wrote them, and
each plugin reads and validates the keys it cares about.  The framework
interprets none of them.
"""


type ComponentRenderer = Callable[
    [RenderContext, ComponentParameters], RenderedComponent
]
"""A component's render callable: the report context and the component's
layout parameters in, one typed outcome out."""


@dataclass(frozen=True, slots=True, kw_only=True)
class RenderedComponent:
    """The typed outcome of one component render call.

    ``status`` decides what the framework renders: ``OK`` wraps ``html``
    in the shared component chrome; ``UNAVAILABLE`` renders ``message``
    through the notice template; ``SKIPPED`` renders nothing.  The
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
    def from_figure(cls, figure: SupportsToHtml) -> Self:
        """An ``OK`` component embedding a Plotly-shaped figure.

        The embedding flags live here, not in every plugin: the figure is
        embedded as a bare ``<div>`` (the wrapper template owns the page
        chrome) and without its own Plotry.js bundle (the report page loads
        Plotly.js exactly once).  Getting either wrong in a plugin is the
        classic bug this constructor makes impossible.
        """
        return cls(
            status=ComponentStatus.OK,
            html=figure.to_html(full_html=False, include_plotlyjs=False),
        )

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
    The current manifest schema version is ``"0.1.0"``.
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
    ``frozenset({"0.1.0"})``.  Must be non-empty."""

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
                f"at least one manifest schema version (currently '0.1.0')"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class ReportComponent:
    """A declared report component offered by a plugin.

    ``id`` is the component's globally unique address,
    ``<plugin_id>.<component_name>`` with exactly one dot — both halves
    lowercase snake_case, e.g. ``generic.provenance``.  Layouts reference
    components by this id.  The registry additionally checks that the id's
    prefix matches the declaring plugin's own id.
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
    render context and the component's layout parameters.  Pass the
    function itself, not a call result: ``render`` is the recipe, not
    the meal.
    """

    def __post_init__(self) -> None:
        """Enforce the id shape and non-empty text fields."""
        if not callable(self.render):
            raise ValueError(
                f"component {self.id!r}: render must be a callable taking "
                f"(context, parameters); got {self.render!r} — pass the "
                f"function itself, not a call result"
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
