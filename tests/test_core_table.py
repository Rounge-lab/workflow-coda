"""Tests for the core table component: the honest-data grammar.

One artifact-backed table, exercised family by family: parse-time
shape errors (teaching ValueErrors before any data is touched),
unavailable outcomes (missing data as facts about the run), the
content-lying family (a file that does not parse under its claimed
``core.table`` format — re-homed from the store suite when the
component became the grammar's one home), the index-column
convention, the columns policy against the header's own vocabulary,
and the build-time column-type stamps the page script consumes.

The sort-state icon stamps ride the same markup: chrome for the
scripted sort, stamped complete in every column, hidden until the
page is scripted, loaded through the build's icon library.  The
controls bar rides icons the same way — the filter field's
decorative prefix and the copy button's two stamped faces, loaded
through the build's library: chrome for the scripted enhancements.

The plugin assembly that ships the component is pinned in
test_core_plugin.py; the component's css and js land with the
assembly and are pinned end-to-end at the seam — the enhancement
script's registration census pinned here, because the page merges
every script and the seam cannot count this one's health alone.
"""

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
from workflow_coda.core.assets import read_core_asset
from workflow_coda.core.table import render_table
from workflow_coda.errors import ArtifactReadError
from workflow_coda.icons import IconLibrary, IconSource
from workflow_coda.manifest import MANIFEST_SCHEMA_VERSION
from workflow_coda.theme import DEFAULT_THEME_PAIR

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
        "schema_version": MANIFEST_SCHEMA_VERSION,
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
    """The render context for one bundle under the default theme,
    wired with the core plugin's own icon library — the same source
    the real build assembles from the plugin's declaration, because
    the table stamps its sort-state icons through the build's
    library.

    Knowing shift (sort-state icons): was — the bare context (store
    and theme; the empty icon library default), honest because the
    table read no icons; now — every healthy table loads its three
    sort-state icons through the build's library, and the empty
    default would teach a false unknown-icon error on every render;
    why — the vehicle follows the feature, the same door the
    builder wires."""
    return RenderContext(
        store=store,
        theme=DEFAULT_THEME_PAIR,
        icons=IconLibrary([IconSource.for_plugin("core", "workflow_coda.core")]),
    )


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
    # Knowing shift (sort-state icons): was — the two header cells
    # pinned byte-adjacent (…>status</th><th…>sample_id</th>); now —
    # every column label carries the sort-state stamp between it and
    # its </th>, so byte adjacency cannot survive; each label pins
    # against the stamp's opening (idle first, the stamp's state
    # order), and the position assert carries what adjacency encoded:
    # status before sample_id, the columns policy's order.
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _table({"columns": ["status", "sample_id"]}))
    assert (
        '<th scope="col" data-key="status" data-type="text">status'
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in html
    )
    assert (
        '<th scope="col" data-key="sample_id" data-type="text">sample_id'
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in html
    )
    assert html.index('data-key="status"') < html.index('data-key="sample_id"')
    assert 'data-key="depth"' not in html  # not selected, not shown
    assert "<tr><td>passed</td><td>S1</td></tr>" in html


# ---------------------------------------------------------------------------
# The index-column convention: detected in-band, never configured
# ---------------------------------------------------------------------------


def test_blank_first_header_cell_declares_an_index(tmp_path: Path) -> None:
    # The producer's in-band declaration: a blank first header cell
    # means the first column is a row index — rendered first,
    # without a label.  Knowing shift (sort-state icons): was — the
    # three header cells pinned byte-adjacent (…></th><th…); now —
    # every label carries the sort-state stamp before its </th>, so
    # each label pins against the stamp's opening — here directly
    # after the empty label — and each pin names its column, so
    # order rides the fixture's own content.
    context = _context(_write_bundle(tmp_path, content=_INDEX_TABLE))
    html = _html(context, _table())
    assert (
        '<th scope="col" data-key="" data-type="text">'
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in html
    )
    assert (
        '<th scope="col" data-key="sample" data-type="text">sample'
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in html
    )
    assert (
        '<th scope="col" data-key="depth" data-type="numeric">depth'
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in html
    )
    assert "<tr><td>S1</td><td>A</td><td>30.5</td></tr>" in html


