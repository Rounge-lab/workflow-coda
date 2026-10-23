"""The table component: one artifact-backed table, complete and
unscripted, with sort, filter, and copy as enhancement.

``core.table`` renders a delimited-text table — every row, in file
order — inside the framework's card chrome: a CARD component, so the
framework paints the card and the placement's resolved title, and
this module paints the body.  The page's script, shipped with the
component through the page-chrome channel, enhances the complete
table in place — sort, filter, copy — so a reader without scripting
still reads every row, and printing shows the whole table.

The component is the ``core.table`` artifact format's one grammar
home.  The format is a namespaced plugin convention: the manifest
declares ``format: core.table`` — a claim whose meaning lives here,
not in the framework — and the store hands over checksum-verified
UTF-8 text through ``read_text``, which this module parses under the
placement's ``sep``.

The parameter grammar follows the honest-data law:

* the *rows and the header* are data: read from the artifact
  verbatim, cells escaped and never reinterpreted — the producer's
  own formatting is data;
* ``sep`` and ``header`` are policy: the author's reading of the
  file's shape — the field delimiter (one character, default the
  tab) and whether the first row is a header (the default; a row of
  text is indistinguishable from a header row, so the author
  declares what the bytes cannot);
* ``columns`` is policy: presentation — which columns appear and in
  what order, selected by their header names;
* ``caption`` is authorship: prose, honest because visibly prose;
* the vocabulary is closed: unknown parameter keys teach at the
  parse boundary, placement keys nested in ``parameters:`` with the
  instruction to move them out.

One convention is detected, never configured: a header whose first
cell is blank is the producer declaring the first column a row
index, in-band.  The index column always renders first, without a
label; ``columns`` orders the named columns after it.

Two failure families, kept distinct:

* a malformed parameter — every *shape* error — raises a teaching
  ``ValueError`` before any data is touched; the report builder
  collects it as a plugin failure shown in place, because the layout
  itself is wrong.  ``columns`` membership is taught at data time,
  against the artifact's own header;
* missing data — an undeclared artifact, a non-complete status, an
  absent file — raises ``ArtifactUnavailableError`` and renders as
  the unavailable notice, because absent data is a fact about the
  run.

A file that does not parse under its claimed format — a ragged row,
an empty or duplicated header cell — teaches as an
:class:`~workflow_coda.errors.ArtifactReadError`: the artifact is
lying about its shape, a plugin failure the builder reports, never
a quiet notice.
"""

import csv
import html
import io
import math
from dataclasses import dataclass
from typing import Final

from ..components import (
    ComponentParameters,
    PlacementInfo,
    RenderedComponent,
    reject_unknown_parameters,
)
from ..context import RenderContext
from ..errors import ArtifactReadError, ArtifactUnavailableError

_FORMAT: Final[str] = "core.table"
"""The artifact format this component reads — its own namespaced
convention, declared in the manifest as ``format: core.table``: the
claim whose grammar lives in this module."""

_TABLE_PARAMETERS: Final[frozenset[str]] = frozenset(
    {"artifact", "caption", "columns", "header", "sep"}
)
"""core.table's accepted parameter vocabulary: the closed set
:func:`_parse_spec` reads, for the unknown-key teaching."""


def _required_text(parameters: ComponentParameters, name: str) -> str:
    """A required string parameter, or a teaching ``ValueError``."""
    if name not in parameters:
        raise ValueError(f"core.table: parameter {name!r} is required")
    value = parameters[name]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"core.table: parameter {name!r} must be a non-empty string, got {value!r}"
        )
    return value


def _optional_text(parameters: ComponentParameters, name: str) -> str | None:
    """An optional string parameter, absent by default."""
    if name not in parameters:
        return None
    value = parameters[name]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"core.table: parameter {name!r}, when given, must be a "
            f"non-empty string, got {value!r}"
        )
    return value


