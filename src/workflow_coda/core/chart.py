"""The chart component: one artifact-backed Plotly figure.

``core.chart`` renders one ``core.tabular``-format artifact — the
core plugin's namespaced file format, shared with ``core.table``
— as one Plotly figure, inside the framework's card chrome: a CARD
component, so the framework paints the card and the placement's
resolved title, and this module paints the figure body.

The honest-data law, chart edition:

* the *rows* are data: read from the artifact verbatim, parsed
  under the placement's ``sep``, plotted in file order — the
  producer's order is the author's story;
* ``chart``, ``x``, and ``y`` are the plot's shape: the author's
  choice of what the figure shows, with no defaults to guess
  wrong — a histogram bins ``x`` and refuses ``y``; a box plot
  distributes ``y`` and groups by ``x`` or ``hue``, never both;
* ``hue`` is grouping: one trace per distinct value, colored from
  the theme's series palette in first-appearance order — the
  color story that owns the figure, and therefore refused together
  with ``color``; when the groups outnumber the palette the colors
  cycle, and a note in the report's diagnostics ledger says so;
* ``color``, ``grid``, ``log_x``, and ``log_y`` are presentation:
  colors resolve from the report's theme (token names or series
  entries — never literals), exactly the grammar ``core.kpi``
  established; log axes refuse the nonpositive values Plotly would
  silently drop;
* ``caption`` is authorship: prose, honest because visibly prose;
* the accessibility description is *inferred* from the figure's
  own facts — chart type, subject, size, grouping — never the
  author's job: the framework-owned bar, met by construction.

Plotly is imported inside the render call: a chartless report
builds on machines without it, and a placement that meets its
absence teaches the fix in the failure card.

Two failure families, kept distinct (the third is the format's
own, through the grammar helpers shared from the table module):

* a malformed parameter — every *shape* error, and the per-chart
  consistency rules — raises a teaching ``ValueError`` before any
  data is touched; the report builder collects it as a plugin
  failure shown in place.  Column-name membership and numeric-ness
  teach at data time, against the artifact's own header and values;
* missing data — an undeclared artifact, a non-complete status, an
  absent file, or a headered file with no data rows — renders as
  an ``unavailable`` notice carrying the store's own message,
  because absent data is a fact about the run;
* a file that does not parse under its claimed format — the
  ``core.tabular`` shape lies — teaches as
  :class:`~workflow_coda.errors.ArtifactReadError`, exactly as
  ``core.table`` teaches them.
"""

import html
import math
from dataclasses import dataclass, replace
from typing import Final, cast

from ..artifact_store import JsonValue
from ..components import (
    ComponentParameters,
    PlacementInfo,
    RenderedComponent,
    SupportsToHtml,
    reject_unknown_parameters,
)
from ..context import RenderContext
from ..errors import ArtifactUnavailableError, RenderError
from ..theme import ColorHex, Theme
from .colors import _SERIES_COLOR_PATTERN, _resolve_color
from .parameters import (
    _optional_bool,
    _optional_text,
    _required_one_of,
    _required_text,
    _sep_from,
)
from .table import _parse_entries, _require_aligned, _require_header

_FORMAT: Final[str] = "core.tabular"
"""The tabular file format this component reads — the core plugin's
namespaced format, shared with ``core.table``: a claim whose
grammar lives in the core package, for its components to
interpret.  This module is the format's second reader."""

_CHARTS: Final[frozenset[str]] = frozenset(
    {"bar", "box", "histogram", "line", "scatter"}
)
"""The plot vocabulary: the five generally useful chart types."""

_CHART_PARAMETERS: Final[frozenset[str]] = frozenset(
    {
        "artifact",
        "caption",
        "chart",
        "color",
        "grid",
        "hue",
        "log_x",
        "log_y",
        "sep",
        "x",
        "y",
    }
)
"""core.chart's accepted parameter vocabulary: the closed set
:func:`_parse_spec` reads, for the unknown-key teaching."""


@dataclass(frozen=True, slots=True)
class _ChartSpec:
    """One placement's parameters, parsed and shape-validated.

    *color* rides raw (a token name or a series entry): its shape
    is validated at parse time only against the hue/color rule;
    its resolution against the theme happens later, through the
    shared color grammar in the colors module.
    """

    artifact_type: str
    chart: str
    x: str | None
    y: str | None
    hue: str | None
    color: JsonValue | None
    sep: str
    grid: bool
    log_x: bool
    log_y: bool
    caption: str | None