def test_index_column_stays_first_under_the_columns_policy(tmp_path: Path) -> None:
    # Knowing shift (sort-state icons): was — the two header cells
    # pinned byte-adjacent, adjacency carrying the columns policy's
    # order; now — each label pins against the stamp's opening and
    # an index assert carries the order adjacency encoded.
    context = _context(_write_bundle(tmp_path, content=_INDEX_TABLE))
    html = _html(context, _table({"columns": ["depth", "sample"]}))
    assert (
        '<th scope="col" data-key="depth" data-type="numeric">depth'
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in html
    )
    assert (
        '<th scope="col" data-key="sample" data-type="text">sample'
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in html
    )
    assert html.index('data-key="depth"') < html.index('data-key="sample"')
    assert "<tr><td>S1</td><td>30.5</td><td>A</td></tr>" in html


# ---------------------------------------------------------------------------
# Headerless files: position as the producer's declared meaning
# ---------------------------------------------------------------------------


def test_headerless_renders_positional_labels(tmp_path: Path) -> None:
    # A producer emitting a grid without a header declares position
    # as meaning; positional vocabulary is honest, not invented.
    # Knowing shift (sort-state icons): same shift as the suite —
    # each label pins against the stamp's opening; the per-column
    # data-type stamps already name each column's position.
    context = _context(
        _write_bundle(tmp_path, content="S1\t30.5\tpassed\nS2\t0\tfailed\n")
    )
    html = _html(context, _table({"header": False}))
    assert (
        '<th scope="col" data-key="Column 1" data-type="text">Column 1'
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in html
    )
    assert (
        '<th scope="col" data-key="Column 2" data-type="numeric">Column 2'
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in html
    )
    assert (
        '<th scope="col" data-key="Column 3" data-type="text">Column 3'
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in html
    )
    assert "<tr><td>S1</td><td>30.5</td><td>passed</td></tr>" in html


# ---------------------------------------------------------------------------
# Build-time column-type stamps: the fact the script consumes
# ---------------------------------------------------------------------------


def test_column_types_stamp_numeric_and_text(tmp_path: Path) -> None:
    # Stamped at build time, never re-derived at read time: numeric
    # when every non-empty cell parses as a finite number, else text.
    # The default artifact carries one column of each.  Knowing
    # shift (sort-state icons): same shift as the suite — each label
    # pins against the stamp's opening.
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _table())
    assert (
        '<th scope="col" data-key="depth" data-type="numeric">depth'
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in html
    )
    assert (
        '<th scope="col" data-key="sample_id" data-type="text">sample_id'
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in html
    )
    assert (
        '<th scope="col" data-key="status" data-type="text">status'
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in html
    )


def test_nan_and_inf_stamp_as_text(tmp_path: Path) -> None:
    # In this domain they are words about data, not data.  Knowing
    # shift (sort-state icons): same shift as the suite.
    context = _context(
        _write_bundle(tmp_path, content="sample\tdepth\nS1\tnan\nS2\tinf\n")
    )
    html = _html(context, _table())
    assert (
        '<th scope="col" data-key="depth" data-type="text">depth'
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in html
    )


def test_all_empty_column_stamps_text(tmp_path: Path) -> None:
    # No data seen means nothing to sort numerically: text is the
    # safe default, and the stamp stays honest.  Knowing shift
    # (sort-state icons): same shift as the suite.
    context = _context(_write_bundle(tmp_path, content="a\tb\nS1\t\nS2\t\n"))
    html = _html(context, _table())
    assert (
        '<th scope="col" data-key="b" data-type="text">b'
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in html
    )


def test_header_only_table_renders_an_empty_body(tmp_path: Path) -> None:
    # Columns declared, no data rows — a valid table, rendered
    # honestly: the header with text stamps (no data seen), an
    # empty body.  Knowing shift (sort-state icons): same shift as
    # the suite.
    context = _context(_write_bundle(tmp_path, content="sample\tdepth\n"))
    html = _html(context, _table())
    assert (
        '<th scope="col" data-key="depth" data-type="text">depth'
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in html
    )
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
    # the visible header text it mirrors.  Knowing shift (sort-state
    # icons): was — the escaped label pinned against its </th>; now —
    # against the stamp's opening, which follows the escaped label.
    context = _context(
        _write_bundle(tmp_path, content="depth<1>\tstatus\nS1\tpassed\n")
    )
    html = _html(context, _table())
    assert 'data-key="depth&lt;1&gt;"' in html
    assert (
        ">depth&lt;1&gt;"
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in html
    )