def _sep_from(parameters: ComponentParameters) -> str:
    """The field delimiter: one character, default the tab."""
    if "sep" not in parameters:
        return "\t"
    value = parameters["sep"]
    if not isinstance(value, str) or len(value) != 1:
        raise ValueError(
            f"core.table: parameter 'sep', when given, must be a single "
            f"character, got {value!r}"
        )
    return value


def _header_from(parameters: ComponentParameters) -> bool:
    """Whether the file's first row is a header; the default."""
    if "header" not in parameters:
        return True
    value = parameters["header"]
    if not isinstance(value, bool):
        raise ValueError(
            f"core.table: parameter 'header', when given, must be a "
            f"boolean, got {value!r}"
        )
    return value


def _columns_from(parameters: ComponentParameters) -> tuple[str, ...] | None:
    """The column order and inclusion policy, or ``None`` when the
    layout declares none.

    Shape only: a non-empty list of unique non-empty strings —
    declared policy that selects nothing teaches, and a column may
    not appear twice.  Membership is checked later, against the
    artifact's own header, where the data lives.
    """
    if "columns" not in parameters:
        return None
    value = parameters["columns"]
    if not isinstance(value, list) or not value:
        raise ValueError(
            "core.table: parameter 'columns', when given, must be a "
            "list of column names, e.g. ['sample', 'depth'], got "
            f"{value!r}"
        )
    names: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                f"core.table: parameter 'columns' must list non-empty "
                f"column names, got {item!r}"
            )
        if item in names:
            raise ValueError(
                f"core.table: parameter 'columns' names {item!r} twice — "
                "a column appears once"
            )
        names.append(item)
    return tuple(names)


@dataclass(frozen=True, slots=True)
class _TableSpec:
    """One placement's parameters, parsed and shape-validated."""

    artifact_type: str
    sep: str
    header: bool
    columns: tuple[str, ...] | None
    caption: str | None


def _parse_spec(parameters: ComponentParameters) -> _TableSpec:
    """Parse and shape-validate every parameter, or teach.

    The shape half of the honest-data law: this function touches no
    store and reads no artifact — every malformed parameter raises
    its teaching ``ValueError`` here, before any data is read.  The
    vocabulary is closed and checked first: unknown keys — typos, and
    placement keys nested by accident — teach before any known key is
    read.
    """
    reject_unknown_parameters("core.table", parameters, _TABLE_PARAMETERS)
    spec = _TableSpec(
        artifact_type=_required_text(parameters, "artifact"),
        sep=_sep_from(parameters),
        header=_header_from(parameters),
        columns=_columns_from(parameters),
        caption=_optional_text(parameters, "caption"),
    )
    if spec.columns is not None and not spec.header:
        raise ValueError(
            "core.table: 'columns' selects columns by their header names, "
            "but this placement declares header: false — a headerless "
            "table shows every column, in file order"
        )
    return spec


@dataclass(frozen=True, slots=True)
class _ParsedTable:
    """The artifact's table, read with full fidelity.

    *labels* is ``None`` for a headerless file.  *has_index* is true
    when the header's first cell is blank — the producer's in-band
    index-column declaration.  *rows* keeps file order and cell text
    verbatim; blank lines are already skipped.
    """

    labels: tuple[str, ...] | None
    has_index: bool
    rows: tuple[tuple[str, ...], ...]


def _parse_entries(
    text: str, sep: str, label: str
) -> list[tuple[int, tuple[str, ...]]]:
    """The artifact's lines as ``(line number, cells)`` entries, blank
    lines skipped; a parse failure teaches as the producer lying
    about the artifact's shape."""
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=sep)
    entries: list[tuple[int, tuple[str, ...]]] = []
    try:
        for row in reader:
            if row:  # Blank lines skip; a line of one empty field is data.
                entries.append((reader.line_num, tuple(row)))
    except csv.Error as e:
        raise ArtifactReadError(
            f"artifact {label} does not parse as core.table data: {e}"
        ) from e
    return entries


