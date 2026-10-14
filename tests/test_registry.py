"""Tests for the plugin registry: namespace assembly and lookup.

Entry-point loading (with the real ``fake_plugin`` module) and the
``PluginError`` family tests append in the next section.
"""

import re
from collections.abc import Iterable
from importlib import metadata

import pytest
from factories import make_component, make_metadata, make_plugin

from workflow_coda.errors import (
    ComponentUnavailableError,
    PluginConflictError,
    PluginError,
    PluginLoadError,
    WorkflowCodaError,
)
from workflow_coda.plugins import ENTRY_POINT_GROUP, ReportPlugin
from workflow_coda.registry import PluginRegistry


def distinct_plugin(
    id: str, supported_schema_versions: Iterable[str] = ("0.1.0",)
) -> ReportPlugin:
    """A valid plugin whose ids are unique to *id*.

    Registry tests assemble multiple plugins, and the factory defaults
    share one id, so distinct plugins override the metadata and
    component ids together — the paired-override pattern from the
    factory step.  Registry-test-local, so it stays out of factories.
    """
    return make_plugin(
        metadata=make_metadata(
            id=id, supported_schema_versions=supported_schema_versions
        ),
        components=(make_component(id=f"{id}.quality"),),
    )


def _force_set(obj: object, name: str, value: object) -> None:
    """Set *name* on *obj*, bypassing frozen ``__setattr__``.

    The single sanctioned use: simulating invariant drift that the
    public constructors make impossible, to exercise the registry's
    defensive re-check.
    """
    object.__setattr__(obj, name, value)


# ---------------------------------------------------------------------------
# Registry construction
# ---------------------------------------------------------------------------


def test_empty_registry_has_no_plugins_or_components() -> None:
    registry = PluginRegistry()
    assert registry.plugins == ()
    assert registry.component_ids == frozenset()


def test_registry_preserves_plugin_order() -> None:
    # Discovery order is contract: plugins surface in the order the
    # environment yielded them, not sorted.
    second = distinct_plugin("beta")
    first = distinct_plugin("alpha")
    registry = PluginRegistry((second, first))
    assert registry.plugins == (second, first)


def test_registry_rejects_duplicate_plugin_ids() -> None:
    with pytest.raises(
        PluginConflictError,
        match=r"multiple loaded plugins claim the same id: 'example' x2",
    ):
        PluginRegistry((make_plugin(), make_plugin()))


def test_registry_rejects_duplicate_component_ids_across_plugins() -> None:
    # Unreachable through the public API: ReportPlugin enforces its own
    # prefix, so distinct plugin ids cannot share component ids.  The
    # registry re-checks anyway so that future drift of that invariant
    # fails loudly here instead of silently overwriting a lookup entry.
    # Simulate the drift by mutating past the frozen __setattr__.
    drifter = distinct_plugin("other")
    _force_set(drifter.components[0], "id", "example.quality")
    with pytest.raises(PluginConflictError, match="invariant drift"):
        PluginRegistry((distinct_plugin("example"), drifter))


# ---------------------------------------------------------------------------
# Component lookup
# ---------------------------------------------------------------------------


def test_component_ids_collect_all_components() -> None:
    registry = PluginRegistry((distinct_plugin("example"), distinct_plugin("other")))
    assert registry.component_ids == frozenset({"example.quality", "other.quality"})


def test_find_component_returns_declaration_or_none() -> None:
    registry = PluginRegistry((distinct_plugin("example"),))
    component = registry.find_component("example.quality")
    assert component is not None
    assert component.id == "example.quality"
    assert registry.find_component("missing.nothing") is None


def test_require_component_returns_declaration() -> None:
    registry = PluginRegistry((distinct_plugin("example"),))
    assert registry.require_component("example.quality").id == "example.quality"


def test_require_component_lists_what_is_available() -> None:
    registry = PluginRegistry((distinct_plugin("example"), distinct_plugin("other")))
    with pytest.raises(
        ComponentUnavailableError,
        match=re.escape(
            "no loaded plugin offers component 'missing.nothing' "
            "(available: example.quality, other.quality)"
        ),
    ):
        registry.require_component("missing.nothing")


