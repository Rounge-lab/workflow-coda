==========
core.table
==========

One artifact-backed table: every row, in file order, rendered into
the page complete — with column sort, row filter, and copy-as-TSV
as enhancement for readers whose browsers run the page's script.

``core.table`` is a CARD component: the framework paints the card
and the placement's resolved ``title``, the component paints the
body.  A reader without scripting still reads the whole table, and
the printed page shows every row — the enhancements operate on
rows that are already there.

Identity
--------

* **Id:** ``core.table``
* **Default title:** ``Table``; the placement's ``title`` key
  overrides it for that instance
* **Description:** one artifact-backed table, complete and
  unscripted, with sort, filter, and copy as enhancement
* **Chrome mode:** ``CARD`` — the framework paints the card and the
  placement's resolved title; the component paints the body alone.
  Degradation is the framework's in both modes (see
  `Outcomes and chrome`_)

Placing it
----------

.. code-block:: yaml

   schema_version: "0.4.0"
   title: Sample QC
   tabs:
     - title: Samples
       components:
         - id: core.table
           title: Sample status
           parameters:
             artifact: org.example.samples
             columns: [status, sample_id]
             caption: Per-sample status.

A placement carries the component id, an optional per-instance
``title``, and the component's ``parameters``.  The two placement
gates — ``on_missing`` and ``on_unavailable`` — decide what happens
when things are absent; they are placement keys, siblings of
``id`` and ``title``, never parameters, and shared by every
component: described once in :ref:`Placement gates <core-placement-gates>`.

Parameters
----------

The parameter grammar follows the honest-data law, and the
vocabulary is closed: every key the table reads is in the table,
and an unknown key — a typo, or a placement key nested by accident —
raises a teaching error naming the accepted vocabulary and, when
close, the nearest match.

.. list-table::
   :header-rows: 1

   * - Key
     - Required
     - Shape
     - Meaning
   * - ``artifact``
     - yes
     - non-empty string
     - The artifact's *type*; must be declared with format
       ``core.tabular``.
   * - ``sep``
     - no — default ``"\t"``
     - single character
     - The field delimiter.  Declare the file's actual delimiter —
       a uniformly wrong ``sep`` reads every line as one field and
       renders a misread one-column table (see
       `Honest boundaries`_).
   * - ``header``
     - no — default ``true``
     - boolean
     - Whether the first row is a header.  The one shape fact the
       bytes cannot declare — a header row is indistinguishable
       from a row of text — so the author declares it.
       ``header: false`` renders positional labels
       (``Column 1`` ...), the file's own declaration of position as
       meaning.
   * - ``columns``
     - no
     - non-empty list of unique, non-empty strings
     - Presentation policy: which columns appear and in what order,
       selected by header name.  Membership is checked against the
       artifact's own header, where the data lives.
       ``header: false`` and ``columns`` together are refused:
       positional selection would be invented vocabulary.
   * - ``column_widths``
     - no — default automatic sizing
     - non-empty list of positive, finite numbers
     - Relative widths, one per rendered column after ``columns``
       selection, including the index column when present.
       ``[2, 1]`` gives the first column twice the second's width.
       Declared widths use fixed table layout with wrapping;
       omitted widths preserve automatic sizing.
   * - ``max_visible_rows``
     - no — default unrestricted
     - positive integer
     - Maximum number of complete body rows in the enhanced scroll
       viewport; the header does not count. Every row remains in
       the HTML. Without scripting, and when printing, all rows
       remain visible.
   * - ``copy_rows``
     - no — default ``all``
     - ``all`` or ``visible``
     - ``all`` copies every filter-matching row, preserving the
       existing behavior. ``visible`` copies filter-matching rows
       intersecting the table's scroll viewport, including partially
       visible rows. Both preserve current sort order and rendered
       columns. Without a scroll restriction, both copy every
       filter-matching row.
   * - ``caption``
     - no
     - non-empty string
     - Author prose, rendered under the table.

The honest-data split, as throughout: the rows and the header are
data — read verbatim, cells escaped and never reinterpreted; the
producer's own formatting is data.  ``sep`` and ``header`` are
shape policy, ``columns`` presentation policy, ``caption``
authorship.  Placement keys — ``title``, ``on_unavailable`` — live
at the placement level, never inside ``parameters:``; a key nested
by accident teaches the move.

Column widths and scrolling
---------------------------

Width ratios describe the final rendered columns, not the artifact's
original column order. An automatically retained index column counts
as a rendered column and takes the first ratio. Headerless tables
also support ratios, in file-column order. A one-column table may
declare a single ratio.

.. code-block:: yaml

   - id: core.table
     title: Sample status
     parameters:
       artifact: org.example.samples
       columns: [status, sample_id]
       column_widths: [1, 2]
       max_visible_rows: 12
       copy_rows: all
       caption: Per-sample status.

This example assumes the artifact has no index column. With an index
column, supply three ratios instead.

The row limit is a scripted enhancement, not truncation: every row
ships in the HTML. The script measures the header and the first
declared number of matching body rows, allowing for wrapped cells.
It refreshes the measurement after sorting, filtering, resizing,
and when a hidden panel becomes visible. Sorting and filtering reset
the table's scroll position to the top.