def _parse_spec(parameters: ComponentParameters) -> _ChartSpec:
    """Parse and shape-validate every parameter, or teach.

    The shape half of the honest-data law: no store, artifact, or
    theme is touched here — every malformed parameter raises its
    teaching ``ValueError`` in this function, before any data is
    read.  The vocabulary is closed and checked first.  The
    per-chart consistency rules are parse-time, like the KPI's
    variant/color rules: the chart type is data-independent, and a
    histogram refusing ``y`` or a chart missing its axis columns
    is wrong on every dataset, not just this report's.
    """
    reject_unknown_parameters("core.chart", parameters, _CHART_PARAMETERS)
    chart = _required_one_of("core.chart", parameters, "chart", _CHARTS)
    x = _optional_text("core.chart", parameters, "x")
    y = _optional_text("core.chart", parameters, "y")
    hue = _optional_text("core.chart", parameters, "hue")
    spec = _ChartSpec(
        artifact_type=_required_text("core.chart", parameters, "artifact"),
        chart=chart,
        x=x,
        y=y,
        hue=hue,
        color=parameters.get("color"),
        sep=_sep_from("core.chart", parameters),
        grid=_optional_bool("core.chart", parameters, "grid", default=True),
        log_x=_optional_bool("core.chart", parameters, "log_x", default=False),
        log_y=_optional_bool("core.chart", parameters, "log_y", default=False),
        caption=_optional_text("core.chart", parameters, "caption"),
    )
    if chart == "histogram":
        if y is not None:
            raise ValueError(
                "core.chart: a histogram bins 'x' and counts the "
                "records — its y is the count; remove 'y', or use "
                "another chart type"
            )
        if x is None:
            raise ValueError(
                "core.chart: parameter 'x' is required for a histogram "
                "— the column to bin"
            )
    elif chart == "box":
        if y is None:
            raise ValueError(
                "core.chart: parameter 'y' is required for a box plot "
                "— the numeric column to distribute"
            )
        if x is not None and hue is not None:
            raise ValueError(
                "core.chart: a box plot groups by one column — 'x' or "
                "'hue', not both; drop one"
            )
        if spec.log_x:
            raise ValueError(
                "core.chart: a box plot's horizontal axis is categorical "
                "grouping — log_y transforms the values; drop 'log_x'"
            )
    else:
        if x is None or y is None:
            raise ValueError(
                f"core.chart: parameters 'x' and 'y' are required for a {chart} chart"
            )
    if hue is not None and spec.color is not None:
        raise ValueError(
            "core.chart: 'hue' groups the records into series-colored "
            "traces, which owns the color story — remove 'color', or "
            "replace 'hue' with a single color"
        )
    return spec


def _read_tabular(
    context: RenderContext, spec: _ChartSpec
) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    """Read and parse the artifact under the placement's ``sep``, or
    raise why not.

    Missing data raises :class:`ArtifactUnavailableError` — the
    caller converts it.  A file that does not parse under its
    claimed format teaches as :class:`ArtifactReadError`, from the
    shared grammar helpers — the producer lying about the
    artifact's shape.  A non-tabular artifact is a layout mistake,
    taught as a ``ValueError``.  The header is required: charts
    address columns by name.
    """
    artifact = context.store.require(spec.artifact_type)
    if artifact.declaration.format != _FORMAT:
        raise ValueError(
            f"core.chart: artifact {spec.artifact_type!r} has format "
            f"'{artifact.declaration.format}'; core.chart reads "
            "'core.tabular'-format artifacts — declare the artifact's "
            "format as 'core.tabular' in the manifest"
        )
    label = f"{artifact.declaration.id!r} ({spec.artifact_type})"
    entries = _parse_entries(artifact.read_text(), spec.sep, label)
    header, _has_index = _require_header(entries, label)
    rows = tuple(_require_aligned(entries[1:], len(header), spec.sep, label))
    return header, rows


def _column_index(header: tuple[str, ...], role: str, name: str, label: str) -> int:
    """The header position of one named column, or the teaching that
    names what the artifact's header actually carries."""
    if name not in header:
        carried = ", ".join(repr(cell) for cell in header) or "no columns"
        raise ValueError(
            f"core.chart: parameter {role!r} names column {name!r}, but "
            f"artifact {label} carries the columns {carried} — fix the "
            "name, or the artifact"
        )
    return header.index(name)


