"""The table component: one artifact-backed table, complete and
unscripted, with sort, filter, and copy as enhancement.

``core.table`` renders a delimited-text table — every row, in file
order — inside the framework's card chrome: a CARD component, so the
framework paints the card and the placement's resolved title, and
this module paints the body.  The page's script, shipped with the
component through the page-chrome channel, enhances the complete
table in place — sort, filter, copy — so a reader without scripting
still reads every row, and printing shows the whole table.

The sort affordance's state icons ship in the markup — one span per state beside every
column label, loaded from the build's icon library — and the stylesheet shows the one
span matching the column's aria-sort, which only the scripted page writes: chrome, not
content, so the complete-and-unscripted law is untouched. The controls bar rides icons
the same way — the filter field's placeholder stand-in and the copy button's icon face,
loaded through the build's library: chrome for the scripted enhancements.

``core.tabular`` is the core plugin's namespaced *file format* — a
delimited-text table, declared in the manifest as
``format: core.tabular`` — decoupled from any one component, the way
``json`` is: a claim whose grammar lives in the owning plugin, for
that plugin's components to interpret.  This module is the format's
first reader (``core.chart`` is its second); the store hands over
checksum-verified UTF-8 text through ``read_text``, which this module
parses under the placement's ``sep``.

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
from .parameters import _optional_bool, _optional_text, _required_text, _sep_from

_FORMAT: Final[str] = "core.tabular"
"""The tabular file format this component reads — the core plugin's
namespaced format, declared in the manifest as ``format:
core.tabular``: a claim whose grammar lives in the core package,
interpreted by this component and ``core.chart`` alike."""

_TABLE_PARAMETERS: Final[frozenset[str]] = frozenset(
    {
        "artifact",
        "caption",
        "columns",
        "column_widths",
        "copy_rows",
        "header",
        "max_visible_rows",
        "sep",
    }
)
"""core.table's accepted parameter vocabulary: the closed set
:func:`_parse_spec` reads, for the unknown-key teaching."""


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


def _column_widths_from(
    parameters: ComponentParameters,
) -> tuple[float, ...] | None:
    """Optional positive, finite ratios for the rendered columns."""
    if "column_widths" not in parameters:
        return None
    value = parameters["column_widths"]
    if not isinstance(value, list) or not value:
        raise ValueError(
            "core.table: parameter 'column_widths' must be a non-empty "
            f"list of positive, finite numbers, got {value!r} — "
            "use one ratio per rendered column, e.g. [2, 1]"
        )
    ratios: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(
                "core.table: parameter 'column_widths' must contain "
                f"numbers, not booleans or strings, got {item!r} — "
                "use positive, finite ratios"
            )
        try:
            ratio = float(item)
        except OverflowError as e:
            raise ValueError(
                "core.table: parameter 'column_widths' contains "
                f"{item!r} — use positive, finite ratios"
            ) from e
        if not math.isfinite(ratio) or ratio <= 0:
            raise ValueError(
                "core.table: parameter 'column_widths' contains "
                f"{item!r} — use positive, finite ratios greater than 0"
            )
        ratios.append(ratio)
    return tuple(ratios)


def _max_visible_rows_from(parameters: ComponentParameters) -> int | None:
    """An optional strictly positive integer, never coerced."""
    if "max_visible_rows" not in parameters:
        return None
    value = parameters["max_visible_rows"]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(
            "core.table: parameter 'max_visible_rows' must be a "
            f"positive integer, got {value!r} — use e.g. 12, "
            "or omit it to show an unrestricted table"
        )
    return value


def _copy_rows_from(parameters: ComponentParameters) -> str:
    """Copy all filter matches by default, or viewport-visible matches."""
    value = parameters.get("copy_rows", "all")
    if not isinstance(value, str) or value not in ("all", "visible"):
        raise ValueError(
            "core.table: parameter 'copy_rows' must be 'all' or "
            f"'visible', got {value!r} — use 'all' to copy every "
            "filter-matching row, or 'visible' for the scroll viewport"
        )
    return value


@dataclass(frozen=True, slots=True)
class _TableSpec:
    """One placement's parameters, parsed and shape-validated."""

    artifact_type: str
    sep: str
    header: bool
    columns: tuple[str, ...] | None
    caption: str | None
    column_widths: tuple[float, ...] | None
    max_visible_rows: int | None
    copy_rows: str


