"""Tests for the core table component: the honest-data grammar.

One artifact-backed table, exercised family by family: parse-time
shape errors (teaching ValueErrors before any data is touched),
unavailable outcomes (missing data as facts about the run), the
content-lying family (a file that does not parse under its claimed
``core.table`` format — re-homed from the store suite when the
component became the grammar's one home), the index-column
convention, the columns policy against the header's own vocabulary,
and the build-time column-type stamps the page script consumes.
The plugin assembly that ships the component is pinned in
test_core_plugin.py; the component's css and js land with the
assembly and are pinned end-to-end at the seam."""

import json
from pathlib import Path

import pytest

from workflow_coda.artifact_store import ArtifactStore, JsonValue
from workflow_coda.components import (
    ComponentParameters,
    ComponentStatus,
    PlacementInfo,
    RenderedComponent,
)
from workflow_coda.context import RenderContext
from workflow_coda.core.table import render_table
from workflow_coda.errors import ArtifactReadError
from workflow_coda.theme import DEFAULT_THEME

_TABLE_TYPE = "org.example.metrics"

_DEFAULT_TABLE: str = (
    "sample_id\tdepth\tstatus\nS1\t30.5\tpassed\nS2\t0\tfailed\nS3\t12.25\tpassed\n"
)
"""The default artifact: three columns of mixed types — a text
sample id, a numeric depth, a text status — and three rows."""

_INDEX_TABLE: str = "\tsample\tdepth\nS1\tA\t30.5\nS2\tB\t0\n"
"""The index fixture: a blank first header cell declares the first
column a row index, in-band."""


def _info(title: str = "Metrics table") -> PlacementInfo:
    """The placement info the builder hands every render call: the
    resolved instance title — unused by the CARD body, but part of
    every call's shape."""
    return PlacementInfo(title=title)


def _render(
    context: RenderContext, parameters: ComponentParameters
) -> RenderedComponent:
    """Render under the default placement info."""
    return render_table(context, _info(), parameters)


def _write_bundle(
    tmp_path: Path,
    *,
    status: str = "complete",
    fmt: str = "core.tabular",
    content: str = _DEFAULT_TABLE,
    newline: str = "\n",
) -> ArtifactStore:
    """A one-artifact manifest bundle rooted at *tmp_path*.

    The manifest and its artifact are written as real files and loaded
    through the real loader, so every fixture is a valid bundle by
    construction — the serialized factory, not a hand-built model."""
    artifact_path = tmp_path / "metrics.tsv"
    artifact_path.write_text(content, encoding="utf-8", newline=newline)
    manifest = {
        "schema_version": "0.2.0",
        "producer": {"name": "table-fixture", "version": "1.0"},
        "artifacts": [
            {
                "id": "metrics",
                "type": _TABLE_TYPE,
                "schema_version": "0.1.0",
                "path": "metrics.tsv",
                "format": fmt,
                "status": status,
            }
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return ArtifactStore.from_manifest_file(manifest_path)


def _context(store: ArtifactStore) -> RenderContext:
    """The render context for one bundle under the default theme."""
    return RenderContext(store=store, theme=DEFAULT_THEME)


def _table(overrides: ComponentParameters | None = None) -> ComponentParameters:
    """The base placement parameters, optionally overridden."""
    base: dict[str, JsonValue] = {"artifact": _TABLE_TYPE}
    if overrides is None:
        return base
    return {**base, **overrides}


def _html(context: RenderContext, parameters: ComponentParameters) -> str:
    """The rendered OK body, with the OK asserted at the call."""
    outcome = _render(context, parameters)
    assert outcome.status is ComponentStatus.OK
    assert outcome.html is not None
    return outcome.html


def _unavailable_message(
    context: RenderContext, parameters: ComponentParameters
) -> str:
    """The rendered unavailable notice, status asserted at the call."""
    outcome = _render(context, parameters)
    assert outcome.status is ComponentStatus.UNAVAILABLE
    assert outcome.message is not None
    return outcome.message


# ---------------------------------------------------------------------------
# Parse-time shape errors: teaching ValueErrors before any data is touched
# ---------------------------------------------------------------------------


def test_artifact_must_be_given(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="parameter 'artifact' is required"):
        render_table(context, _info(), {})


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("artifact", 3),
        ("artifact", True),
        ("artifact", ""),
        ("artifact", "  "),
    ],
)
def test_required_text_rejects_non_strings(
    tmp_path: Path, name: str, value: JsonValue
) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="must be a non-empty string"):
        render_table(context, _info(), {name: value})