def _numeric_values(
    rows: tuple[tuple[str, ...], ...],
    index: int,
    role: str,
    name: str,
    label: str,
) -> list[float]:
    """One column's cells as finite floats, or the data-time
    teaching: the author's column choice measured against the
    artifact's own values, the first offender named with its row."""

    def _teach(cell: str, position: int) -> ValueError:
        return ValueError(
            f"core.chart: parameter {role!r} names column {name!r}, "
            f"but artifact {label} carries {cell!r} at row {position} "
            f"— {role} needs numbers; point it at a numeric column, or "
            "fix the artifact"
        )

    values: list[float] = []
    for position, row in enumerate(rows, start=1):
        cell = row[index]
        try:
            value = float(cell)
        except ValueError:
            raise _teach(cell, position) from None
        if not math.isfinite(value):
            raise _teach(cell, position)
        values.append(value)
    return values


def _positive_for_log(values: list[float], axis: str, name: str, label: str) -> None:
    """Refuse a nonpositive value on a log axis, naming the first
    offender — Plotly would silently drop the point, and the report
    does not quietly lose data."""
    for position, value in enumerate(values, start=1):
        if value <= 0:
            raise ValueError(
                f"core.chart: 'log_{axis}' needs positive {name!r} "
                f"values, but artifact {label} carries {value} at row "
                f"{position} — Plotly silently drops nonpositive points "
                f"on log axes; fix the data, or drop 'log_{axis}'"
            )


@dataclass(frozen=True, slots=True)
class _TraceData:
    """One plotly trace's worth of prepared data: its legend name
    (``None`` for a single-trace figure), its x cells (``None``
    when the chart has no x axis — a hue-grouped box plot), and its
    y values (``None`` for histograms, whose y is the count).

    The uniform shape lets :func:`_make_figure` branch on chart
    type alone: every grouping decision is already made here, in
    pure Python, before Plotly is imported.
    """

    name: str | None
    xs: list[str] | None
    ys: list[float] | None


