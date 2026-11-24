"""The KPI component: one artifact-backed headline number.

``core.kpi`` renders one measurement — a depth, a runtime, a count —
as a headline stat card: one big number, an optional unit, an optional
author caption, and an optional icon, on an optional colored plate.
Its parameter grammar follows the honest-data law:

* the *value* is data: it reads from a manifest-verified JSON artifact
  through the store, addressed by artifact type and a dotted key path;
* *unit*, *decimals*, and *thresholds* are policy: the author's
  definition of what matters about the number — how it is shown, and
  when it counts as good;
* *caption* is authorship: prose, honest because visibly prose;
* *color*, *variant*, *icon*, and *icon_position* are presentation:
  colors resolve from the report's theme (token names or series
  entries — never literals), and icons load from the build's icon
  library through the render context — every installed plugin's
  shipped, sanitized, namespaced icons — so the report stays
  self-contained.
* the vocabulary is closed: unknown parameter keys teach at the
  parse boundary — typos with a closest-match suggestion, and
  placement keys (``on_unavailable`` and friends) with the
  instruction to move them out of ``parameters:``;

The card's *title* is not a parameter, and neither is it framework
chrome: the KPI is a ``TILE`` component and paints its own card —
the placement's resolved title (the layout's own ``title`` for this
instance, the declaration's default otherwise) arrives through
:class:`~workflow_coda.components.PlacementInfo`, and the framework
contributes only the ``data-component`` wrapper around the healthy
outcome.  Degradation is the framework's: an unavailable KPI
teaches in the notice card, whose heading is the same resolved
title.

Two failure families, kept distinct:

* a malformed parameter — every *shape* error — raises a teaching
  ``ValueError`` before any data is touched; the report builder
  collects it as a plugin failure shown in place, because the layout
  itself is wrong.  The value-dependent judgments (a non-scalar key,
  thresholds on a text value) fire where the data is;
* missing data — an undeclared artifact, a key the artifact does not
  carry — renders as an ``unavailable`` notice carrying the store's
  own message, because absent data is a fact about the run.

Checksum and read failures propagate: a corrupt artifact is the
manifest lying, which is a plugin failure the builder reports — never
a quiet notice.

User-provided icons — an SVG file next to the layout — are a planned
extension of the ``icon`` parameter; today it accepts shipped,
namespaced names only (``core-arrow-up`` and friends)."""

import html
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Final

from ..artifact_store import JsonValue
from ..components import (
    ComponentParameters,
    PlacementInfo,
    RenderedComponent,
    ThemeColorProperty,
    reject_unknown_parameters,
)
from ..context import RenderContext
from ..errors import ArtifactUnavailableError
from ..icons import Icon
from ..manifest.artifact import ArtifactFormat
from ..theme import ThemePair
from .parameters import _optional_one_of, _optional_text, _required_text

_VARIANTS: Final[frozenset[str]] = frozenset({"text", "fill", "gradient"})
"""The plate styles: plain text on the card, a solid color plate, or
a two-color gradient plate."""

_KPI_PARAMETERS: Final[frozenset[str]] = frozenset(
    {
        "artifact",
        "caption",
        "color",
        "decimals",
        "icon",
        "icon_position",
        "key",
        "thresholds",
        "unit",
        "variant",
    }
)
"""core.kpi's accepted parameter vocabulary: the closed set
:func:`_parse_spec` reads, for the unknown-key teaching."""

_ICON_POSITIONS: Final[frozenset[str]] = frozenset({"inline", "corner"})
"""Where the icon renders: in the value line, or pinned to the card's
corner."""


class KpiStatus(Enum):
    """The status a threshold policy assigns to a KPI value.

    Deliberately narrower than the component outcome vocabulary: a
    KPI is either unstatused (no policy declared) or judged by the
    author's own thresholds.  The status rides the wrapper as
    ``coda-kpi--<status>`` for semantics and styling."""

    OK = "ok"
    NOTICE = "notice"
    FAILURE = "failure"


_STATUS_COLOR_TOKENS: Final[dict[KpiStatus, str]] = {
    KpiStatus.OK: "success",
    KpiStatus.NOTICE: "warning",
    KpiStatus.FAILURE: "danger",
}
"""The theme token whose color a statused KPI wears when the author
declared no explicit color: the threshold policy's own vocabulary."""


def _optional_int(parameters: ComponentParameters, name: str) -> int | None:
    """An optional non-negative integer parameter, absent by default."""
    if name not in parameters:
        return None
    value = parameters[name]
    # JSON booleans are ints to isinstance(); refuse them explicitly.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"core.kpi: parameter {name!r}, when given, must be an "
            f"integer, got {value!r}"
        )
    if value < 0:
        raise ValueError(
            f"core.kpi: parameter {name!r} must be 0 or greater, got {value!r}"
        )
    return value