def _require_header(
    entries: list[tuple[int, tuple[str, ...]]], label: str
) -> tuple[tuple[str, ...], bool]:
    """The header row and its index-column declaration, or the
    teaching errors of a malformed header."""
    if not entries:
        raise ArtifactReadError(f"artifact {label} contains no header row")
    header = entries[0][1]
    has_index = header[0] == ""
    seen: set[str] = set()
    for position, cell in enumerate(header):
        if cell == "":
            if position == 0:
                continue  # the in-band index-column declaration
            raise ArtifactReadError(
                f"artifact {label} has an empty header column name at "
                f"position {position + 1} (only the first cell may be "
                "blank, to declare an index column)"
            )
        if cell in seen:
            raise ArtifactReadError(
                f"artifact {label} has duplicate header column {cell!r}"
            )
        seen.add(cell)
    return header, has_index


def _require_aligned(
    data: list[tuple[int, tuple[str, ...]]],
    width: int,
    sep: str,
    label: str,
) -> list[tuple[str, ...]]:
    """The data rows, each matching the table's width — or the
    ragged-row teaching, naming the delimiter when a one-field row
    suggests the wrong ``sep``."""
    checked: list[tuple[str, ...]] = []
    for line_num, row in data:
        if len(row) != width:
            fields = "field" if len(row) == 1 else "fields"
            hint = (
                f" — is sep ({sep!r}) the file's actual delimiter?"
                if len(row) == 1 and width > 1
                else ""
            )
            raise ArtifactReadError(
                f"artifact {label}: row at line {line_num} has "
                f"{len(row)} {fields}, expected {width}{hint}"
            )
        checked.append(row)
    return checked


def _read_table(context: RenderContext, spec: _TableSpec) -> _ParsedTable:
    """Read and parse the artifact under the placement's ``sep``, or
    raise why not.

    Missing data raises :class:`ArtifactUnavailableError` — the
    caller converts it.  A file that does not parse under its claimed
    format teaches as :class:`ArtifactReadError` — the producer lying
    about the artifact's shape.  A non-``core.table`` artifact is a
    layout mistake, taught as a ``ValueError``.  The parse, header,
    and ragged-row families each live in their own helper above.
    """
    artifact = context.store.require(spec.artifact_type)
    if artifact.declaration.format != _FORMAT:
        raise ValueError(
            f"core.table: artifact {spec.artifact_type!r} has format "
            f"'{artifact.declaration.format}'; core.table reads "
            "'core.table'-format artifacts — declare the artifact's "
            "format as 'core.table' in the manifest"
        )
    label = f"{artifact.declaration.id!r} ({spec.artifact_type})"
    entries = _parse_entries(artifact.read_text(), spec.sep, label)
    header: tuple[str, ...] | None
    if spec.header:
        header, has_index = _require_header(entries, label)
        data = entries[1:]
        width = len(header)
    else:
        if not entries:
            raise ArtifactReadError(
                f"artifact {label} has no rows, so its column count is "
                "unknown — a headerless table needs at least one row"
            )
        header = None
        has_index = False
        data = entries
        width = len(entries[0][1])
    return _ParsedTable(
        labels=header,
        has_index=has_index,
        rows=tuple(_require_aligned(data, width, spec.sep, label)),
    )


@dataclass(frozen=True, slots=True)
class _RenderedTable:
    """The table as this placement shows it: labels beside aligned
    rows, the ``columns`` policy applied."""

    labels: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