def _resolve_single_color(theme: Theme, raw: JsonValue) -> ColorHex:
    """One color request — a theme token or a series entry — to
    hex: the resolution grammar core.kpi established, reused."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(
            f"core.chart: 'color' must be a theme color token (e.g. "
            f"'primary') or a series entry like 'series-1', got {raw!r}"
        )
    match = _SERIES_COLOR_PATTERN.fullmatch(raw)
    if match is not None:
        index = int(match.group(1))
        if not 1 <= index <= len(theme.series):
            raise ValueError(
                f"core.chart: 'color' names {raw!r}, but this theme's "
                f"series palette has {len(theme.series)} colors "
                f"(valid: series-1 to series-{len(theme.series)})"
            )
        return theme.series[index - 1]
    if raw in theme.colors:
        return theme.colors[raw]
    available = ", ".join(sorted(theme.colors))
    raise ValueError(
        f"core.chart: 'color' must be a theme token this theme "
        f"declares ({available}) or a series entry like 'series-1', "
        f"got {raw!r}"
    )


def _chart_data(
    theme: Theme,
    spec: _ChartSpec,
    header: tuple[str, ...],
    rows: tuple[tuple[str, ...], ...],
) -> tuple[list[_TraceData], int, str | None]:
    """Prepare the plot's data: resolve the columns against the
    header's own vocabulary, validate the numeric columns, group
    under hue in first-appearance order — the producer's order is
    the story.

    The data-time teachings fire here: column membership, numeric
    cells, log-axis positivity — each naming the artifact's own
    values.  Returns one :class:`_TraceData` per trace, the record
    count for the inferred description, and the hue-wrap note when
    the groups outnumber the theme's series palette (``None``
    otherwise).
    """
    label = spec.artifact_type
    x_index = _column_index(header, "x", spec.x, label) if spec.x is not None else None
    y_index = _column_index(header, "y", spec.y, label) if spec.y is not None else None
    hue_index = (
        _column_index(header, "hue", spec.hue, label) if spec.hue is not None else None
    )
    groups = (
        list(dict.fromkeys(row[hue_index] for row in rows))
        if hue_index is not None
        else []
    )
    traces: list[_TraceData] = []
    if spec.chart == "histogram":
        assert x_index is not None and spec.x is not None  # guaranteed by _parse_spec
        values = _numeric_values(rows, x_index, "x", spec.x, label)
        if spec.log_x:
            _positive_for_log(values, "x", spec.x, label)
        if hue_index is not None:
            traces = [
                _TraceData(
                    name=group,
                    xs=[row[x_index] for row in rows if row[hue_index] == group],
                    ys=None,
                )
                for group in groups
            ]
        else:
            traces = [_TraceData(name=None, xs=[row[x_index] for row in rows], ys=None)]
    elif spec.chart == "box":
        assert y_index is not None and spec.y is not None  # guaranteed by _parse_spec
        values = _numeric_values(rows, y_index, "y", spec.y, label)
        if spec.log_y:
            _positive_for_log(values, "y", spec.y, label)
        if hue_index is not None:
            traces = [
                _TraceData(
                    name=group,
                    xs=None,
                    ys=[float(row[y_index]) for row in rows if row[hue_index] == group],
                )
                for group in groups
            ]
        elif x_index is not None:
            traces = [
                _TraceData(name=None, xs=[row[x_index] for row in rows], ys=values)
            ]
        else:
            traces = [_TraceData(name=None, xs=None, ys=values)]
    else:
        assert (  # guaranteed by _parse_spec
            x_index is not None
            and spec.x is not None
            and y_index is not None
            and spec.y is not None
        )
        ys = _numeric_values(rows, y_index, "y", spec.y, label)
        if spec.log_y:
            _positive_for_log(ys, "y", spec.y, label)
        if spec.log_x:
            _positive_for_log(
                _numeric_values(rows, x_index, "x", spec.x, label),
                "x",
                spec.x,
                label,
            )
        if hue_index is not None:
            traces = [
                _TraceData(
                    name=group,
                    xs=[row[x_index] for row in rows if row[hue_index] == group],
                    ys=[float(row[y_index]) for row in rows if row[hue_index] == group],
                )
                for group in groups
            ]
        else:
            traces = [_TraceData(name=None, xs=[row[x_index] for row in rows], ys=ys)]
    note = None
    if hue_index is not None and len(traces) > len(theme.series):
        note = (
            f"the chart of artifact {spec.artifact_type!r} colors "
            f"{len(traces)} '{spec.hue}' groups from the theme's "
            f"{len(theme.series)}-color series palette, so the colors "
            "cycle — add colors to the theme's 'series' if the report "
            "needs distinct colors"
        )
    return traces, len(rows), note


def _make_figure(
    theme: Theme, spec: _ChartSpec, traces: list[_TraceData]
) -> SupportsToHtml:
    """Assemble the theme-dressed Plotly figure from the prepared
    traces: colors from the theme (series-cycled under hue; the
    resolved token or ``series-1`` without), transparent
    backgrounds so the card's surface shows through, the theme's
    font and computed ink, grid at the theme's border color, and
    axis titles from the column names — the data's own vocabulary.

    Plotly is imported here, inside the render call: a chartless
    report builds on machines without it, and a placement that
    meets its absence teaches the fix as the environment failure
    it is.
    """
    try:
        import plotly.graph_objects as go
    except ImportError as e:
        raise RenderError(
            "core.chart renders figures with the plotly package, "
            "which is not installed (or cannot be imported) — "
            "install plotly and build again"
        ) from e
    if spec.hue is not None:
        colors = [theme.series[i % len(theme.series)] for i in range(len(traces))]
    else:
        single = (
            theme.series[0]
            if spec.color is None
            else _resolve_color("core.chart", theme, spec.color)
        )
        colors = [single] * len(traces)
    figure = go.Figure()
    for color, trace in zip(colors, traces, strict=True):
        if spec.chart == "scatter":
            figure.add_trace(
                go.Scatter(
                    x=trace.xs,
                    y=trace.ys,
                    mode="markers",
                    name=trace.name,
                    marker={"color": color},
                )
            )
        elif spec.chart == "line":
            figure.add_trace(
                go.Scatter(
                    x=trace.xs,
                    y=trace.ys,
                    mode="lines+markers",
                    name=trace.name,
                    marker={"color": color},
                    line={"color": color},
                )
            )
        elif spec.chart == "bar":
            figure.add_trace(
                go.Bar(
                    x=trace.xs,
                    y=trace.ys,
                    name=trace.name,
                    marker={"color": color},
                )
            )
        elif spec.chart == "histogram":
            figure.add_trace(
                go.Histogram(
                    x=trace.xs,
                    name=trace.name,
                    marker={"color": color},
                    opacity=0.75 if spec.hue is not None else 1.0,
                )
            )
        else:  # box
            figure.add_trace(
                go.Box(
                    x=trace.xs,
                    y=trace.ys,
                    name=trace.name,
                    marker={"color": color},
                    line={"color": color},
                )
            )
    ink = theme.text_on(theme.colors["surface"])
    border = theme.colors["border"]
    xaxis: dict[str, object] = {
        "showgrid": spec.grid,
        "gridcolor": border,
        "zerolinecolor": border,
    }
    if spec.x is not None:
        xaxis["title"] = {"text": spec.x}
    if spec.log_x:
        xaxis["type"] = "log"
    yaxis: dict[str, object] = {
        "showgrid": spec.grid,
        "gridcolor": border,
        "zerolinecolor": border,
    }
    yaxis["title"] = {"text": "count" if spec.chart == "histogram" else spec.y}
    if spec.log_y:
        yaxis["type"] = "log"
    figure.update_layout(
        paper_bgcolor="rgba(0, 0, 0, 0)",
        plot_bgcolor="rgba(0, 0, 0, 0)",
        font={"family": theme.font_body, "color": ink},
        showlegend=spec.hue is not None,
        xaxis=xaxis,
        yaxis=yaxis,
    )
    # Plotly ships no type markers, so its Figure is Any to mypy; the
    # cast documents the trust at the contract boundary — the figure
    # satisfies SupportsToHtml by construction, and from_figure
    # consumes only that protocol.
    return cast(SupportsToHtml, figure)


def _describe(spec: _ChartSpec, records: int) -> str:
    """The figure's accessibility label, inferred from the figure's
    own facts — chart type, subject, size, grouping — the
    framework-owned bar, met by construction: the layout author
    never writes it.

    The hue clause rides every colored figure; a box plot's
    grouping clause names whichever column groups it, ``x`` or
    ``hue``.
    """
    colored = f", colored by {spec.hue}" if spec.hue is not None else ""
    if spec.chart == "scatter":
        return f"Scatter plot of {spec.y} against {spec.x}, {records} points{colored}"
    if spec.chart == "line":
        return f"Line chart of {spec.y} against {spec.x}, {records} points{colored}"
    if spec.chart == "bar":
        return f"Bar chart of {spec.y} by {spec.x}, {records} bars{colored}"
    if spec.chart == "histogram":
        return f"Histogram of {spec.x}, {records} records{colored}"
    group = spec.x if spec.x is not None else spec.hue
    by = f" by {group}" if group is not None else ""
    return f"Box plot of {spec.y}{by}, {records} records"


def render_chart(
    context: RenderContext,
    _info: PlacementInfo,
    parameters: ComponentParameters,
) -> RenderedComponent:
    """Render one figure: data from the store through the tabular
    grammar, shape policy from the layout, colors from the theme —
    the figure body alone, because core.chart is a CARD component
    and the framework paints the card, the placement's resolved
    title included.

    The orchestrator sequences the stories: parse the placement's
    parameters (:func:`_parse_spec`), read the tabular artifact
    (:func:`_read_tabular`), convert missing data and zero data
    rows to the unavailable notice, prepare the chart's data
    (:func:`_chart_data`), assemble the figure (:func:`_make_figure`
    — Plotly imported inside this call), and return through
    :meth:`RenderedComponent.from_figure` with the inferred
    accessibility label (:func:`_describe`), the caption appended
    after the figure's marker div, and the hue-wrap note riding
    the notes channel.
    """
    spec = _parse_spec(parameters)
    try:
        header, rows = _read_tabular(context, spec)
    except ArtifactUnavailableError as e:
        return RenderedComponent.unavailable(str(e))
    if not rows:
        return RenderedComponent.unavailable(
            f"core.chart: artifact {spec.artifact_type!r} carries a "
            "header but no data rows — nothing to plot; a chart "
            "needs at least one row of data"
        )
    traces, records, note = _chart_data(context.theme, spec, header, rows)
    figure = _make_figure(context.theme, spec, traces)
    outcome = RenderedComponent.from_figure(
        figure, description=_describe(spec, records)
    )
    caption_html = (
        f'<p class="coda-chart__caption">{html.escape(spec.caption)}</p>'
        if spec.caption is not None
        else ""
    )
    assert outcome.html is not None  # OK outcomes always carry html
    return replace(
        outcome,
        html=outcome.html + caption_html,
        notes=(note,) if note is not None else (),
    )
