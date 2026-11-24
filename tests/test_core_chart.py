"""Tests for the chart component: one core.tabular artifact as a
theme-dressed Plotly figure.

The families, byte-pinned: the parse family (shape, the closed
vocabulary, per-chart consistency — all before any data is touched),
the data-time family (column membership, numeric cells, log-axis
positivity — taught against the artifact's own values), the
unavailable family (missing data and zero rows — facts about the
run), and the figure family (real Plotly output: trace types and
modes, hue grouping in first-appearance order, series-cycled
colors, theme dressing, the inferred accessibility label).

Palette pins derive from the default theme, never byte-hardcoded:
a theme edit is never a test sweep."""

import json
import sys
from pathlib import Path
from typing import Any, Final

import pytest
from factories import make_manifest_payload

from workflow_coda.artifact_store import ArtifactStore
from workflow_coda.components import ComponentStatus, PlacementInfo, RenderedComponent
from workflow_coda.context import RenderContext
from workflow_coda.core.chart import render_chart
from workflow_coda.errors import ArtifactReadError, RenderError
from workflow_coda.icons import IconLibrary
from workflow_coda.theme import DEFAULT_THEME, DEFAULT_THEME_PAIR

_SAMPLES: Final[str] = (
    "sample_id\tdepth\tstatus\nS1\t9\tpassed\nS2\t100\tfailed\nS3\t10\tpassed\n"
)
"""The main tabular artifact: three samples, two statuses, one
numeric column — the table the happy paths plot."""

_MIXED: Final[str] = "sample_id\tdepth\tstatus\nS1\t9\tpassed\nS2\tshallow\tfailed\n"
"""A depth column carrying a text cell — the numeric-ness
teaching's trigger, the offender at data row 2."""

_ZEROED: Final[str] = "sample_id\tdepth\treads\nS1\t9\t100\nS2\t0\t50\n"
"""A zero depth beside positive reads — the log-axis positivity
teaching's trigger from both directions: y=depth with log_y, and
x=depth with log_x."""

_NONFINITE: Final[str] = "sample_id\tdepth\treads\nS1\tinf\tnan\n"
"""Infinite and not-a-number, one word-form per column — each the
only cell of its own column, so each parametrized case meets its
own first offender: numeric-shaped words about data, not data."""

_RAGGED: Final[str] = "sample_id\tdepth\nS1\n"
"""A two-column header over a one-field row — the tabular grammar's
ragged-row shape lie, taught through the shared helpers."""

_EMPTY: Final[str] = "sample_id\tdepth\tstatus\n"
"""A header with no data rows — valid shape, nothing to plot: the
unavailable family's chart-owned member."""

_CSV: Final[str] = "sample_id,depth\nS1,9\nS2,100\n"
"""The same shape, comma-separated — the sep policy; the .txt name
pins that the format claim, never the extension, governs."""

_STATS: Final[str] = '{"depth": 12.4}'
"""A JSON artifact — the format-claim teaching's trigger."""


def _initial_figure(page: str) -> tuple[list[Any], dict[str, Any]]:
    """Decode the initial Plotly data and layout, not theme metadata."""
    start = page.index("Plotly.newPlot(")
    arguments = page[page.index(",", start) + 1 :].lstrip()
    decoder = json.JSONDecoder()

    data, end = decoder.raw_decode(arguments)
    arguments = arguments[end:].lstrip()
    assert arguments.startswith(",")
    layout, _ = decoder.raw_decode(arguments[1:].lstrip())

    assert isinstance(data, list)
    assert isinstance(layout, dict)
    return data, layout


def _groups_text() -> str:
    """The hue-wrap artifact, derived from the theme: one more
    group than the series palette carries, so the cyclic wrap —
    the last trace wears series-1 again — is a fact about the
    palette's length, never a coincidence of the fixture.  Series
    bounds derive from the theme; a theme edit is never a test
    sweep."""
    count = len(DEFAULT_THEME.series) + 1
    lines = ["sample_id\tdepth\tbatch"]
    lines += [f"S{i}\t{i}\tb{i}" for i in range(1, count + 1)]
    return "\n".join(lines) + "\n"


def _artifact(
    type_: str, path: str, format_: str, *, status: str = "complete"
) -> dict[str, str]:
    """One artifact declaration per the manifest's wire grammar; the
    id is the type's last segment — unique because the types are."""
    return {
        "id": type_.rpartition(".")[2],
        "type": type_,
        "schema_version": "1.0",
        "path": path,
        "format": format_,
        "status": status,
    }