def _parse_spec(parameters: ComponentParameters) -> _TableSpec:
    """Validate the closed parameter vocabulary before reading data."""
    reject_unknown_parameters("core.table", parameters, _TABLE_PARAMETERS)
    spec = _TableSpec(
        artifact_type=_required_text("core.table", parameters, "artifact"),
        sep=_sep_from("core.table", parameters),
        header=_optional_bool("core.table", parameters, "header", default=True),
        columns=_columns_from(parameters),
        caption=_optional_text("core.table", parameters, "caption"),
        column_widths=_column_widths_from(parameters),
        max_visible_rows=_max_visible_rows_from(parameters),
        copy_rows=_copy_rows_from(parameters),
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
            "'core.tabular'-format artifacts — declare the artifact's "
            "format as 'core.tabular' in the manifest"
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


def _column_group(rendered: _RenderedTable, spec: _TableSpec) -> str:
    """Validate width count and emit normalized presentation ratios."""
    ratios = spec.column_widths
    if ratios is None:
        return ""
    if len(ratios) != len(rendered.labels):
        raise ValueError(
            f"core.table: 'column_widths' gives {len(ratios)} ratios "
            f"for {len(rendered.labels)} rendered columns — use exactly "
            "one ratio per column after 'columns' selection, including "
            "the index column when present"
        )
    largest = max(ratios)
    scaled = tuple(ratio / largest for ratio in ratios)
    total = math.fsum(scaled)
    columns = "".join(
        f'<col style="width: {ratio / total * 100:.12g}%">' for ratio in scaled
    )
    return f"<colgroup>{columns}</colgroup>"


def _assemble_markup(
    rendered: _RenderedTable,
    spec: _TableSpec,
    sort_icons: str,
    controls_bar: str,
    column_group: str,
) -> str:
    """Emit all content, with optional width policy and enhancement metadata."""
    head = "".join(
        f'<th scope="col" data-key="{html.escape(label)}"'
        f' data-type="{_column_type([row[i] for row in rendered.rows])}">'
        f"{html.escape(label)}{sort_icons}</th>"
        for i, label in enumerate(rendered.labels)
    )
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
        for row in rendered.rows
    )
    caption_html = (
        f'<p class="coda-table__caption">{html.escape(spec.caption)}</p>'
        if spec.caption is not None
        else ""
    )
    classes = "coda-table"
    if spec.column_widths is not None:
        classes += " coda-table--fixed-widths"
    limit_attribute = (
        f' data-max-visible-rows="{spec.max_visible_rows}"'
        if spec.max_visible_rows is not None
        else ""
    )
    return (
        f'<div class="{classes}" data-copy-rows="{spec.copy_rows}"'
        f"{limit_attribute}>"
        f"{controls_bar}"
        '<div class="coda-table__viewport">'
        f"<table>{column_group}<thead><tr>"
        f"{head}"
        "</tr></thead><tbody>"
        f"{body}"
        "</tbody></table></div>"
        f"{caption_html}"
        "</div>"
    )


_SORT_ICONS: Final[dict[str, str]] = {
    "idle": "core-table",
    "ascending": "core-ascending",
    "descending": "core-descending",
}
"""The sort-state icons by state: the framework's own shipped
icons, stamped beside every column label.  The state keys ride the
stamped spans' classes, and the stylesheet shows the one span that
matches the column's ``aria-sort`` — the state channel the page's
script owns."""


def _sort_icons_html(context: RenderContext) -> str:
    """The sort-state icon spans, one per state, stamped beside
    every column label.

    Loads the three shipped icons through the build's icon library
    — the same sanitized, cached, namespaced door every plugin's
    icons ride — and wraps each in its state's span.  All three
    ship in the markup, display-none until the page is scripted:
    the icons are the sort affordance's chrome, and a reader
    without scripting loses nothing by their silence.
    """
    return "".join(
        f'<span class="coda-table__sort-icon coda-table__sort-icon--{state}">'
        f"{context.icons.load(name).markup}</span>"
        for state, name in _SORT_ICONS.items()
    )


def _controls_bar(context: RenderContext) -> str:
    """The controls bar, iconed: the filter field with its permanent
    decorative prefix and the square copy button — chrome,
    display-none until the page is scripted.

    The filter's icon rides a wrapper span, always shown: it names
    the control's purpose beside its aria-label, not a placeholder
    that empties as the reader types.  The copy button is square —
    its height the filter field's own, its width its height — and
    both of its faces ship at build time: the copy icon it shows and
    the framework's check icon its success state swaps in, by class,
    never by DOM mutation.  The success count rides a visually
    hidden live region — the visible feedback is the check icon
    alone — and a refusal shows its message as text in the visible
    live region: honest both ways, on both channels.  All three
    icons load through the build's library: the same sanitized,
    cached door as the sort states.
    """
    filter_icon = context.icons.load("core-filter").markup
    copy_icon = context.icons.load("core-copy").markup
    check_icon = context.icons.load("core-check").markup
    return (
        '<div class="coda-table__controls">'
        '<span class="coda-table__filter-wrap">'
        '<input type="search" class="coda-table__filter" aria-label="Filter rows">'
        f'<span class="coda-table__filter-icon">{filter_icon}</span>'
        "</span>"
        '<button type="button" class="coda-table__copy" aria-label="Copy as TSV">'
        f'<span class="coda-table__copy-icon">{copy_icon}</span>'
        f'<span class="coda-table__copy-check">{check_icon}</span>'
        '<span class="coda-table__copy-feedback" aria-live="polite"></span>'
        '<span class="coda-table__copy-count coda-table__sr" aria-live="polite">'
        "</span>"
        "</button>"
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
    load the table's icons (:func:`_sort_icons_html` and
    :func:`_controls_bar` — after the unavailable conversion, so an
    unavailable placement stays unavailable), apply the ``columns``
    policy (:func:`_apply_columns`), and assemble the complete markup
    (:func:`_assemble_markup`), column types and icon chrome
    included.  Each helper owns its own errors; missing data
    converts to an unavailable notice here, where the outcome
    vocabulary lives.
    """
    spec = _parse_spec(parameters)
    try:
        parsed = _read_table(context, spec)
    except ArtifactUnavailableError as e:
        return RenderedComponent.unavailable(str(e))
    rendered = _apply_columns(parsed, spec)
    column_group = _column_group(rendered, spec)
    sort_icons = _sort_icons_html(context)
    controls_bar = _controls_bar(context)
    return RenderedComponent.from_html(
        _assemble_markup(rendered, spec, sort_icons, controls_bar, column_group)
    )
