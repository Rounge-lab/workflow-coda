==========
core.chart
==========

One artifact-backed chart: the artifact's rows plotted as one
interactive Plotly figure, inside the framework's card chrome.
``core.chart`` is a CARD component: the framework paints the card
and the placement's resolved ``title``, the component paints the
figure body alone.

The figure is the roster's one script-rendered body — it needs the
page's script to draw — while everything around it ships complete
in the HTML: the card, the resolved title, the caption, and the
figure's accessibility label, which states in words what the
figure shows.

``core.chart`` is the second reader of the ``core.tabular``
format: the same delimited-text files ``core.table`` renders as
tables (:doc:`table`), plotted — one file format, two readers,
decoupled from any one component the way ``json`` is.

Identity
--------

* **Id:** ``core.chart``
* **Default title:** ``Chart``; the placement's ``title`` key
  overrides it for that instance
* **Description:** one artifact-backed chart, rendered as an
  interactive Plotly figure
* **Chrome mode:** ``CARD`` — the framework paints the card and
  the placement's resolved title; the component paints the body
  alone.  Degradation is the framework's (see
  `Outcomes and chrome`_)

Placing it
----------

.. code-block:: yaml

   schema_version: "0.2.0"
   title: Sample QC
   tabs:
     - title: Samples
       components:
         - id: core.chart
           title: Depth by sample
           parameters:
             artifact: org.example.samples
             chart: bar
             x: sample_id
             y: depth
             hue: status

A placement carries the component id, an optional per-instance
``title``, and the component's ``parameters``.  The two placement
gates — ``on_missing`` and ``on_unavailable`` — decide what
happens when things are absent; they are placement keys, siblings
of ``id`` and ``title``, never parameters, and shared by every
component: described once in :ref:`Placement gates
<core-placement-gates>`.

Parameters
----------

The parameter grammar follows the honest-data law, and the
vocabulary is closed: every key the chart reads is in the table,
and an unknown key — a typo, or a placement key nested by accident
— raises a teaching error naming the accepted vocabulary and, when
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
   * - ``chart``
     - yes
     - ``bar`` | ``box`` | ``histogram`` | ``line`` | ``scatter``
     - The plot type.  No honest default exists — the placement
       names it.
   * - ``x``
     - all but a plain ``box``
     - non-empty string
     - The horizontal column: the values a histogram bins, the
       categories a grouped box plot groups by, the axis of the
       other types.  Optional only for ``box``, whose grouping is
       optional.
   * - ``y``
     - ``bar``, ``box``, ``line``, ``scatter``; refused with
       ``histogram``
     - non-empty string
     - The vertical column — the values.  A histogram's y is the
       count and may not be declared.
   * - ``hue``
     - no
     - non-empty string
     - The grouping column: one trace per distinct value, colored
       from the theme's series palette in first-appearance order.
       Refused together with ``color`` — grouping owns the color
       story.
   * - ``color``
     - no — default ``series-1``
     - theme token or ``series-N``
     - The single-trace color, resolved from the report's theme —
       never a literal.
   * - ``sep``
     - no — default ``"\t"``
     - single character
     - The field delimiter, as in ``core.table``.
   * - ``grid``
     - no — default ``true``
     - boolean
     - The axis grid, both axes together.
   * - ``log_x``, ``log_y``
     - no — default ``false``
     - boolean
     - Log-scale the axis.  Nonpositive values are refused at data
       time — Plotly silently drops them on log axes, and the
       report does not quietly lose data.
   * - ``caption``
     - no
     - non-empty string
     - Author prose under the figure.

Per-chart consistency rules, all checked at parse time — the type
is data-independent, so a wrong combination teaches before any
data is read:

* ``scatter``, ``line``, and ``bar`` require both ``x`` and
  ``y``.
* ``histogram`` requires ``x`` and refuses ``y`` — it bins the
  column and counts the records.
* ``box`` requires ``y``; groups by one column — ``x`` or
  ``hue``, never both; and refuses ``log_x`` (its horizontal axis
  is categorical grouping; ``log_y`` transforms the values).