def _write_bundle(tmp_path: Path) -> Path:
    """The chart bundle: one manifest declaring the suite's ten
    artifacts beside their files — the tabular set the chart reads,
    plus the JSON and failed pair that teach the format claim and
    the unavailable family.  Returns the bundle directory."""
    payload = make_manifest_payload()
    payload["artifacts"] = [
        _artifact("org.example.samples", "samples.tsv", "core.tabular"),
        _artifact("org.example.mixed", "mixed.tsv", "core.tabular"),
        _artifact("org.example.zeroed", "zeroed.tsv", "core.tabular"),
        _artifact("org.example.nonfinite", "nonfinite.tsv", "core.tabular"),
        _artifact("org.example.ragged", "ragged.tsv", "core.tabular"),
        _artifact("org.example.groups", "groups.tsv", "core.tabular"),
        _artifact("org.example.empty", "empty.tsv", "core.tabular"),
        _artifact("org.example.csv", "csv.txt", "core.tabular"),
        _artifact("org.example.stats", "stats.json", "json"),
        _artifact("org.example.failed", "failed.tsv", "core.tabular", status="failed"),
    ]
    (tmp_path / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    for name, content in {
        "samples.tsv": _SAMPLES,
        "mixed.tsv": _MIXED,
        "zeroed.tsv": _ZEROED,
        "nonfinite.tsv": _NONFINITE,
        "ragged.tsv": _RAGGED,
        "groups.tsv": _groups_text(),
        "empty.tsv": _EMPTY,
        "csv.txt": _CSV,
        "stats.json": _STATS,
        "failed.tsv": _SAMPLES,  # never read: the failed status teaches first
    }.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    return tmp_path


def _context(bundle: Path) -> RenderContext:
    """The render context over one written bundle: the store rooted
    at the manifest file (its directory holds the artifact files),
    the default theme — every palette pin in the suite derives
    from it — and an empty icon library, because core.chart never
    loads icons and the suite's subject stays the chart."""
    return RenderContext(
        store=ArtifactStore.from_manifest_file(bundle / "manifest.json"),
        theme=DEFAULT_THEME_PAIR,
        icons=IconLibrary(sources=()),
    )


def _info() -> PlacementInfo:
    """The placement's resolved facts; the chart ignores the title
    (CARD chrome — the framework paints it), so any title serves."""
    return PlacementInfo(title="Depth by sample")


def _render(context: RenderContext, parameters: dict[str, Any]) -> RenderedComponent:
    """Render one chart placement from a plain parameter dict."""
    return render_chart(context, _info(), parameters)


def _html(context: RenderContext, parameters: dict[str, Any]) -> str:
    """Render and require OK: the html body of a healthy figure."""
    outcome = _render(context, parameters)
    assert outcome.status is ComponentStatus.OK
    assert outcome.html is not None
    return outcome.html


_BAR: Final[dict[str, Any]] = {
    "artifact": "org.example.samples",
    "chart": "bar",
    "x": "sample_id",
    "y": "depth",
}
"""The minimal healthy bar placement: the samples artifact, one bar
per sample, no hue — the base most tests derive from with ``|``."""


# ---------------------------------------------------------------------------
# The parse family: shape and consistency, before any data
# ---------------------------------------------------------------------------


def test_chart_is_required(tmp_path: Path) -> None:
    # No honest default exists for the plot type: the placement
    # names it, and 'chart' teaches before anything else.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="parameter 'chart' is required"):
        _render(context, {"artifact": "org.example.samples"})


def test_chart_must_be_text(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="'chart' must be a non-empty string"):
        _render(context, _BAR | {"chart": 5})


def test_chart_vocabulary_is_closed(tmp_path: Path) -> None:
    # The five generally useful types, listed in the teaching.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(
        ValueError,
        match="must be one of 'bar', 'box', 'histogram', 'line', 'scatter'",
    ):
        _render(context, _BAR | {"chart": "pie"})


def test_artifact_is_required(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="parameter 'artifact' is required"):
        _render(context, {"chart": "bar", "x": "sample_id", "y": "depth"})


def test_unknown_parameter_teaches_with_suggestion(tmp_path: Path) -> None:
    # The closed vocabulary teaches at the parse boundary: a typo
    # gets its closest match.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="did you mean 'color'"):
        _render(context, _BAR | {"colr": "primary"})


def test_placement_keys_teach_the_move(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="placement key, not a component parameter"):
        _render(context, _BAR | {"title": "Depth"})


