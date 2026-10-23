"""The framework's core plugin: the generally useful, field-agnostic
components that ship with workflow-coda itself.

Assembly lives here so each component module stays a pure
implementation.  :func:`get_plugin` is the entry point the registry
loads; the framework's own version is the plugin's version, read from
the installed package metadata so pyproject stays the single source
of truth.

Core components may declare page chrome; ``core.kpi`` self-hosts its
card styles through the component channel — the framework's own
roster proving the contract third-party plugins will rely on.
"""

from importlib import metadata
from typing import Final

from ..components import ComponentChrome, PluginMetadata, ReportComponent
from ..plugins import ReportPlugin
from .kpi import render_kpi
from .table import render_table

_KPI_CSS: Final[str] = """\
/* One headline number as its own card: the KPI is a TILE component,
   so it paints everything — title, value, plate, corners — and
   these rules are its paint.  The default is the surface card look;
   fill and gradient variants override background and ink inline,
   and their plate reaches every edge because the KPI *is* the card.
   Inlined after the framework stylesheet exactly when a KPI
   placement rendered. */
.coda-kpi {
  position: relative; /* the corner icon pins against it */
  background: var(--coda-surface);
  border: 1px solid var(--coda-border);
  border-radius: 6px;
  padding: 1rem 1.25rem;
}

.coda-kpi__title {
  font-family: var(--coda-font-heading);
  font-size: 1.1rem;
  margin: 0 0 0.5rem;
}

.coda-kpi__value {
  margin: 0;
  font-family: var(--coda-font-heading);
  font-size: 2.25rem;
  font-weight: 700;
  line-height: 1.1;
}

.coda-kpi__unit {
  font-size: 0.45em; /* relative to the value: shrinks with it */
  font-weight: 500;
  opacity: 0.85;
}

.coda-kpi__caption {
  margin: 0.35rem 0 0;
  font-size: 0.875rem;
  color: var(--coda-muted);
}

/* The corner icon sits in the card's top right, scaled up and dimmed. */
.coda-kpi__corner {
  position: absolute;
  top: 0.4rem;
  right: 0.5rem;
  font-size: 1.5rem;
  line-height: 1;
  opacity: 0.6;
}

/* On a plate, the caption rides the computed ink. */
.coda-kpi--fill .coda-kpi__caption,
.coda-kpi--gradient .coda-kpi__caption {
  color: inherit;
  opacity: 0.85;
}
"""
"""core.kpi's page chrome: the card vocabulary for the tile it paints.

Self-hosted through the same channel third-party components use —
the framework's own roster proving the contract — and legal because
core owns bare ``coda-*`` names."""


_KPI = ReportComponent(
    id="core.kpi",
    title="Key metric",
    description="One artifact-backed headline number.",
    render=render_kpi,
    chrome=ComponentChrome.TILE,
    css=_KPI_CSS,
)
"""The core plugin's kpi component"""