The honest-data split: the rows are data, read verbatim in file
order — the producer's order is the author's story; ``chart``,
``x``, ``y``, and ``hue`` are the plot's shape; ``color``,
``grid``, ``log_x``, and ``log_y`` are presentation; ``caption``
is authorship.  There is no ``header`` parameter: charts address
columns by name, so the first row is always the header (see
`Honest boundaries`_).

Semantics
---------

The five chart types
....................

* **scatter** — one point per record: ``y`` against ``x``.
* **line** — the points *and* the connections between them, in
  file order: a trend.
* **bar** — one bar per record: ``y`` as height over category
  ``x``.
* **histogram** — the distribution of ``x``: the column is binned
  and the records counted; the y axis is titled ``count``, and
  hue-grouped histograms overlay at reduced opacity so the groups
  read together.
* **box** — the distribution of ``y``: quartiles, median,
  outliers; optionally grouped by one column.

Grouping by ``hue``
...................

Each distinct value in the hue column is one trace, colored from
the theme's series palette in first-appearance order — the
producer's order is the story, and the legend tells it.  Empty
cells form their own group under a blank legend label.  When the
groups outnumber the palette the colors cycle, and an
informational note rides the report's diagnostics ledger,
suggesting more series colors in the theme.

Colors
......

Without ``hue``, one color story: a theme token or a
categorical-palette entry (``series-1`` … bounded by the palette's
length); the default is ``series-1``.  Grouped figures wear the
palette in order.  The figure's dressing is the theme's own:
transparent backgrounds so the card's surface shows through, the
computed ink for that surface, the border color for the grid, the
theme's body font — the figure never invents a palette.

The accessibility label
.......................

The figure's ``aria-label`` is inferred from the figure's own
facts — the type, the columns, the record count, the grouping —
and is never the author's job: *Bar chart of depth by sample_id,
3 bars, colored by status*.  A reader who cannot see the figure
still reads what it shows.

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
       ``parameters:``, a per-chart inconsistency, a column name
       the header does not carry, a non-numeric cell in a numeric
       role, a nonpositive value on a log axis, or a
       non-``core.tabular`` artifact
     - ``ValueError``
     - a plugin failure, collected and shown in place
   * - The run is partial: the artifact is undeclared, declared
       with a non-``complete`` status, its file is missing, or it
       carries a header but no data rows
     - ``ArtifactUnavailableError``
     - the unavailable notice card — a fact about the run
   * - The artifact lies about its shape: no header row, a blank
       header cell beyond the first, duplicate column names, or a
       ragged row
     - ``ArtifactReadError``
     - a plugin failure, collected and shown in place

Zero data rows is the chart's own unavailable: a headered file
with no rows is valid shape — the run produced no records — and
the notice says the chart needs at least one row of data.

The chart declares no css and no js.  The figure rides the
framework's figure channel: the marker div, the figure's
bootstrap, and Plotly.js itself, inlined exactly when the document
contains figures — a report without healthy chart placements
carries none of it.  Plotly is imported when the render runs, not
when the plugin loads: a chartless machine builds chartless
reports, and a placement that meets its absence teaches as an
environment failure with the fix in the message.

Honest boundaries
-----------------

* A chart always reads the first row as the header — a headerless
  file misreads its first data row as the header, complete and
  misread.  A file without a header row belongs to ``core.table``'s
  ``header: false``; the chart has no such policy, because it has
  no column names to fall back on.
* A uniformly wrong ``sep`` reads every line as one field; the
  chart then teaches ``x`` and ``y`` against the one-column header
  the misread produced.  Declare the file's actual delimiter —
  the same boundary ``core.table`` documents (see :doc:`table`).
* Log axes refuse what Plotly would silently drop: a nonpositive
  value teaches at data time, naming the first offender and
  offering the fix both ways — fix the data, or drop the axis.

Example
-------

A manifest declaration and a layout placement, together:

.. code-block:: json

   {
     "id": "samples",
     "type": "org.example.samples",
     "schema_version": "1.0.0",
     "path": "samples.tsv",
     "format": "core.tabular",
     "status": "complete"
   }

.. code-block:: yaml

   - id: core.chart
     title: Depth by sample
     parameters:
       artifact: org.example.samples
       chart: bar
       x: sample_id
       y: depth
       hue: status