def test_histogram_refuses_y(tmp_path: Path) -> None:
    # A histogram bins 'x' and counts the records — its y is the
    # count, and declaring one is a shape mistake, not data.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="its y is the count"):
        _render(context, _BAR | {"chart": "histogram", "x": "depth"})


def test_histogram_requires_x(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="'x' is required for a histogram"):
        _render(context, {"artifact": "org.example.samples", "chart": "histogram"})


def test_box_requires_y(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="'y' is required for a box plot"):
        _render(context, {"artifact": "org.example.samples", "chart": "box"})


def test_box_groups_by_one_column(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="'x' or 'hue', not both"):
        _render(context, _BAR | {"chart": "box", "hue": "status"})


def test_box_refuses_log_x(tmp_path: Path) -> None:
    # A box plot's horizontal axis is categorical grouping; the log
    # transform belongs to the values.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="drop 'log_x'"):
        _render(context, _BAR | {"chart": "box", "log_x": True})


@pytest.mark.parametrize("chart", ["scatter", "line", "bar"])
def test_x_and_y_are_required(tmp_path: Path, chart: str) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(
        ValueError, match=f"'x' and 'y' are required for a {chart} chart"
    ):
        _render(context, {"artifact": "org.example.samples", "chart": chart})


def test_hue_owns_the_color_story(tmp_path: Path) -> None:
    # Hue groups the records into series-colored traces; a single
    # color and a grouping are two different figures.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="remove 'color', or replace 'hue'"):
        _render(context, _BAR | {"hue": "status", "color": "primary"})


def test_grid_must_be_boolean(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="'grid', when given, must be a boolean"):
        _render(context, _BAR | {"grid": "yes"})


def test_log_axes_must_be_boolean(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="'log_x', when given, must be a boolean"):
        _render(context, _BAR | {"log_x": "true"})


def test_sep_must_be_one_character(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="must be a single character"):
        _render(context, _BAR | {"sep": "::"})


def test_text_parameters_must_be_nonempty(tmp_path: Path) -> None:
    # Whitespace-only is always an authoring mistake — the visible-
    # text house rule, parameter edition; and a non-string teaches
    # the same lesson.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="'x', when given, must be a non-empty string"):
        _render(context, _BAR | {"x": "  "})
    with pytest.raises(
        ValueError, match="'caption', when given, must be a non-empty string"
    ):
        _render(context, _BAR | {"caption": 12})


# ---------------------------------------------------------------------------
# The data-time family: taught against the artifact's own values
# ---------------------------------------------------------------------------


def test_unknown_column_teaches_against_the_header(tmp_path: Path) -> None:
    # Column membership is a data-time judgment: the teaching names
    # the column the author asked for and what the header actually
    # carries — the same vocabulary lesson for x and y alike.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="names column 'sample', but artifact"):
        _render(context, _BAR | {"x": "sample"})
    with pytest.raises(
        ValueError, match="carries the columns 'sample_id', 'depth', 'status'"
    ):
        _render(context, _BAR | {"y": "depths"})


def test_text_cell_teaches_with_the_row(tmp_path: Path) -> None:
    # The numeric teaching names the first offender — the cell and
    # its data row — against the mixed artifact's shallow cell.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(
        ValueError, match="carries 'shallow' at row 2 — y needs numbers"
    ):
        _render(context, _BAR | {"artifact": "org.example.mixed"})


@pytest.mark.parametrize(("cell", "column"), [("inf", "depth"), ("nan", "reads")])
def test_nonfinite_cells_are_words_not_data(
    tmp_path: Path, cell: str, column: str
) -> None:
    # Numeric-shaped but not finite: in this domain they are words
    # about data, and the numeric teaching refuses them exactly as
    # it refuses text — the finite branch, same message.  One
    # word-form per column, each the first offender of its own.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match=f"carries {cell!r} at row"):
        _render(context, _BAR | {"artifact": "org.example.nonfinite", "y": column})


def test_log_y_refuses_nonpositive_values(tmp_path: Path) -> None:
    # Plotly silently drops nonpositive points on log axes — the
    # quiet data disappearance this framework refuses: the first
    # offender named, and the fix offered both ways.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(
        ValueError,
        match="'log_y' needs positive 'depth' values.*fix the data, or drop 'log_y'",
    ):
        _render(context, _BAR | {"artifact": "org.example.zeroed", "log_y": True})