def test_caption_escapes_and_renders_under_the_table(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _table({"caption": "<i>note</i>"}))
    assert '<p class="coda-table__caption">&lt;i&gt;note&lt;/i&gt;</p>' in html
    assert html.index("coda-table__caption") > html.index("</table>")


def test_the_controls_bar_ships_in_the_markup(tmp_path: Path) -> None:
    # Display-none until the page script marks the document scripted
    # (the seam pins the gate): the DOM carries no lies — nothing
    # looks interactive that is not.  Knowing shift (iconed
    # controls): was — a <label> naming the filter and a text-face
    # copy button; now — the filter's name rides aria-label with the
    # core-filter icon as its permanent decorative prefix, and the
    # copy button is a square icon button named through aria-label,
    # both faces stamped at build time: the copy icon it shows and
    # the check icon its success state swaps in — the count
    # announced from a visually hidden live region, a refusal shown
    # as text in the visible one.  The icon payloads derive from
    # the same library call the render made — like compared with
    # like.
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _table())
    filter_icon = context.icons.load("core-filter").markup
    copy_icon = context.icons.load("core-copy").markup
    check_icon = context.icons.load("core-check").markup
    assert '<div class="coda-table__controls">' in html
    assert (
        '<span class="coda-table__filter-wrap">'
        '<input type="search" class="coda-table__filter" aria-label="Filter rows">'
        f'<span class="coda-table__filter-icon">{filter_icon}</span>'
        "</span>" in html
    )
    assert (
        '<button type="button" class="coda-table__copy" aria-label="Copy as TSV">'
        f'<span class="coda-table__copy-icon">{copy_icon}</span>'
        f'<span class="coda-table__copy-check">{check_icon}</span>'
        '<span class="coda-table__copy-feedback" aria-live="polite"></span>'
        '<span class="coda-table__copy-count coda-table__sr" aria-live="polite">'
        "</span>"
        "</button>" in html
    )


def test_the_card_body_carries_no_title(tmp_path: Path) -> None:
    # core.table is a CARD component: the framework paints the card
    # and the placement's resolved title; the body is the table
    # alone, and the resolved title never reaches it.
    context = _context(_write_bundle(tmp_path))
    outcome = render_table(context, PlacementInfo(title="Never rendered"), _table())
    assert outcome.status is ComponentStatus.OK
    assert outcome.html is not None
    assert "Never rendered" not in outcome.html
    # Knowing shift: the CARD body root now stamps the default copy
    # policy; title ownership remains with the framework.
    assert outcome.html.startswith('<div class="coda-table" data-copy-rows="all">')


# ---------------------------------------------------------------------------
# The sort-state icon stamp: chrome for the scripted sort, shipped
# complete
# ---------------------------------------------------------------------------


def test_sort_state_icons_stamp_every_column(tmp_path: Path) -> None:
    # The stamp, transcribed whole: one span per state, in the fixed
    # state order, beside every column label.  The expected string
    # transcribes the landed assembly byte-for-byte — the wrapper
    # spans and the state-to-icon mapping from core's own constant —
    # with the svg payloads read through the same library door
    # production reads, so a wrong state order or a renamed icon
    # reddens as a count of zero, and a deleted shipped icon reds
    # here as the unknown-name teaching: this pin is the table's
    # roster pin for the three icons it depends on.
    context = _context(_write_bundle(tmp_path))
    stamp = "".join(
        f'<span class="coda-table__sort-icon coda-table__sort-icon--{state}">'
        f"{context.icons.load(name).markup}</span>"
        for state, name in (
            ("idle", "core-table"),
            ("ascending", "core-ascending"),
            ("descending", "core-descending"),
        )
    )
    html = _html(context, _table())
    # The census, arithmetic stated: the default artifact has 3
    # columns, so 3 identical stamps — 9 spans (3 states × 3
    # columns) — and the state class names read 9 in the markup (one
    # per span; the stylesheet is not in this body).  Knowing shift
    # (iconed controls): the svg census was 9, the stamps alone; then
    # 11 for the filter and copy icons; now 12 — the check icon
    # rides the button at build time too, its success state stamped
    # rather than fetched.
    assert html.count(stamp) == 3
    assert html.count("coda-table__sort-icon--") == 9
    assert html.count('class="coda-icon"') == 12
    # Position: the stamp rides after the label, inside the cell —
    # one column shows the contract for all.
    assert f'data-type="numeric">depth{stamp}' in html