_TABLE_CSS: Final[str] = """\
/* core.table */

.coda-table__controls {
  display: none;
}

.coda-js .coda-table__controls {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
  padding: 0 0 0.75rem;
  font-size: 0.9em;
}

.coda-table__filter,
.coda-table__copy {
  padding: 0.15rem 0.5rem;
  border: 1px solid var(--coda-border);
  border-radius: 4px;
  font: inherit;
  color: inherit;
  background: transparent;
}

.coda-table__copy {
  padding: 0.15rem 0.75rem;
  cursor: pointer;
}

.coda-table__copy:hover {
  background: var(--coda-accent);
  /* readable ink on the accent plate, as the KPI computes for the same pair */
  color: #ffffff;
}

.coda-table table {
  width: 100%;
  border-collapse: collapse;
  font-variant-numeric: tabular-nums;
}

.coda-table th,
.coda-table td {
  padding: 0.35rem 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--coda-border);
}

.coda-table thead th {
  border-bottom: 2px solid var(--coda-border);
  white-space: nowrap;
}

.coda-table thead th button {
  padding: 0;
  border: none;
  background: none;
  color: inherit;
  font: inherit;
  text-align: inherit;
  cursor: pointer;
}

.coda-js .coda-table thead th button::after {
  content: " ⇅";
  opacity: 0.4;
}

.coda-js .coda-table thead th[aria-sort="ascending"] button::after {
  content: " ▲";
  opacity: 1;
}

.coda-js .coda-table thead th[aria-sort="descending"] button::after {
  content: " ▽";
  opacity: 1;
}

.coda-table__caption {
  margin: 0.5rem 0 0;
  font-size: 0.9em;
  opacity: 0.75;
}

.coda-table--filtered {
  display: none;
}

@media print {
  .coda-js .coda-table__controls {
    display: none !important;
  }

  .coda-table--filtered {
    display: table-row !important;
  }

  .coda-js .coda-table thead th button::after {
    content: none !important;
  }
}
"""
"""The table component's stylesheet, inlined once per report through
the page-chrome channel.

Owns the ``coda-table`` vocabulary.  The controls bar is display-none
until the page is scripted (the framework's ``coda-js`` class gates
it), so nothing looks interactive that is not; the table's styling
draws only from theme tokens; sort-state arrows ride ``aria-sort``
pseudo-content, invisible without scripting; filter-hidden rows hide
by class, never by deletion.  The print block honors the panels law —
controls gone, hidden rows restored, arrows dropped — so the printed
page shows the complete table in its current order.  The container
itself never scrolls: the framework card body's own ``overflow-x``
rule owns wide tables, per the CARD-mode ruling."""