@pytest.mark.parametrize("sep", ["", "::", 2, None])
def test_sep_must_be_a_single_character(tmp_path: Path, sep: JsonValue) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="must be a single character"):
        render_table(context, _info(), _table({"sep": sep}))


@pytest.mark.parametrize("header", ["yes", 1, "true", None])
def test_header_must_be_a_boolean(tmp_path: Path, header: JsonValue) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="must be a boolean"):
        render_table(context, _info(), _table({"header": header}))


@pytest.mark.parametrize("columns", ["depth", [], {}, 3])
def test_columns_must_be_a_non_empty_list(tmp_path: Path, columns: JsonValue) -> None:
    # Declared policy that selects nothing teaches, like the empty
    # thresholds object: it declares a policy and judges nothing.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="must be a list of column names"):
        render_table(context, _info(), _table({"columns": columns}))


@pytest.mark.parametrize(
    ("columns", "pin"),
    [
        (["depth", ""], "must list non-empty column names"),
        (["depth", "  "], "must list non-empty column names"),
        (["depth", "depth"], "names 'depth' twice"),
    ],
)
def test_column_names_teach_on_shape(
    tmp_path: Path, columns: list[JsonValue], pin: str
) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match=pin):
        render_table(context, _info(), _table({"columns": columns}))


def test_columns_needs_a_header(tmp_path: Path) -> None:
    # Positional selection would be invented vocabulary: a headerless
    # file declares position as meaning, and every column shows.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="declares header: false"):
        render_table(context, _info(), _table({"columns": ["depth"], "header": False}))


def test_parameter_typos_get_a_suggestion(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="did you mean 'columns'"):
        render_table(context, _info(), _table({"colums": ["depth"]}))
    with pytest.raises(ValueError, match="did you mean 'caption'"):
        render_table(context, _info(), _table({"captio": "note"}))


def test_placement_keys_nested_in_parameters_teach_the_move(
    tmp_path: Path,
) -> None:
    # A policy nested inside parameters is inert — the closed
    # vocabulary teaches the move rather than silently ignoring it.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(
        ValueError, match="move it out of 'parameters:' to the placement level"
    ):
        render_table(context, _info(), _table({"on_missing": "skip"}))
    with pytest.raises(ValueError, match="move it out of 'parameters:'"):
        render_table(context, _info(), _table({"title": "Metrics"}))


# ---------------------------------------------------------------------------
# The format gate: core.table's own convention, claimed in the manifest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fmt", "pin"),
    [
        ("json", "core.table reads 'core.tabular'-format artifacts"),
        ("bio.newick", "has format 'bio.newick'"),
    ],
)
def test_other_formats_are_layout_mistakes(tmp_path: Path, fmt: str, pin: str) -> None:
    # The format is a claim whose grammar lives in this component: the
    # store hands any artifact over (readers are explicit), and the
    # component teaches the move.  A core value and another namespaced
    # convention both teach, each naming the file's actual format.
    context = _context(_write_bundle(tmp_path, fmt=fmt))
    with pytest.raises(ValueError, match=pin):
        render_table(context, _info(), _table())


# ---------------------------------------------------------------------------
# Missing data: unavailable outcomes, carrying the store's own messages
# ---------------------------------------------------------------------------