def test_unavailable_tables_never_load_their_icons(tmp_path: Path) -> None:
    # The ordering pin: the sort-state icons load only after the
    # unavailable conversion.  Missing data is a fact about the run,
    # and a build whose icon library is empty or broken must not
    # turn an unavailable placement into a crash — the bare context
    # (the empty-library default) proves the icon door is never
    # consulted on the unavailable path.
    store = _write_bundle(tmp_path, status="failed")
    context = RenderContext(store=store, theme=DEFAULT_THEME_PAIR)
    message = _unavailable_message(context, _table())
    assert "declared with status 'failed'" in message


def test_healthy_tables_require_their_sort_icons(tmp_path: Path) -> None:
    # Design pin: no degradation on icon failure.  A build whose
    # library does not carry the table's icons — the sort states,
    # the filter, the copy, the check — must not render a healthy
    # table silently chrome-less: that would hide a broken
    # installation behind a plausible page, so the load teaches in
    # place and the builder reports it as the plugin failure it is.
    # The match names the first icon the render loads — core-table,
    # the idle state — so the pin is also the load order: sort
    # states before controls, first-offender fixtures for
    # first-offender teachings.
    store = _write_bundle(tmp_path)
    context = RenderContext(store=store, theme=DEFAULT_THEME_PAIR)
    with pytest.raises(ValueError, match="unknown icon 'core-table'"):
        _render(context, _table())


# ---------------------------------------------------------------------------
# The enhancement script's source census: registration health,
# counted where the seam cannot
# ---------------------------------------------------------------------------


def test_the_enhancement_script_registration_census() -> None:
    # The page merges every script — tab wiring, Plotly.js — so a
    # page-level census over the enhancement script's strings counts
    # authors this suite does not hold; the honest home for the
    # census is the file itself, every author held.  Each count
    # transcribes the landed source with its arithmetic stated; the
    # two splice casualties this effort shipped — a dead handler
    # left behind a replacement, a duplicate declaration — would
    # have reddened here before they shipped.
    js = read_core_asset("table.js")
    # Registrations: one header-wrap listener, one copy listener —
    # the dead-handler casualty read 3.
    assert js.count('addEventListener("click"') == 2
    # The stamp consumers: the nameless-button check and the copy
    # header — a reversion to a textContent read of an icon-stamped
    # header reads 0.
    assert js.count('getAttribute("data-key")') == 2
    # One timer binding — the duplicate-declaration casualty read 2.
    assert js.count("var feedbackTimer") == 1
    # Knowing shift: one definition plus three calls was 4; now 5 —
    # the additional refusal call handles a synchronous clipboard
    # exception, beside promise refusal and unsupported browsers.
    assert js.count("showFeedback") == 5
    assert js.count('feedback("Copied"') == 0
    assert js.count("COPY_LABEL") == 0
    # The success path and the runtime label: one source site each.
    assert js.count("Copied ") == 1
    assert js.count('aria-label", "Sort') == 1


# ---------------------------------------------------------------------------
# Widths, row limits, and copy policy: shape before artifact access
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (
            [],
            "core.table: parameter 'column_widths' must be a non-empty "
            "list of positive, finite numbers, got [] — "
            "use one ratio per rendered column, e.g. [2, 1]",
        ),
        (
            "2, 1",
            "core.table: parameter 'column_widths' must be a non-empty "
            "list of positive, finite numbers, got '2, 1' — "
            "use one ratio per rendered column, e.g. [2, 1]",
        ),
        (
            None,
            "core.table: parameter 'column_widths' must be a non-empty "
            "list of positive, finite numbers, got None — "
            "use one ratio per rendered column, e.g. [2, 1]",
        ),
        (
            [True],
            "core.table: parameter 'column_widths' must contain "
            "numbers, not booleans or strings, got True — "
            "use positive, finite ratios",
        ),
        (
            ["2"],
            "core.table: parameter 'column_widths' must contain "
            "numbers, not booleans or strings, got '2' — "
            "use positive, finite ratios",
        ),
        (
            [0],
            "core.table: parameter 'column_widths' contains "
            "0 — use positive, finite ratios greater than 0",
        ),
        (
            [-1],
            "core.table: parameter 'column_widths' contains "
            "-1 — use positive, finite ratios greater than 0",
        ),
        (
            [float("inf")],
            "core.table: parameter 'column_widths' contains "
            "inf — use positive, finite ratios greater than 0",
        ),
        (
            [float("-inf")],
            "core.table: parameter 'column_widths' contains "
            "-inf — use positive, finite ratios greater than 0",
        ),
        (
            [float("nan")],
            "core.table: parameter 'column_widths' contains "
            "nan — use positive, finite ratios greater than 0",
        ),
    ],
)
def test_column_width_shape_teaches_before_unavailable_data(
    tmp_path: Path, value: JsonValue, message: str
) -> None:
    store = _write_bundle(tmp_path, status="failed")
    context = RenderContext(store=store, theme=DEFAULT_THEME_PAIR)
    with pytest.raises(ValueError) as exc_info:
        _render(context, _table({"column_widths": value}))
    assert str(exc_info.value) == message