_TABLE_JS: Final[str] = """\
/* core.table */
(function () {
  "use strict";

  var HIDDEN = "coda-table--filtered";
  var COPY_LABEL = "Copy as TSV";
  var UNAVAILABLE = "copy unavailable in this browser";
  var FEEDBACK_MS = 1500;

  function field(text) {
    if (/[\t\n\r"]/.test(text)) {
      return '"' + text.replace(/"/g, '""') + '"';
    }
    return text;
  }

  function enhance(root) {
    var table = root.querySelector("table");
    if (!table || !table.tHead || !table.tBodies.length) {
      return;
    }
    var tbody = table.tBodies[0];
    var filterInput = root.querySelector(".coda-table__filter");
    var copyButton = root.querySelector(".coda-table__copy");
    var headers = table.tHead.rows[0].cells;
    var original = [];
    var feedbackTimer = null;
    var i;
    for (i = 0; i < tbody.rows.length; i += 1) {
      original.push(tbody.rows[i]);
    }

    function cellText(row, index) {
      return row.cells[index].textContent.trim();
    }

    function rowText(row) {
      var parts = [];
      var j;
      for (j = 0; j < row.cells.length; j += 1) {
        parts.push(row.cells[j].textContent);
      }
      return parts.join("\n").toLowerCase();
    }

    function applySort(index, direction) {
      var rows = original.slice(0);
      var numeric;
      var th;
      var j;
      for (j = 0; j < headers.length; j += 1) {
        headers[j].removeAttribute("aria-sort");
      }
      if (index < 0) {
        for (j = 0; j < rows.length; j += 1) {
          tbody.appendChild(rows[j]);
        }
        return;
      }
      th = headers[index];
      th.setAttribute("aria-sort", direction > 0 ? "ascending" : "descending");
      numeric = th.getAttribute("data-type") === "numeric";
      rows.sort(function (a, b) {
        var av = cellText(a, index);
        var bv = cellText(b, index);
        var diff;
        if (av === "" || bv === "") {
          if (av === "" && bv === "") {
            return 0;
          }
          return av === "" ? 1 : -1;
        }
        if (numeric) {
          diff = Number(av) - Number(bv);
        } else {
          diff = av.localeCompare(bv);
        }
        return direction * diff;
      });
      for (j = 0; j < rows.length; j += 1) {
        tbody.appendChild(rows[j]);
      }
    }

    var sortIndex = -1;
    var sortDirection = 0;

    function onHeaderClick(index) {
      if (sortIndex !== index) {
        sortIndex = index;
        sortDirection = 1;
      } else if (sortDirection > 0) {
        sortDirection = -1;
      } else {
        sortIndex = -1;
        sortDirection = 0;
      }
      applySort(sortIndex, sortDirection);
    }

    for (i = 0; i < headers.length; i += 1) {
      (function (th, index) {
        var button = document.createElement("button");
        button.type = "button";
        if (th.textContent.trim() === "") {
          button.setAttribute("aria-label", "Sort");
        }
        while (th.firstChild) {
          button.appendChild(th.firstChild);
        }
        th.appendChild(button);
        button.addEventListener("click", function () {
          onHeaderClick(index);
        });
      }(headers[i], i));
    }

    if (filterInput) {
      filterInput.addEventListener("input", function () {
        var query = filterInput.value.trim().toLowerCase();
        var j;
        for (j = 0; j < original.length; j += 1) {
          var matches = query === "" || rowText(original[j]).indexOf(query) !== -1;
          original[j].classList.toggle(HIDDEN, !matches);
        }
      });
    }

    if (copyButton) {
      var feedback = function (message) {
        copyButton.textContent = message;
        if (feedbackTimer !== null) {
          window.clearTimeout(feedbackTimer);
        }
        feedbackTimer = window.setTimeout(function () {
          copyButton.textContent = COPY_LABEL;
          feedbackTimer = null;
        }, FEEDBACK_MS);
      };
      copyButton.addEventListener("click", function () {
        var lines = [];
        var cells = [];
        var count = 0;
        var j;
        var k;
        var row;
        for (j = 0; j < headers.length; j += 1) {
          cells.push(field(headers[j].textContent));
        }
        lines.push(cells.join("\t"));
        for (j = 0; j < tbody.rows.length; j += 1) {
          row = tbody.rows[j];
          if (row.classList.contains(HIDDEN)) {
            continue;
          }
          cells = [];
          for (k = 0; k < row.cells.length; k += 1) {
            cells.push(field(row.cells[k].textContent));
          }
          lines.push(cells.join("\t"));
          count += 1;
        }
        var text = lines.join("\n");
        if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
          navigator.clipboard.writeText(text).then(
            function () {
              feedback("Copied " + count + " rows");
            },
            function () {
              feedback(UNAVAILABLE);
            }
          );
        } else {
          feedback(UNAVAILABLE);
        }
      });
    }
  }

  var tables = document.querySelectorAll(".coda-table");
  for (var i = 0; i < tables.length; i += 1) {
    enhance(tables[i]);
  }
}());
"""
"""The table component's enhancement script, inlined once per report
through the page-chrome channel: the js half of the channel's first
consumer.

One independent enhancement per placed ``.coda-table``.  Sort is a
three-state cycle per column — ascending, descending, original file
order — so the authored order is always one click away, told on the
``th`` through ``aria-sort``; numeric columns sort by value and text
by ``localeCompare``, per the build-time ``data-type`` stamps, which
the script consumes and never re-derives; empty cells sink to the
bottom in both directions, absent data rather than extremes.  Filter
is a case-insensitive substring over each row's cells, hiding rows by
class and never deleting them.  Copy exports the current view —
post-policy columns, sorted, filtered — as TSV through
``navigator.clipboard``, quoting cells per the csv dialect, with
honest feedback both ways and the button restored after a moment.
The sort affordance is created at runtime by wrapping each header's
text in a real button, so a page without scripting shows plain text
headers; a header without visible text (the index column) gets an
explicit label so its button is not nameless.  House dialect:
strict-mode IIFE, ``var``, no dependencies, no network."""


_TABLE: Final[ReportComponent] = ReportComponent(
    id="core.table",
    title="Table",
    description="One artifact-backed table, complete and unscripted, "
    "with sort, filter, and copy as enhancement.",
    render=render_table,
    chrome=ComponentChrome.CARD,
    css=_TABLE_CSS,
    js=_TABLE_JS,
)
"""The core plugin's table component"""


def get_plugin() -> ReportPlugin:
    """The core plugin: workflow-coda's own components."""
    return ReportPlugin(
        metadata=PluginMetadata(
            id="core",
            name="Core report components",
            version=metadata.version("workflow-coda"),
            description=(
                "Generally useful report components shipped with "
                "workflow-coda: headline metrics, and more as the core "
                "grows."
            ),
            supported_schema_versions=frozenset({"0.2.0"}),
        ),
        components=(_KPI, _TABLE),
    )
