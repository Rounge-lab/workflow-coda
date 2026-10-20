"""Tests for the core plugin assembly: what workflow-coda ships.

The registry-facing contract: the entry point constructs a valid
plugin whose id, version, and component roster match the framework's
own metadata.  The components themselves are pinned in their
per-module test files (test_core_kpi.py)."""

from importlib import metadata

from workflow_coda.components import ComponentChrome
from workflow_coda.core.kpi import render_kpi
from workflow_coda.core.plugin import get_plugin


def test_core_plugin_identity() -> None:
    # The plugin the environment's entry point loads: the framework's
    # own id and version, with the KPI component wired to render.
    plugin = get_plugin()
    assert plugin.metadata.id == "core"
    assert plugin.metadata.name == "Core report components"
    assert plugin.metadata.version == metadata.version("workflow-coda")
    assert plugin.metadata.supported_schema_versions == frozenset({"0.2.0"})
    assert len(plugin.components) == 1
    component = plugin.components[0]
    assert component.id == "core.kpi"
    assert component.title == "Key metric"
    assert component.description == "One artifact-backed headline number."
    assert component.render is render_kpi
    assert component.chrome is ComponentChrome.TILE
    # Self-hosted page chrome: the card vocabulary ships through the
    # same channel third-party components use.
    assert component.css is not None
    assert ".coda-kpi {" in component.css
    assert component.js is None


def test_core_plugin_constructs_fresh_each_call() -> None:
    # get_plugin is a factory, not a singleton: every call yields an
    # independently usable plugin with the same identity.
    first = get_plugin()
    second = get_plugin()
    assert first.metadata.id == second.metadata.id
    assert first is not second