@pytest.mark.parametrize("value", [True, False, 0, -1, 2.0, "2", None])
def test_row_limit_shape_teaches_before_unavailable_data(
    tmp_path: Path, value: JsonValue
) -> None:
    store = _write_bundle(tmp_path, status="failed")
    context = RenderContext(store=store, theme=DEFAULT_THEME_PAIR)
    with pytest.raises(ValueError) as exc_info:
        _render(context, _table({"max_visible_rows": value}))
    assert str(exc_info.value) == (
        "core.table: parameter 'max_visible_rows' must be a "
        f"positive integer, got {value!r} — use e.g. 12, "
        "or omit it to show an unrestricted table"
    )


@pytest.mark.parametrize("value", ["ALL", "filtered", "", True, 1, None])
def test_copy_policy_shape_teaches_before_unavailable_data(
    tmp_path: Path, value: JsonValue
) -> None:
    store = _write_bundle(tmp_path, status="failed")
    context = RenderContext(store=store, theme=DEFAULT_THEME_PAIR)
    with pytest.raises(ValueError) as exc_info:
        _render(context, _table({"copy_rows": value}))
    assert str(exc_info.value) == (
        "core.table: parameter 'copy_rows' must be 'all' or "
        f"'visible', got {value!r} — use 'all' to copy every "
        "filter-matching row, or 'visible' for the scroll viewport"
    )


def test_table_presentation_defaults_preserve_existing_behavior(
    tmp_path: Path,
) -> None:
    context = _context(_write_bundle(tmp_path))
    body = _html(context, _table())
    assert body.startswith('<div class="coda-table" data-copy-rows="all">')
    assert "data-max-visible-rows" not in body
    assert "coda-table--fixed-widths" not in body
    assert "<colgroup>" not in body
    assert '<div class="coda-table__viewport"><table>' in body
    assert "<tr><td>S1</td><td>30.5</td><td>passed</td></tr>" in body
    assert "<tr><td>S2</td><td>0</td><td>failed</td></tr>" in body
    assert "<tr><td>S3</td><td>12.25</td><td>passed</td></tr>" in body


# ---------------------------------------------------------------------------
# Width ratios: validated against the final rendered columns
# ---------------------------------------------------------------------------


def test_column_widths_follow_selected_column_order(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    body = _html(
        context,
        _table(
            {
                "columns": ["status", "sample_id"],
                "column_widths": [1, 3],
            }
        ),
    )
    assert body.startswith(
        '<div class="coda-table coda-table--fixed-widths" data-copy-rows="all">'
    )
    assert (
        '<table><colgroup><col style="width: 25%">'
        '<col style="width: 75%"></colgroup><thead>' in body
    )
    assert body.index('data-key="status"') < body.index('data-key="sample_id"')
    assert 'data-key="depth"' not in body
    assert "<tr><td>passed</td><td>S1</td></tr>" in body


@pytest.mark.parametrize(
    ("parameters", "count"),
    [
        ({"column_widths": [1, 1]}, 3),
        ({"columns": ["depth"], "column_widths": [1, 1]}, 1),
    ],
)
def test_width_count_matches_rendered_columns(
    tmp_path: Path, parameters: ComponentParameters, count: int
) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError) as exc_info:
        _render(context, _table(parameters))
    assert str(exc_info.value) == (
        "core.table: 'column_widths' gives 2 ratios "
        f"for {count} rendered columns — use exactly "
        "one ratio per column after 'columns' selection, including "
        "the index column when present"
    )