def _bound(group: str, bounds: Mapping[str, JsonValue], name: str) -> float | None:
    """One inclusive threshold bound: an optional number."""
    if name not in bounds:
        return None
    value = bounds[name]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"core.kpi: thresholds group {group!r} bound {name!r} must be "
            f"a number, got {value!r}"
        )
    return float(value)


def _thresholds_from(
    parameters: ComponentParameters,
) -> dict[str, tuple[float | None, float | None]] | None:
    """The thresholds policy, or ``None`` when the layout declares none.

    Shape::

        thresholds:
          ok: {above: 10, below: 1000}
          notice: {above: 5}

    Both groups optional, both bounds optional, bounds inclusive.  An
    empty ``thresholds`` object is a teaching error: it declares policy
    but judges nothing.
    """
    if "thresholds" not in parameters:
        return None
    raw = parameters["thresholds"]
    if not isinstance(raw, dict):
        raise ValueError(
            f"core.kpi: parameter 'thresholds', when given, must be an "
            f'object like {{"ok": {{"above": 10}}}}, got {raw!r}'
        )
    groups: dict[str, tuple[float | None, float | None]] = {}
    for group in ("ok", "notice"):
        if group not in raw:
            continue
        bounds = raw[group]
        if not isinstance(bounds, dict):
            raise ValueError(
                f"core.kpi: thresholds group {group!r} must be an object "
                f"with optional 'above' and 'below', got {bounds!r}"
            )
        groups[group] = (_bound(group, bounds, "above"), _bound(group, bounds, "below"))
    if not groups:
        raise ValueError(
            "core.kpi: parameter 'thresholds', when given, must declare "
            "an 'ok' and/or 'notice' group with bounds"
        )
    return groups


def _in_range(value: float, bounds: tuple[float | None, float | None]) -> bool:
    """Inclusive range test against optional bounds."""
    above, below = bounds
    if above is not None and value < above:
        return False
    if below is not None and value > below:
        return False
    return True


def _evaluate_thresholds(
    value: float, groups: dict[str, tuple[float | None, float | None]]
) -> KpiStatus:
    """ok first, then notice, else failure — the declared policy order."""
    if "ok" in groups and _in_range(value, groups["ok"]):
        return KpiStatus.OK
    if "notice" in groups and _in_range(value, groups["notice"]):
        return KpiStatus.NOTICE
    return KpiStatus.FAILURE


def _lookup_scalar(
    payload: JsonValue, key: str, artifact_label: str
) -> str | int | float:
    """The scalar at a dotted key path, teaching on the way down.

    A path that does not exist raises :class:`ArtifactUnavailableError`
    — missing data is a fact about the run.  A path that exists but
    lands on a non-scalar is an authoring error: a ``ValueError``
    naming what was found instead.
    """
    node: JsonValue = payload
    walked: list[str] = []
    for segment in key.split("."):
        if not isinstance(node, dict) or segment not in node:
            where = ".".join(walked) or "the root"
            raise ArtifactUnavailableError(
                f"core.kpi: artifact {artifact_label} carries no key "
                f"{key!r} (no {segment!r} under {where})"
            )
        walked.append(segment)
        node = node[segment]
    if isinstance(node, bool) or not isinstance(node, (str, int, float)):
        raise ValueError(
            f"core.kpi: key {key!r} in artifact {artifact_label} does not "
            f"name a scalar (got {type(node).__name__}); 'key' must point "
            f"at a string or number"
        )
    return node


def _format_value(value: str | int | float, decimals: int | None) -> str:
    """The value as the card shows it.

    Strings pass through verbatim — the producer's own formatting is
    data.  Numbers stringify honestly by default; ``decimals`` rounds
    for display when the author asks.
    """
    if isinstance(value, str):
        return value
    if decimals is None:
        return str(value)
    return f"{value:.{decimals}f}"


@dataclass(frozen=True, slots=True)
class _KpiSpec:
    """One placement's parameters, parsed and shape-validated.

    *color* rides raw (a theme token name, a series entry, or a
    two-entry gradient list): its *shape* was validated at parse
    time; its *resolution* against the theme happens later, in
    :func:`_resolve_palette`.
    """

    artifact_type: str
    key: str
    variant: str
    icon_position: str
    unit: str | None
    decimals: int | None
    caption: str | None
    icon_name: str | None
    thresholds: dict[str, tuple[float | None, float | None]] | None
    color: JsonValue | None