def test_undeclared_artifact_renders_unavailable(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    message = _unavailable_message(context, _table({"artifact": "org.example.absent"}))
    assert "manifest declares no artifact" in message


def test_incomplete_artifact_renders_unavailable(tmp_path: Path) -> None:
    # A partial run's declaration is a fact about the run, not a bug
    # in the report.
    context = _context(_write_bundle(tmp_path, status="failed"))
    message = _unavailable_message(context, _table())
    assert "declared with status 'failed'" in message


def test_missing_artifact_file_renders_unavailable(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    (tmp_path / "metrics.tsv").unlink()
    message = _unavailable_message(context, _table())
    assert "does not exist at" in message


# ---------------------------------------------------------------------------
# The content-lying family: a file that does not parse under its claim
# (re-homed from the store suite — core.table is the grammar's one home)
# ---------------------------------------------------------------------------


def test_empty_file_has_no_header(tmp_path: Path) -> None:
    # The artifact lying about its shape is a plugin failure the
    # builder reports — never a quiet notice: it propagates.
    context = _context(_write_bundle(tmp_path, content=""))
    with pytest.raises(ArtifactReadError, match="contains no header row"):
        render_table(context, _info(), _table())


def test_blank_only_file_has_no_header(tmp_path: Path) -> None:
    # The knowing fold from the store's grammar: blank lines skip
    # before a header exists, so a blank-only file teaches the
    # honest message — the file has no content at all.
    context = _context(_write_bundle(tmp_path, content="\n\n"))
    with pytest.raises(ArtifactReadError, match="contains no header row"):
        render_table(context, _info(), _table())


def test_empty_header_cell_beyond_the_index_teaches(tmp_path: Path) -> None:
    # Only the first cell may be blank — the in-band index-column
    # declaration; a blank cell elsewhere has no meaning.
    context = _context(_write_bundle(tmp_path, content="a\t\tb\nS1\tx\ty\n"))
    with pytest.raises(ArtifactReadError) as exc_info:
        render_table(context, _info(), _table())
    message = str(exc_info.value)
    assert "empty header column name at position 2" in message
    assert "only the first cell may be blank" in message


def test_duplicate_header_columns_teach(tmp_path: Path) -> None:
    context = _context(
        _write_bundle(tmp_path, content="sample_id\tsample_id\nS1\ttrue\n")
    )
    with pytest.raises(ArtifactReadError, match="duplicate header column 'sample_id'"):
        render_table(context, _info(), _table())


def test_short_rows_teach_with_the_delimiter_hint(tmp_path: Path) -> None:
    # A row of one field against a wider header is the wrong-sep
    # signature: the teaching names the suspect delimiter.
    context = _context(_write_bundle(tmp_path, content="a\tb\nS1\tx\nS2\n"))
    with pytest.raises(ArtifactReadError) as exc_info:
        render_table(context, _info(), _table())
    message = str(exc_info.value)
    assert "row at line 3 has 1 field, expected 2" in message
    assert "is sep" in message


def test_merely_short_rows_teach_without_the_hint(tmp_path: Path) -> None:
    # The hint fires only on the one-field signature — a genuinely
    # short row has more than one field and names no suspect.
    context = _context(_write_bundle(tmp_path, content="a\tb\tc\nS1\tx\ty\nS2\tz\n"))
    with pytest.raises(ArtifactReadError) as exc_info:
        render_table(context, _info(), _table())
    message = str(exc_info.value)
    assert "row at line 3 has 2 fields, expected 3" in message
    assert "is sep" not in message


def test_headerless_ragged_rows_teach(tmp_path: Path) -> None:
    # Width comes from the first row; later rows must match it.
    context = _context(_write_bundle(tmp_path, content="S1\t30.5\nS2\n"))
    with pytest.raises(ArtifactReadError, match="row at line 2 has 1 field"):
        render_table(context, _info(), _table({"header": False}))


def test_headerless_file_with_no_rows_teaches(tmp_path: Path) -> None:
    # Positional labels need a column count; no rows means none
    # exists.
    context = _context(_write_bundle(tmp_path, content=""))
    with pytest.raises(ArtifactReadError, match="column count is unknown"):
        render_table(context, _info(), _table({"header": False}))


def test_blank_lines_skip(tmp_path: Path) -> None:
    # Re-homed from the store suite: blank lines are not data.
    context = _context(_write_bundle(tmp_path, content="a\tb\n\nS1\tx\n\n"))
    html = _html(context, _table())
    assert "<tbody><tr><td>S1</td><td>x</td></tr></tbody>" in html


def test_crlf_line_endings_are_tolerated(tmp_path: Path) -> None:
    # Re-homed from the store suite: producers on Windows may write
    # CRLF; no '\r' leaks into cells.  (Fixtures elsewhere pin LF;
    # this test deliberately does not.)
    context = _context(_write_bundle(tmp_path, content="a\tb\nS1\tx\n", newline="\r\n"))
    html = _html(context, _table())
    assert "<td>S1</td><td>x</td>" in html
    assert "\r" not in html


def test_quoted_cells_follow_the_csv_dialect(tmp_path: Path) -> None:
    # Re-homed from the store suite: a quoted cell may carry the
    # delimiter itself.
    context = _context(_write_bundle(tmp_path, content='a\tnote\nS1\t"a\tb"\n'))
    html = _html(context, _table())
    assert "<td>a\tb</td>" in html


def test_uniform_wrong_sep_renders_one_column_until_declared(
    tmp_path: Path,
) -> None:
    # The honest boundary, pinned: a file whose delimiter is wrong
    # everywhere parses every line as one field — header included —
    # so the table is one column wide and renders misread, aligned,
    # with the header's full line as its lone label.  Parse-time
    # teaching cannot see it (nothing disagrees); the fix is declaring
    # the file's actual delimiter, and then the same artifact reads.
    context = _context(_write_bundle(tmp_path, content="sample,depth\nS1,30.5\n"))
    misread = _html(context, _table())
    assert 'data-key="sample,depth"' in misread
    fixed = _html(context, _table({"sep": ","}))
    assert 'data-key="sample"' in fixed
    assert "<td>S1</td><td>30.5</td>" in fixed


# ---------------------------------------------------------------------------
# The columns policy: membership taught where the data lives
# ---------------------------------------------------------------------------


def test_unknown_column_teaches_the_headers_vocabulary(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError) as exc_info:
        render_table(context, _info(), _table({"columns": ["depth", "middle"]}))
    message = str(exc_info.value)
    assert "names 'middle'" in message
    assert "'sample_id', 'depth', 'status'" in message


def test_columns_order_and_inclusion(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _table({"columns": ["status", "sample_id"]}))
    assert (
        '<th scope="col" data-key="status" data-type="text">status</th>'
        '<th scope="col" data-key="sample_id" data-type="text">sample_id</th>' in html
    )
    assert 'data-key="depth"' not in html  # not selected, not shown
    assert "<tr><td>passed</td><td>S1</td></tr>" in html


# ---------------------------------------------------------------------------
# The index-column convention: detected in-band, never configured
# ---------------------------------------------------------------------------


def test_blank_first_header_cell_declares_an_index(tmp_path: Path) -> None:
    # The producer's in-band declaration: a blank first header cell
    # means the first column is a row index — rendered first,
    # without a label.
    context = _context(_write_bundle(tmp_path, content=_INDEX_TABLE))
    html = _html(context, _table())
    assert '<th scope="col" data-key="" data-type="text"></th>' in html
    assert (
        '<th scope="col" data-key="sample" data-type="text">sample</th>'
        '<th scope="col" data-key="depth" data-type="numeric">depth</th>' in html
    )
    assert "<tr><td>S1</td><td>A</td><td>30.5</td></tr>" in html


def test_index_column_stays_first_under_the_columns_policy(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path, content=_INDEX_TABLE))
    html = _html(context, _table({"columns": ["depth", "sample"]}))
    assert (
        '<th scope="col" data-key="depth" data-type="numeric">depth</th>'
        '<th scope="col" data-key="sample" data-type="text">sample</th>' in html
    )
    assert "<tr><td>S1</td><td>30.5</td><td>A</td></tr>" in html


# ---------------------------------------------------------------------------
# Headerless files: position as the producer's declared meaning
# ---------------------------------------------------------------------------


def test_headerless_renders_positional_labels(tmp_path: Path) -> None:
    # A producer emitting a grid without a header declares position
    # as meaning; positional vocabulary is honest, not invented.
    context = _context(
        _write_bundle(tmp_path, content="S1\t30.5\tpassed\nS2\t0\tfailed\n")
    )
    html = _html(context, _table({"header": False}))
    assert '<th scope="col" data-key="Column 1" data-type="text">Column 1</th>' in html
    assert (
        '<th scope="col" data-key="Column 2" data-type="numeric">Column 2</th>' in html
    )
    assert '<th scope="col" data-key="Column 3" data-type="text">Column 3</th>' in html
    assert "<tr><td>S1</td><td>30.5</td><td>passed</td></tr>" in html


# ---------------------------------------------------------------------------
# Build-time column-type stamps: the fact the script consumes
# ---------------------------------------------------------------------------


def test_column_types_stamp_numeric_and_text(tmp_path: Path) -> None:
    # Stamped at build time, never re-derived at read time: numeric
    # when every non-empty cell parses as a finite number, else text.
    # The default artifact carries one column of each.
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _table())
    assert '<th scope="col" data-key="depth" data-type="numeric">depth</th>' in html
    assert (
        '<th scope="col" data-key="sample_id" data-type="text">sample_id</th>' in html
    )
    assert '<th scope="col" data-key="status" data-type="text">status</th>' in html


