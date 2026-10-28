"""Tests for the core plugin assembly: what workflow-coda ships.

The registry-facing contract: the entry point constructs a valid
plugin whose id, version, and component roster match the framework's
own metadata.  The components themselves are pinned in their
per-module test files (test_core_kpi.py, test_core_table.py)."""

from importlib import metadata

from workflow_coda.components import ComponentChrome
from workflow_coda.core.kpi import render_kpi
from workflow_coda.core.plugin import get_plugin
from workflow_coda.core.table import render_table


def test_core_plugin_identity() -> None:
    # The plugin the environment's entry point loads: the framework's
    # own id and version, with the KPI and table components wired to
    # their renderers.
    plugin = get_plugin()
    assert plugin.metadata.id == "core"
    assert plugin.metadata.name == "Core report components"
    assert plugin.metadata.version == metadata.version("workflow-coda")
    assert plugin.metadata.supported_schema_versions == frozenset({"0.2.0"})
    # The icon declaration: core ships the framework's icon set
    # through the same optional field third-party plugins use.
    assert plugin.metadata.icons_package == "workflow_coda.core"
    assert len(plugin.components) == 3
    kpi = plugin.components[0]
    assert kpi.id == "core.kpi"
    assert kpi.title == "Key metric"
    assert kpi.description == "One artifact-backed headline number."
    assert kpi.render is render_kpi
    assert kpi.chrome is ComponentChrome.TILE
    # Self-hosted page chrome: the card vocabulary ships through the
    # same channel third-party components use.
    assert kpi.css is not None
    assert ".coda-kpi {" in kpi.css
    assert kpi.js is None
    table = plugin.components[1]
    assert table.id == "core.table"
    assert table.title == "Table"
    assert table.description == (
        "One artifact-backed table, complete and unscripted, "
        "with sort, filter, and copy as enhancement."
    )
    assert table.render is render_table
    assert table.chrome is ComponentChrome.CARD
    # The js half of the channel's first consumer: the table ships
    # both halves — the controls bar stylesheet and the enhancement
    # script — each bannered with its own class vocabulary.
    assert table.css is not None
    assert ".coda-table__controls" in table.css
    assert table.js is not None
    assert ".coda-table" in table.js
    assert "coda-table--filtered" in table.js
    assert "Copy as TSV" in table.js


def test_core_plugin_constructs_fresh_each_call() -> None:
    # get_plugin is a factory, not a singletoon: every call yields an
    # independently usable plugin with the same identity.
    first = get_plugin()
    second = get_plugin()
    assert first.metadata.id == second.metadata.id
    assert first is not second