def test_require_component_on_empty_registry_says_none() -> None:
    with pytest.raises(ComponentUnavailableError, match=r"available: none"):
        PluginRegistry().require_component("anything.anything")


# ---------------------------------------------------------------------------
# Schema-version gating
# ---------------------------------------------------------------------------


def test_plugins_supporting_filters_by_manifest_schema_version() -> None:
    # ``ManifestSchemaVersion`` is a Literal: "0.1.0" is the only version
    # the manifest contract carries today, so the *query* side is fixed
    # and the plugin *declarations* provide the variation.  (Asking about
    # "0.2.0" is a type type system enforcing that only
    # manifest-carryable versions can be looked up, not something to
    # work around with a cast.)
    current = distinct_plugin("current")  # declares {"0.1.0"}
    also_current = distinct_plugin("also_current")  # declares {"0.1.0}
    stale = distinct_plugin("stale", ("0.0.9",))  # declares {"0.0.9"} only

    mixed = PluginRegistry((current, stale, also_current))
    # Non-matching plugins are excluded; matching ones keep discovery order.
    assert mixed.plugins_supporting("0.1.0") == (current, also_current)
    # A registry where nothing matches yields an empty tuple.
    transcribe_only = PluginRegistry((stale,))
    assert transcribe_only.plugins_supporting("0.1.0") == ()


# ---------------------------------------------------------------------------
# Entry-point loading
# ---------------------------------------------------------------------------


def test_from_entry_points_loads_a_real_plugin() -> None:
    ep = metadata.EntryPoint(
        name="fake", value="fake_plugin:get_plugin", group=ENTRY_POINT_GROUP
    )
    registry = PluginRegistry.from_entry_points([ep])
    assert [p.metadata.id for p in registry.plugins] == ["fake"]
    assert registry.component_ids == frozenset({"fake.loaded"})


def test_from_entry_points_wraps_missing_modules() -> None:
    ep = metadata.EntryPoint(
        name="missing",
        value="no_such_module_anywhere:get_plugin",
        group=ENTRY_POINT_GROUP,
    )
    with pytest.raises(PluginLoadError, match="failed to load"):
        PluginRegistry.from_entry_points([ep])


def test_from_entry_points_wraps_raising_constructors() -> None:
    ep = metadata.EntryPoint(
        name="exploding",
        value="fake_plugin:get_plugin_exploding",
        group=ENTRY_POINT_GROUP,
    )
    with pytest.raises(
        PluginLoadError, match="failed to load: plugin construction failed"
    ):
        PluginRegistry.from_entry_points([ep])


def test_from_entry_points_rejects_wrong_return_types() -> None:
    ep = metadata.EntryPoint(
        name="wrong",
        value="fake_plugin:get_wrong_type",
        group=ENTRY_POINT_GROUP,
    )
    with pytest.raises(PluginLoadError, match="expected a ReportPlugin"):
        PluginRegistry.from_entry_points([ep])


def test_load_reflects_the_installed_environment() -> None:
    # No plugins are installed in the test environment, so load() yields
    # an empty registry.  If the project ever ships its own extension
    # package, update this test to assert on it instead.
    registry = PluginRegistry.load()
    loaded_ids = {plugin.metadata.id for plugin in registry.plugins}
    assert loaded_ids >= {"core"}


# ---------------------------------------------------------------------------
# The plugin error family
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error_type",
    [PluginError, PluginLoadError, PluginConflictError, ComponentUnavailableError],
)
def test_plugin_errors_are_framework_errors(
    error_type: type[BaseException],
) -> None:
    # The family shape is contract: the CLI's handler catches the root
    # WorkflowCodaError, so every plugin-family failure is catchable
    # there, and the family keeps one inheritance line.
    assert issubclass(error_type, PluginError)
    assert issubclass(error_type, WorkflowCodaError)