The scroll region is keyboard-focusable and its header stays visible
while scrolling. Without scripting, the table has no height
restriction. Printing removes the restriction and restores
filter-hidden rows.

``copy_rows: all`` means all rows in the current filtered result,
not rows excluded by the filter. ``copy_rows: visible`` uses the
table's own scroll viewport, not the browser's page viewport; rows
covered entirely by the sticky header are excluded. The copy button's
accessible label and tooltip identify its policy.

The ``core.tabular`` format
---------------------------

``core.table`` reads artifacts declared with the core plugin's
own namespaced file format — ``format: core.tabular`` in the
manifest.  The format is a claim, not a service: the store hands
the reader checksum-verified UTF-8 text and parses nothing.  The
format is decoupled from any one component, the way ``json`` is:
``core.chart`` (:doc:`chart`) reads the same format and plots it —
one format, two readers, the grammar living in the core plugin
(the format value space is documented in
:doc:`../schemas/index`).

The index-column convention
---------------------------

A header whose first cell is blank is the producer declaring the
first column a row index — in-band, the widespread tabular
convention for count matrices and per-sample tables.  The
convention is detected, never configured: the index column renders
first, without a label, and ``columns`` orders the named columns
after it.  A blank header cell anywhere else is refused — only the
first position carries meaning.

Sort, filter, copy
------------------

The complete table ships in the HTML.  The controls bar — a filter
input and a copy button — ships with it, display-none until the
page's script marks the document scripted, so nothing looks
interactive that is not.

* **Sort** is a three-state cycle per column: ascending, descending,
  then the original file order — the authored order is always one
  click away.  Numeric columns sort by value, text by
  ``localeCompare``, per the column's build-time type stamp; empty
  cells sink to the bottom in both directions.  The stamp rides
  each header as ``data-type``: ``numeric`` when the column has data
  and every non-empty cell parses as a finite number, else ``text``
  — ``nan`` and ``inf`` read as text, words about data rather than
  data. State is announced on the ``th`` through ``aria-sort`` — the
  single announced channel.
* **Filter** is a case-insensitive substring match across each
  row's cells; matching rows hide by class and are never deleted,
  so clearing the filter restores the table exactly.  The field is
  named through its ``aria-label``, with the framework's filter
  icon as a decorative prefix.
* **Copy** exports post-``columns`` columns in current sort order
  as TSV through ``navigator.clipboard``, cells quoted per the
  ``csv`` dialect. By default, ``copy_rows: all`` exports every
  filter-matching row, including rows outside the scroll viewport.
  ``copy_rows: visible`` exports only filter-matching rows
  intersecting that viewport, including partially visible rows.
  The button's accessible label and tooltip identify the policy.
  Success shows a check icon and announces the actual copied row
  count; clipboard refusal shows a message. The button icon is
  restored after a moment.
* **Print** honors the panels law: controls are hidden,
  filter-hidden rows are restored, and the scroll viewport becomes
  unrestricted, so the printed page shows the complete table in
  its current order.

Outcomes and chrome
-------------------

Three families, kept distinct — who is wrong decides what the
reader sees.

.. list-table::
   :header-rows: 1

   * - Family
     - Raised as
     - Shown as
   * - The layout is wrong: a missing or malformed parameter, an
       unknown key (with a suggestion), a placement key nested in
       ``parameters:``, ``columns`` against ``header: false``, a
       non-``core.tabular`` artifact, or a ``columns`` name the header
       does not carry (taught at data time, against the header's
       own vocabulary)
     - ``ValueError``
     - a plugin failure, collected and shown in place
   * - The run is partial: the artifact is undeclared, declared with
       a non-``complete`` status, or its file is missing
     - ``ArtifactUnavailableError``
     - the unavailable notice card — a fact about the run
   * - The artifact lies about its shape: no header row, a blank
       header cell beyond the first, duplicate column names, a row
       that does not match the table's width, or a headerless file
       with no rows
     - ``ArtifactReadError``
     - a plugin failure, collected and shown in place

The table's page chrome is self-hosted through the component
channel: the stylesheet and the script each inline once per report,
in first-placement order, exactly when at least one table placement
renders ``ok`` — the stylesheet into the page's component style
block under the ``/* core.table */`` banner, the script into its
component script block under the ``// core.table`` banner, after
the framework's own scripts so the DOM is established when the
enhancement runs.  A report without healthy table placements
carries no table chrome at all.

Honest boundaries
-----------------

A uniformly wrong ``sep`` cannot be caught at parse time — nothing
disagrees.  A comma-delimited file read under the default tab
parses every line as one field and renders a one-column table whose
header is the file's first line, complete and misread.  The fix is
declaring the file's actual delimiter; the ragged-row teaching names
the suspect delimiter when the signature matches — a one-field row
against a wider header — which is the mixed-delimiter case the
parser *can* see.

Example
-------

A manifest declaration and a layout placement, together:

.. code-block:: json

   {
     "id": "samples",
     "type": "org.example.samples",
     "schema_version": "0.1.0",
     "path": "samples.tsv",
     "format": "core.tabular",
     "status": "complete"
   }

.. code-block:: yaml

   - id: core.table
     title: Sample status
     parameters:
       artifact: org.example.samples
       columns: [status, sample_id]
       caption: Per-sample status.