def _parse_spec(parameters: ComponentParameters) -> _KpiSpec:
    """Parse and shape-validate every parameter, or teach.

    The shape half of the honest-data law: this function touches no
    theme, store, or icon set — every malformed parameter, including
    the variant/color consistency rules below, raises its teaching
    ``ValueError`` here, before any data is read.  The vocabulary is
    closed and checked first: unknown keys — typos, and placement
    keys nested by accident — teach before any known key is read.
    """
    reject_unknown_parameters("core.kpi", parameters, _KPI_PARAMETERS)
    spec = _KpiSpec(
        artifact_type=_required_text("core.kpi", parameters, "artifact"),
        key=_required_text("core.kpi", parameters, "key"),
        variant=_optional_one_of(
            "core.kpi", parameters, "variant", _VARIANTS, default="text"
        ),
        icon_position=_optional_one_of(
            "core.kpi", parameters, "icon_position", _ICON_POSITIONS, default="inline"
        ),
        unit=_optional_text("core.kpi", parameters, "unit"),
        decimals=_optional_int(parameters, "decimals"),
        caption=_optional_text("core.kpi", parameters, "caption"),
        icon_name=_optional_text("core.kpi", parameters, "icon"),
        thresholds=_thresholds_from(parameters),
        color=parameters.get("color"),
    )
    if spec.variant == "gradient":
        if spec.color is None:
            raise ValueError(
                "core.kpi: variant 'gradient' requires 'color' — a "
                "two-entry list [from-color, to-color], e.g. "
                "['primary', 'accent']"
            )
    elif isinstance(spec.color, list):
        raise ValueError(
            "core.kpi: 'color' is a two-entry list, which only variant "
            f"'gradient' accepts; the variant is {spec.variant!r} — give "
            "a single theme token or series entry"
        )
    elif spec.variant == "fill" and spec.color is None and spec.thresholds is None:
        raise ValueError(
            "core.kpi: variant 'fill' requires 'color' (or a 'thresholds' "
            "policy to supply one), e.g. color: primary"
        )
    return spec


def _read_value(context: RenderContext, spec: _KpiSpec) -> str | int | float:
    """Read the KPI's scalar from its artifact, or raise why not.

    The data half: ``require`` and the dotted lookup both raise
    :class:`ArtifactUnavailableError` carrying the message the
    unavailable notice shows — the caller converts it.  A non-JSON
    artifact is a layout mistake, taught as a ``ValueError``.
    """
    artifact = context.store.require(spec.artifact_type)
    if artifact.declaration.format is not ArtifactFormat.JSON:
        raise ValueError(
            f"core.kpi: artifact {spec.artifact_type!r} has format "
            f"'{artifact.declaration.format}'; core.kpi reads "
            "JSON artifacts — point 'artifact' at a JSON artifact"
        )
    payload = artifact.read_json()
    label = f"{artifact.declaration.id!r} ({spec.artifact_type})"
    return _lookup_scalar(payload, spec.key, label)


def _assign_status(
    value: str | int | float,
    thresholds: dict[str, tuple[float | None, float | None]] | None,
) -> KpiStatus | None:
    """Apply the thresholds policy, or ``None`` when none declared."""
    if thresholds is None:
        return None
    if isinstance(value, str):
        raise ValueError(
            "core.kpi: parameter 'thresholds' requires a numeric "
            "value, but the artifact's value is a string — thresholds "
            "cannot compare text"
        )
    return _evaluate_thresholds(float(value), thresholds)


@dataclass(frozen=True, slots=True)
class _Palette:
    """Responsive CSS references and placement-local paired ink."""

    plate: str | None
    stops: tuple[str, str] | None
    ink: str | None
    theme_colors: tuple[ThemeColorProperty, ...] = ()