def _apply_columns(parsed: _ParsedTable, spec: _TableSpec) -> _RenderedTable:
    """Apply the ``columns`` policy to the parsed table, or teach.

    Headerless tables pass through with positional labels — the
    file's own declaration of position as meaning.  Headered tables
    keep the index column (when present) first, always, and order the
    named columns as the author asked; an unknown name teaches
    against the header's own vocabulary.
    """
    if parsed.labels is None:
        width = len(parsed.rows[0])
        labels = tuple(f"Column {i + 1}" for i in range(width))
        return _RenderedTable(labels=labels, rows=parsed.rows)
    start = 1 if parsed.has_index else 0
    fixed = ("",) if parsed.has_index else ()
    named = parsed.labels[start:]
    if spec.columns is None:
        order = tuple(range(len(named)))
    else:
        by_name = {name: i for i, name in enumerate(named)}
        for name in spec.columns:
            if name not in by_name:
                carried = ", ".join(repr(n) for n in named) or "no named columns"
                raise ValueError(
                    f"core.table: 'columns' names {name!r}, but this "
                    f"artifact's header carries {carried} — fix the "
                    "name, or the artifact"
                )
        order = tuple(by_name[name] for name in spec.columns)
    return _RenderedTable(
        labels=fixed + tuple(named[i] for i in order),
        rows=tuple(
            row[:start] + tuple(row[start + i] for i in order) for row in parsed.rows
        ),
    )


def _is_numeric_cell(cell: str) -> bool:
    """Whether one cell reads as a finite number."""
    try:
        return math.isfinite(float(cell))
    except ValueError:
        return False


def _column_type(cells: list[str]) -> str:
    """The build-time column type: ``numeric`` when the column has
    data and every non-empty cell reads as a finite number, else
    ``text``.

    ``nan`` and ``inf`` read as text: in this domain they are words
    about data, not data.  The stamp is fact, precomputed — the
    page's script consumes it and never re-derives it.
    """
    seen_data = False
    for cell in cells:
        if not cell:
            continue
        if not _is_numeric_cell(cell):
            return "text"
        seen_data = True
    return "numeric" if seen_data else "text"


def _assemble_markup(rendered: _RenderedTable, caption: str | None) -> str:
    """Emit the complete table: the controls bar, the header with its
    build-time stamps, every row, the caption.

    Pure string assembly — every decision is already made; all
    artifact- and author-sourced text escapes here.  The controls
    bar ships in the markup and is display-none until the page's
    script marks the document scripted — nothing looks interactive
    that is not.
    """
    head = "".join(
        f'<th scope="col" data-key="{html.escape(label)}"'
        f' data-type="{_column_type([row[i] for row in rendered.rows])}">'
        f"{html.escape(label)}</th>"
        for i, label in enumerate(rendered.labels)
    )
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
        for row in rendered.rows
    )
    caption_html = (
        f'<p class="coda-table__caption">{html.escape(caption)}</p>'
        if caption is not None
        else ""
    )
    return (
        '<div class="coda-table">'
        '<div class="coda-table__controls">'
        "<label>Filter rows "
        '<input type="search" class="coda-table__filter"></label> '
        '<button type="button" class="coda-table__copy">Copy as TSV</button>'
        "</div>"
        "<table><thead><tr>"
        f"{head}"
        "</tr></thead><tbody>"
        f"{body}"
        "</tbody></table>"
        f"{caption_html}"
        "</div>"
    )


def render_table(
    context: RenderContext,
    _info: PlacementInfo,
    parameters: ComponentParameters,
) -> RenderedComponent:
    """Render one table: data from the store, shape policy from the
    layout, presentation stamped at build time — the body alone,
    because core.table is a CARD component and the framework paints
    the card, the placement's resolved title included.

    The orchestrator only sequences the stories: parse the
    placement's parameters (:func:`_parse_spec`), read and parse the
    artifact under the placement's ``sep`` (:func:`_read_table`),
    apply the ``columns`` policy (:func:`_apply_columns`), and
    assemble the complete markup (:func:`_assemble_markup`), column
    types included.  Each helper owns its own errors; missing data
    converts to an unavailable notice here, where the outcome
    vocabulary lives.
    """
    spec = _parse_spec(parameters)
    try:
        parsed = _read_table(context, spec)
    except ArtifactUnavailableError as e:
        return RenderedComponent.unavailable(str(e))
    rendered = _apply_columns(parsed, spec)
    return RenderedComponent.from_html(_assemble_markup(rendered, spec.caption))