def test_log_x_refuses_nonpositive_values(tmp_path: Path) -> None:
    # Both chart families that bin or plot x values guard the log
    # axis: scatter's x and the histogram's x teach identically.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="'log_x' needs positive 'depth' values"):
        _render(
            context,
            {
                "artifact": "org.example.zeroed",
                "chart": "scatter",
                "x": "depth",
                "y": "reads",
                "log_x": True,
            },
        )
    with pytest.raises(ValueError, match="'log_x' needs positive 'depth' values"):
        _render(
            context,
            {
                "artifact": "org.example.zeroed",
                "chart": "histogram",
                "x": "depth",
                "log_x": True,
            },
        )


# ---------------------------------------------------------------------------
# The unavailable family: missing data is a fact about the run
# ---------------------------------------------------------------------------


def test_undeclared_artifact_is_unavailable(tmp_path: Path) -> None:
    # The store's own message rides the notice — the chart adds
    # nothing, because the fact is the store's to tell.
    context = _context(_write_bundle(tmp_path))
    outcome = _render(context, _BAR | {"artifact": "org.example.absent"})
    assert outcome.status is ComponentStatus.UNAVAILABLE
    assert outcome.message is not None
    assert "declares no artifact of type 'org.example.absent'" in outcome.message


def test_failed_artifact_is_unavailable(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    outcome = _render(context, _BAR | {"artifact": "org.example.failed"})
    assert outcome.status is ComponentStatus.UNAVAILABLE
    assert outcome.message is not None
    assert "status 'failed'" in outcome.message


def test_zero_rows_render_the_unavailable_notice(tmp_path: Path) -> None:
    # A header with no data rows is valid shape — the chart's own
    # unavailable, not a shape lie: the artifact carried nothing to
    # plot, and the notice says what the placement needs.  The
    # outcome carries no content and no notes, per the contract.
    context = _context(_write_bundle(tmp_path))
    outcome = _render(context, _BAR | {"artifact": "org.example.empty"})
    assert outcome.status is ComponentStatus.UNAVAILABLE
    assert outcome.message is not None
    assert "header but no data rows" in outcome.message
    assert "at least one row of data" in outcome.message
    assert outcome.html is None
    assert outcome.notes == ()


# ---------------------------------------------------------------------------
# The format claim: core.tabular, read through the shared grammar
# ---------------------------------------------------------------------------


def test_non_tabular_artifact_teaches_the_format_claim(tmp_path: Path) -> None:
    # A JSON artifact is a layout mistake, not missing data: the
    # teaching names what the artifact has and what the chart reads.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(
        ValueError, match="has format 'json'; core.chart reads 'core.tabular'-format"
    ):
        _render(context, _BAR | {"artifact": "org.example.stats"})


def test_ragged_rows_teach_as_the_shape_lie(tmp_path: Path) -> None:
    # The shared grammar's ArtifactReadError flows through the
    # second reader unchanged — the producer lying about the
    # artifact's shape, a plugin failure, never a quiet notice; the
    # one-field row names the wrong-sep suspicion.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ArtifactReadError, match="1 field, expected 2.*is sep"):
        _render(context, _BAR | {"artifact": "org.example.ragged"})


def test_sep_reads_comma_separated_files(tmp_path: Path) -> None:
    # The format claim governs, never the file extension: the .txt
    # file renders under its declared separator, the rows reaching
    # the figure.
    context = _context(_write_bundle(tmp_path))
    page = _html(
        context,
        {
            "artifact": "org.example.csv",
            "chart": "bar",
            "x": "sample_id",
            "y": "depth",
            "sep": ",",
        },
    )
    assert "S1" in page
    assert "S2" in page


# ---------------------------------------------------------------------------
# The figure family: real Plotly output, dressed from the theme
# ---------------------------------------------------------------------------


def test_renders_the_figure_marker_and_bootstrap(tmp_path: Path) -> None:
    # The embedding contract in one place: the framework's figure
    # marker div, plotly's own bootstrap script (no bundled library
    # — the page loads Plotly.js once), the responsive config, and
    # a healthy figure's silence on the notes channel.
    context = _context(_write_bundle(tmp_path))
    outcome = _render(context, _BAR)
    assert outcome.status is ComponentStatus.OK
    assert outcome.notes == ()
    assert outcome.html is not None
    assert 'class="coda-figure"' in outcome.html
    assert "Plotly.newPlot" in outcome.html
    assert '"responsive": true' in outcome.html