def test_nan_and_inf_stamp_as_text(tmp_path: Path) -> None:
    # In this domain they are words about data, not data.
    context = _context(
        _write_bundle(tmp_path, content="sample\tdepth\nS1\tnan\nS2\tinf\n")
    )
    html = _html(context, _table())
    assert '<th scope="col" data-key="depth" data-type="text">depth</th>' in html


def test_all_empty_column_stamps_text(tmp_path: Path) -> None:
    # No data seen means nothing to sort numerically: text is the
    # safe default, and the stamp stays honest.
    context = _context(_write_bundle(tmp_path, content="a\tb\nS1\t\nS2\t\n"))
    html = _html(context, _table())
    assert '<th scope="col" data-key="b" data-type="text">b</th>' in html


def test_header_only_table_renders_an_empty_body(tmp_path: Path) -> None:
    # Columns declared, no data rows — a valid table, rendered
    # honestly: the header with text stamps (no data seen), an
    # empty body.
    context = _context(_write_bundle(tmp_path, content="sample\tdepth\n"))
    html = _html(context, _table())
    assert '<th scope="col" data-key="depth" data-type="text">depth</th>' in html
    assert "<tbody></tbody>" in html


# ---------------------------------------------------------------------------
# Markup: escaping, the controls bar, the caption, the card contract
# ---------------------------------------------------------------------------


