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
from .assets import read_core_asset
from .chart import render_chart
from .kpi import render_kpi
from .table import render_table

_KPI_CSS: Final[str] = read_core_asset("kpi.css")
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


_TABLE_CSS: Final[str] = read_core_asset("table.css")
"""The table component's stylesheet, inlined once per report through
the page-chrome channel.

Owns the ``coda-table`` vocabulary.  The controls bar is display-none
until the page is scripted (the framework's ``coda-js`` class gates
it), so nothing looks interactive that is not; the table's styling draws only from theme
tokens; sort-state icons ship in the stamped markup — one span per state beside every
column label, display-none until scripted, shown keyed on the th's aria-sort, which only
the scripted page writes; the controls bar rides icons — the filter field's permanent
decorative prefix and the square copy button, whose success state swaps its copy icon
for the framework's check icon by class; filter-hidden rows hide by class, never by
deletion.  The print block honors the panels law —
controls gone, hidden rows restored, sort icons dropped — so the printed
page shows the complete table in its current order.  The container
itself never scrolls: the framework card body's own ``overflow-x``
rule owns wide tables, per the CARD-mode ruling."""

_TABLE_JS: Final[str] = read_core_asset("table.js")
"""The table component's enhancement script, inlined once per report
through the page-chrome channel: the js half of the channel's first
consumer.

One independent enhancement per placed ``.coda-table``.  Sort is a three-state cycle per
column — ascending, descending, original file order — so the authored order is always
one click away, told on the ``th`` through ``aria-sort``; numeric columns sort by value
and text by ``localeCompare``, per the build-time ``data-type`` stamps, which the script
consumes and never re-derives; empty cells sink to the bottom in both directions, absent
data rather than extremes.  Filter is a case-insensitive substring over each row's
cells, hiding rows by class and never deleting them.  Copy exports the current view —
post-policy columns, sorted, filtered — as TSV through ``navigator.clipboard``, quoting
cells per the csv dialect, with honest feedback both ways — success swaps the button's
copy icon for the framework's check icon by class and announces the copied count to
screen readers through a visually hidden live region, a refusal shows its message as
text — and the button is restored after a moment.  The sort affordance is created at
runtime by wrapping each header's contents — label text and the build-time sort-state
spans alike — in a real button, so a page without scripting shows plain text headers; a
header without visible text (the index column) gets an explicit label so its button is
not nameless.  House dialect: strict-mode IIFE, ``var``, no dependencies, no network."""


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


_CHART: Final[ReportComponent] = ReportComponent(
    id="core.chart",
    title="Chart",
    description="One artifact-backed chart, rendered as an interactive Plotly figure.",
    render=render_chart,
    chrome=ComponentChrome.CARD,
)
"""The core plugin's chart component: core.tabular data as a
Plotly figure — the second reader of the tabular format, after
core.table."""


def get_plugin() -> ReportPlugin:
    """The core plugin: workflow-coda's own components."""
    return ReportPlugin(
        metadata=PluginMetadata(
            id="core",
            name="Core report components",
            version=metadata.version("workflow-coda"),
            description=(
                "Generally useful report components shipped with "
                "workflow-coda: headline metrics, tables, and charts."
            ),
            supported_schema_versions=frozenset({"0.2.0"}),
            icons_package="workflow_coda.core",
        ),
        components=(_KPI, _TABLE, _CHART),
    )