def test_trace_modes_match_the_chart_types(tmp_path: Path) -> None:
    # Scatter draws points only; a line draws points *and* the
    # connection between them — the points are data too.  The
    # figure JSON rides plotly's compact separators (only the
    # config argument is default-spaced), so the shape pins are
    # compact.
    context = _context(_write_bundle(tmp_path))
    scatter = _html(context, _BAR | {"chart": "scatter"})
    assert '"mode":"markers"' in scatter
    assert "lines+markers" not in scatter
    assert '"type":"scatter"' in scatter
    line = _html(context, _BAR | {"chart": "line"})
    assert '"mode":"lines+markers"' in line
    assert '"type":"bar"' in _html(context, _BAR)


def test_hue_groups_traces_in_first_appearance_order(tmp_path: Path) -> None:
    # One trace per distinct hue value, colored from the series
    # palette in first-appearance order — passed appears before
    # failed because S1 passed — with the legend telling the story.
    context = _context(_write_bundle(tmp_path))
    page = _html(context, _BAR | {"hue": "status"})
    assert DEFAULT_THEME.series[0] in page
    assert DEFAULT_THEME.series[1] in page
    assert page.index('"passed"') < page.index('"failed"')
    assert '"showlegend":true' in page


def test_hue_wrap_cycles_and_notes_the_ledger(tmp_path: Path) -> None:
    # One more group than the palette carries: the last trace wears
    # series-1 again, and the wrap note rides the notes channel —
    # teaching for the reader, byte-pinned against the derived
    # count.
    count = len(DEFAULT_THEME.series) + 1
    context = _context(_write_bundle(tmp_path))
    outcome = _render(
        context,
        {
            "artifact": "org.example.groups",
            "chart": "bar",
            "x": "sample_id",
            "y": "depth",
            "hue": "batch",
        },
    )
    assert outcome.status is ComponentStatus.OK
    assert outcome.notes == (
        f"the chart of artifact 'org.example.groups' colors {count} "
        f"'batch' groups from the theme's {len(DEFAULT_THEME.series)}-color "
        "series palette, so the colors cycle — add colors to the theme's "
        "'series' if the report needs distinct colors",
    )
    assert outcome.html is not None
    traces, _ = _initial_figure(outcome.html)
    colors = [trace["marker"]["color"] for trace in traces]
    assert colors == [
        DEFAULT_THEME.series[index % len(DEFAULT_THEME.series)]
        for index in range(count)
    ]
    assert (
        f'aria-label="Bar chart of depth by sample_id, {count} bars, '
        'colored by batch"' in outcome.html
    )


def test_explicit_color_uses_the_theme_grammar(tmp_path: Path) -> None:
    # Without hue, one color story: a theme token or a series
    # entry, resolved to the theme's own hex — never a literal.
    context = _context(_write_bundle(tmp_path))
    assert DEFAULT_THEME.colors["primary"] in _html(
        context, _BAR | {"color": "primary"}
    )
    assert DEFAULT_THEME.series[1] in _html(context, _BAR | {"color": "series-2"})
    with pytest.raises(ValueError, match="must be a theme color token"):
        _render(context, _BAR | {"color": 5})
    with pytest.raises(ValueError, match="series palette has"):
        _render(context, _BAR | {"color": f"series-{len(DEFAULT_THEME.series) + 1}"})
    with pytest.raises(ValueError, match="must be a theme token this theme declares"):
        _render(context, _BAR | {"color": "chartreuse"})