def _resolve_palette(
    theme: ThemePair,
    spec: _KpiSpec,
    status: KpiStatus | None,
) -> _Palette:
    """Resolve shared plate references and independently picked ink."""

    def plate_palette(
        references: tuple[object, ...],
    ) -> _Palette:
        backgrounds = tuple(
            theme.resolve_color("core.kpi", reference) for reference in references
        )
        css_references = tuple(
            theme.css_color("core.kpi", reference) for reference in references
        )
        ink = theme.text_on(*backgrounds)
        properties = (
            ThemeColorProperty(
                name="--coda-kpi-ink",
                light=ink.light,
                dark=ink.dark,
            ),
        )
        if len(css_references) == 1:
            return _Palette(
                plate=css_references[0],
                stops=None,
                ink="var(--coda-kpi-ink)",
                theme_colors=properties,
            )
        return _Palette(
            plate=None,
            stops=(css_references[0], css_references[1]),
            ink="var(--coda-kpi-ink)",
            theme_colors=properties,
        )

    if spec.variant == "gradient":
        raw = spec.color
        if not isinstance(raw, list) or len(raw) != 2:
            raise ValueError(
                "core.kpi: variant 'gradient' takes 'color' as a "
                "two-entry list [from-color, to-color], e.g. "
                f"['primary', 'accent'], got {raw!r}"
            )
        return plate_palette((raw[0], raw[1]))

    reference: object = spec.color
    if reference is None and status is not None:
        reference = _STATUS_COLOR_TOKENS[status]

    if spec.variant == "fill":
        assert reference is not None  # validated by _parse_spec
        return plate_palette((reference,))

    ink = theme.css_color("core.kpi", reference) if reference is not None else None
    return _Palette(plate=None, stops=None, ink=ink)


def _icon_html(icon: Icon | None, position: str) -> tuple[str, str]:
    """The icon as (inline, corner) markup for its position."""
    if icon is None:
        return "", ""
    if position == "corner":
        return "", f'<span class="coda-kpi__corner">{icon.markup}</span>'
    return icon.markup, ""


def _assemble_markup(
    spec: _KpiSpec,
    title: str,
    icon: Icon | None,
    value: str | int | float,
    status: KpiStatus | None,
    palette: _Palette,
) -> str:
    """Emit the KPI card: the plate wrapper, the title, the value
    line, the caption.

    Pure string assembly — every decision is already made; all
    author- or artifact-sourced text, the resolved title included,
    escapes here.
    """
    inline_icon, corner_icon = _icon_html(icon, spec.icon_position)
    title_html = f'<p class="coda-kpi__title">{html.escape(title)}</p>'
    unit_html = (
        f' <span class="coda-kpi__unit">{html.escape(spec.unit)}</span>'
        if spec.unit is not None
        else ""
    )
    caption_html = (
        f'<p class="coda-kpi__caption">{html.escape(spec.caption)}</p>'
        if spec.caption is not None
        else ""
    )
    classes = "coda-kpi"
    if spec.variant != "text":
        classes += f" coda-kpi--{spec.variant}"
    if status is not None:
        classes += f" coda-kpi--{status.value}"
    if spec.variant == "text":
        wrapper_style = ""
        value_style = (
            f' style="color: {palette.ink};"' if palette.ink is not None else ""
        )
    elif spec.variant == "fill":
        assert palette.plate is not None  # guaranteed by _resolve_palette
        wrapper_style = f' style="background: {palette.plate}; color: {palette.ink};"'
        value_style = ""
    else:
        assert palette.stops is not None  # guaranteed by _resolve_palette
        wrapper_style = (
            f' style="background: linear-gradient(135deg, {palette.stops[0]},'
            f' {palette.stops[1]}); color: {palette.ink};"'
        )
        value_style = ""
    return (
        f'<div class="{classes}"{wrapper_style}>'
        f"{corner_icon}"
        f"{title_html}"
        f'<p class="coda-kpi__value"{value_style}>'
        f"{html.escape(_format_value(value, spec.decimals))}{unit_html}"
        f"{inline_icon}"
        "</p>"
        f"{caption_html}"
        "</div>"
    )


def render_kpi(
    context: RenderContext,
    info: PlacementInfo,
    parameters: ComponentParameters,
) -> RenderedComponent:
    """Render one headline number: data from the store, policy from
    the layout, color from the theme, icons from the build's icon
    library — the whole card, the resolved title included, because
    the KPI is a ``TILE`` component.

    The orchestrator only sequences the stories: parse the placement's
    parameters (:func:`_parse_spec`), read the artifact value
    (:func:`_read_value`), apply the threshold policy
    (:func:`_assign_status`), resolve colors against the theme
    (:func:`_resolve_palette`), and assemble the markup
    (:func:`_assemble_markup`) around the placement's resolved title.
    Each helper owns its own errors; missing data converts to an
    unavailable notice here, where the outcome vocabulary lives.
    """
    spec = _parse_spec(parameters)
    icon = context.icons.load(spec.icon_name) if spec.icon_name is not None else None
    try:
        value = _read_value(context, spec)
    except ArtifactUnavailableError as e:
        return RenderedComponent.unavailable(str(e))
    status = _assign_status(value, spec.thresholds)
    palette = _resolve_palette(context.theme, spec, status)
    return RenderedComponent.from_html(
        _assemble_markup(spec, info.title, icon, value, status, palette),
        theme_colors=palette.theme_colors,
    )