def test_cells_escape_html(tmp_path: Path) -> None:
    # Artifact-sourced text inside a data page: anything that looks
    # like markup renders as visible text.
    context = _context(
        _write_bundle(tmp_path, content="sample\tnote\nS1\t<b>bold</b>\n")
    )
    html = _html(context, _table())
    assert "&lt;b&gt;bold&lt;/b&gt;" in html


def test_header_names_escape_in_key_and_text(tmp_path: Path) -> None:
    # The stamped data-key escapes too — it is artifact-sourced like
    # the visible header text it mirrors.
    context = _context(
        _write_bundle(tmp_path, content="depth<1>\tstatus\nS1\tpassed\n")
    )
    html = _html(context, _table())
    assert 'data-key="depth&lt;1&gt;"' in html
    assert ">depth&lt;1&gt;</th>" in html


def test_caption_escapes_and_renders_under_the_table(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _table({"caption": "<i>note</i>"}))
    assert '<p class="coda-table__caption">&lt;i&gt;note&lt;/i&gt;</p>' in html
    assert html.index("coda-table__caption") > html.index("</table>")


def test_the_controls_bar_ships_in_the_markup(tmp_path: Path) -> None:
    # Display-none until the page script marks the document scripted
    # (the seam pins the gate): the DOM carries no lies — nothing
    # looks interactive that is not.
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _table())
    assert '<div class="coda-table__controls">' in html
    assert 'class="coda-table__filter"' in html
    assert 'class="coda-table__copy">Copy as TSV</button>' in html
    assert "Filter rows" in html


def test_the_card_body_carries_no_title(tmp_path: Path) -> None:
    # core.table is a CARD component: the framework paints the card
    # and the placement's resolved title; the body is the table
    # alone, and the resolved title never reaches it.
    context = _context(_write_bundle(tmp_path))
    outcome = render_table(context, PlacementInfo(title="Never rendered"), _table())
    assert outcome.status is ComponentStatus.OK
    assert outcome.html is not None
    assert "Never rendered" not in outcome.html
    assert outcome.html.startswith('<div class="coda-table">')