def test_the_figure_wears_the_theme(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    page = _html(context, _BAR | {"chart": "scatter"})
    _, layout = _initial_figure(page)
    theme = DEFAULT_THEME_PAIR.light

    assert layout["paper_bgcolor"] == "rgba(0, 0, 0, 0)"
    assert layout["plot_bgcolor"] == "rgba(0, 0, 0, 0)"
    assert layout["font"]["color"] == theme.text_on(theme.colors["surface"])
    assert layout["font"]["family"] == theme.font_body
    assert layout["xaxis"]["gridcolor"] == theme.colors["border"]
    assert layout["yaxis"]["gridcolor"] == theme.colors["border"]
    assert 'data-coda-figure-theme="' in page


def test_grid_toggle(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    assert '"showgrid":true' in _html(context, _BAR)
    assert '"showgrid":false' in _html(context, _BAR | {"grid": False})


def test_log_axes_render_the_transform(tmp_path: Path) -> None:
    # The successful log renders — the data-time teachings refuse
    # the nonpositive values; these pin the transform arriving at
    # the figure.  Exactly one log axis each: y for the bar, x for
    # the histogram.
    context = _context(_write_bundle(tmp_path))
    assert _html(context, _BAR | {"log_y": True}).count('"type":"log"') == 1
    assert (
        _html(
            context,
            {
                "artifact": "org.example.samples",
                "chart": "histogram",
                "x": "depth",
                "log_x": True,
            },
        ).count('"type":"log"')
        == 1
    )


def test_box_renders_distribution_and_grouping(tmp_path: Path) -> None:
    # A box plot distributes y; grouping is optional — a plain
    # distribution, or grouped by x with the category array riding
    # the trace.  The parameters are spelled out, never derived
    # from _BAR: the base dict carries an x, which a plain box must
    # not have — the fixture says what the test means.
    context = _context(_write_bundle(tmp_path))
    page = _html(
        context, {"artifact": "org.example.samples", "chart": "box", "y": "depth"}
    )
    assert '"type":"box"' in page
    assert 'aria-label="Box plot of depth, 3 records"' in page
    grouped = _html(
        context,
        {
            "artifact": "org.example.samples",
            "chart": "box",
            "x": "status",
            "y": "depth",
        },
    )
    assert '"type":"box"' in grouped
    assert '"passed"' in grouped  # the category array rides the trace


def test_histogram_counts_and_overlays(tmp_path: Path) -> None:
    # A histogram bins x and counts the records — its y axis is
    # titled "count" — and hue-grouped histograms overlay at
    # reduced opacity so the groups read together.
    context = _context(_write_bundle(tmp_path))
    page = _html(
        context, {"artifact": "org.example.samples", "chart": "histogram", "x": "depth"}
    )
    assert '"type":"histogram"' in page
    assert '"text":"count"' in page
    assert '"opacity":0.75' not in page
    overlay = _html(
        context,
        {
            "artifact": "org.example.samples",
            "chart": "histogram",
            "x": "depth",
            "hue": "status",
        },
    )
    assert '"opacity":0.75' in overlay


@pytest.mark.parametrize(
    ("parameters", "label"),
    [
        (
            _BAR | {"chart": "scatter"},
            "Scatter plot of depth against sample_id, 3 points",
        ),
        (_BAR | {"chart": "line"}, "Line chart of depth against sample_id, 3 points"),
        (_BAR, "Bar chart of depth by sample_id, 3 bars"),
        (
            {"artifact": "org.example.samples", "chart": "histogram", "x": "depth"},
            "Histogram of depth, 3 records",
        ),
        (
            {"artifact": "org.example.samples", "chart": "box", "y": "depth"},
            "Box plot of depth, 3 records",
        ),
        (
            {
                "artifact": "org.example.samples",
                "chart": "box",
                "x": "status",
                "y": "depth",
            },
            "Box plot of depth by status, 3 records",
        ),
        (
            {
                "artifact": "org.example.samples",
                "chart": "box",
                "y": "depth",
                "hue": "status",
            },
            "Box plot of depth by status, 3 records",
        ),
        (
            _BAR | {"hue": "status"},
            "Bar chart of depth by sample_id, 3 bars, colored by status",
        ),
    ],
)
def test_the_description_is_inferred_from_the_figure(
    tmp_path: Path, parameters: dict[str, Any], label: str
) -> None:
    # The accessibility label is the figure's own facts — type,
    # subject, size, grouping — never the author's job: pinned
    # byte-for-byte on the marker div.  The box rows spell their
    # parameters out: _BAR carries an x, which a plain box must not
    # have and a hue-grouped box must not share.
    context = _context(_write_bundle(tmp_path))
    assert f'aria-label="{label}"' in _html(context, parameters)


def test_caption_renders_under_the_figure(tmp_path: Path) -> None:
    # Author prose, escaped, after the figure's marker div — the
    # caption says what everyone should read beside the plot.
    context = _context(_write_bundle(tmp_path))
    page = _html(context, _BAR | {"caption": "Depth across samples & runs"})
    assert '<p class="coda-chart__caption">Depth across samples &amp; runs</p>' in page
    assert page.index("coda-chart__caption") > page.index('class="coda-figure"')


def test_missing_plotly_raises_the_render_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The lazy-import contract's absence branch: with the module
    # halted in sys.modules (the None-in-sys.modules import seam),
    # the render call teaches the environment failure — the fix in
    # the message, never a bare ImportError leaking through.
    context = _context(_write_bundle(tmp_path))
    monkeypatch.setitem(sys.modules, "plotly.graph_objects", None)
    with pytest.raises(RenderError, match="install plotly and build again"):
        _render(context, _BAR)