def test_width_count_includes_the_retained_index(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path, content=_INDEX_TABLE))
    parameters = _table({"columns": ["depth"], "column_widths": [1]})
    with pytest.raises(ValueError) as exc_info:
        _render(context, parameters)
    assert str(exc_info.value) == (
        "core.table: 'column_widths' gives 1 ratios "
        "for 2 rendered columns — use exactly "
        "one ratio per column after 'columns' selection, including "
        "the index column when present"
    )
    body = _html(
        context,
        _table({"columns": ["depth"], "column_widths": [1, 3]}),
    )
    assert (
        '<colgroup><col style="width: 25%"><col style="width: 75%"></colgroup>' in body
    )
    assert body.index('data-key=""') < body.index('data-key="depth"')
    assert "<tr><td>S1</td><td>30.5</td></tr>" in body


def test_headerless_tables_accept_positional_widths(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path, content="S1\t30.5\nS2\t0\n"))
    body = _html(
        context,
        _table({"header": False, "column_widths": [3, 1]}),
    )
    assert (
        '<colgroup><col style="width: 75%"><col style="width: 25%"></colgroup>' in body
    )
    assert body.index('data-key="Column 1"') < body.index('data-key="Column 2"')
    assert "<tr><td>S1</td><td>30.5</td></tr>" in body


def test_single_column_tables_accept_one_width_ratio(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    body = _html(
        context,
        _table({"columns": ["depth"], "column_widths": [2]}),
    )
    assert '<colgroup><col style="width: 100%"></colgroup>' in body
    assert "<tr><td>30.5</td></tr>" in body


def test_width_normalization_avoids_sum_overflow(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    body = _html(
        context,
        _table(
            {
                "columns": ["sample_id", "depth"],
                "column_widths": [1e308, 1e308],
            }
        ),
    )
    assert (
        '<colgroup><col style="width: 50%"><col style="width: 50%"></colgroup>' in body
    )


# ---------------------------------------------------------------------------
# Row limits are enhancement metadata, never content truncation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("copy_rows", ["all", "visible"])
def test_row_limit_ships_every_row_without_inline_clipping(
    tmp_path: Path, copy_rows: str
) -> None:
    context = _context(_write_bundle(tmp_path))
    body = _html(
        context,
        _table({"max_visible_rows": 1, "copy_rows": copy_rows}),
    )
    assert body.startswith(
        f'<div class="coda-table" data-copy-rows="{copy_rows}"'
        ' data-max-visible-rows="1">'
    )
    assert '<div class="coda-table__viewport"><table>' in body
    assert body.count("<tr><td>") == 3
    assert "<tr><td>S1</td><td>30.5</td><td>passed</td></tr>" in body
    assert "<tr><td>S2</td><td>0</td><td>failed</td></tr>" in body
    assert "<tr><td>S3</td><td>12.25</td><td>passed</td></tr>" in body
    assert "max-height" not in body
    assert "overflow" not in body
    assert "coda-table__viewport--scrolling" not in body
    assert 'tabindex="0"' not in body


def test_visible_copy_policy_is_allowed_without_a_row_limit(
    tmp_path: Path,
) -> None:
    context = _context(_write_bundle(tmp_path))
    body = _html(context, _table({"copy_rows": "visible"}))
    assert body.startswith('<div class="coda-table" data-copy-rows="visible">')
    assert "data-max-visible-rows" not in body
    assert body.count("<tr><td>") == 3


def test_row_limit_accepts_a_header_only_table(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path, content="sample\tdepth\n"))
    body = _html(context, _table({"max_visible_rows": 1}))
    assert 'data-max-visible-rows="1"' in body
    assert "<tbody></tbody>" in body
    assert "max-height" not in body


def test_caption_is_outside_the_scroll_viewport(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    body = _html(
        context,
        _table({"max_visible_rows": 1, "caption": "All samples."}),
    )
    assert (
        "</tbody></table></div>"
        '<p class="coda-table__caption">All samples.</p>'
        "</div>" in body
    )
    assert body.index("coda-table__controls") < body.index("coda-table__viewport")


def test_valid_enhancement_parameters_preserve_unavailable_outcomes(
    tmp_path: Path,
) -> None:
    store = _write_bundle(tmp_path, status="failed")
    context = RenderContext(store=store, theme=DEFAULT_THEME_PAIR)
    message = _unavailable_message(
        context,
        _table(
            {
                "column_widths": [1, 2, 1],
                "max_visible_rows": 1,
                "copy_rows": "visible",
            }
        ),
    )
    assert "declared with status 'failed'" in message


# ---------------------------------------------------------------------------
# Enhancement source contracts: not browser-execution tests
# ---------------------------------------------------------------------------


def test_width_styles_are_opt_in_and_allow_wrapping() -> None:
    css = read_core_asset("table.css")
    assert ".coda-table--fixed-widths table {\n  table-layout: fixed;\n}" in css
    assert (
        ".coda-table--fixed-widths th,\n"
        ".coda-table--fixed-widths td {\n"
        "  overflow-wrap: anywhere;\n"
        "}" in css
    )
    assert ".coda-table--fixed-widths thead th {\n  white-space: normal;\n}" in css


def test_scroll_styles_are_script_gated_and_print_restores_content() -> None:
    css = read_core_asset("table.css")
    screen, print_rules = css.split("@media print {", 1)
    assert (
        ".coda-js .coda-table__viewport--scrolling {\n  overflow-y: auto;\n}" in screen
    )
    # Baseline CSS cannot clip content without successful measurement.
    assert "max-height:" not in screen
    assert (
        ".coda-table__viewport {\n"
        "    max-height: none !important;\n"
        "    height: auto !important;\n"
        "    overflow: visible !important;\n"
        "  }" in print_rules
    )
    assert (
        ".coda-table--filtered {\n"
        "    display: table-row !important;\n"
        "  }" in print_rules
    )
    assert (
        ".coda-js .coda-table__viewport--scrolling thead {\n"
        "    position: static !important;\n"
        "  }" in print_rules
    )


def test_viewport_measurement_source_tracks_rows_and_visibility() -> None:
    js = read_core_asset("table.js")
    assert 'root.getAttribute("data-max-visible-rows")' in js
    assert "height = table.tHead.getBoundingClientRect().height;" in js
    assert "height += row.getBoundingClientRect().height;" in js
    assert "if (count < limit)" in js
    assert "if (count <= limit)" in js
    assert "if (rect.width <= 0 || rect.height <= 0)" in js
    assert 'viewport.style.removeProperty("max-height");' in js
    assert 'viewport.style.maxHeight = Math.ceil(height) + "px";' in js
    assert 'viewport.setAttribute("tabindex", "0");' in js
    assert 'viewport.setAttribute("role", "region");' in js
    assert 'viewport.setAttribute("aria-label", "Scrollable table rows");' in js
    # One definition and two calls: sort and filter reset scrolling.
    assert js.count("resetViewport()") == 3
    assert 'window.addEventListener("resize", scheduleRefresh);' in js
    assert "observer.observe(root);" in js
    assert "observer.observe(table);" in js
    assert 'attributeFilter: ["class", "style", "hidden"]' in js
    assert "document.fonts.ready.then(scheduleRefresh);" in js


def test_copy_source_respects_filter_and_declared_viewport_policy() -> None:
    js = read_core_asset("table.js")
    assert 'var copyVisible = root.getAttribute("data-copy-rows") === "visible";' in js
    # An unbounded table copies every filter match even in visible mode.
    assert "if (!copyVisible || !viewport.classList.contains(SCROLLING))" in js
    # Positive rectangle intersection includes partially visible rows;
    # the sticky header's bottom bounds the unobscured viewport.
    assert "table.tHead.getBoundingClientRect().bottom" in js
    assert (
        "return rowBounds.bottom > top &&\n"
        "        rowBounds.top < bounds.top + viewport.clientHeight;" in js
    )
    assert "if (row.classList.contains(HIDDEN) || !withinViewport(row))" in js
    assert '"Copy visible rows as TSV" : "Copy all matching rows as TSV";' in js
    assert 'copyButton.setAttribute("aria-label", copyLabel);' in js
    assert 'copyButton.setAttribute("title", copyLabel);' in js
    assert 'showFeedback("Copied " + count + " rows", true);' in js
