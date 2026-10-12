"""Tests for the report plugin contract: assembly integrity."""

import pytest
from factories import make_component, make_metadata, make_plugin
from helpers import assert_frozen_dataclass

from workflow_coda.plugins import ENTRY_POINT_GROUP, ReportPlugin


def test_plugin_assembles_metadata_and_components() -> None:
    plugin = make_plugin()
    assert plugin.metadata.id == "example"
    assert [c.id for c in plugin.components] == ["example.quality"]


def test_plugin_preserves_component_order() -> None:
    # Discovery order is contract: the registry and the report builder
    # surface components in declaration order, not sorted or deduped.
    first = make_component(id="example.quality", title="First")
    second = make_component(id="example.overview", title="Second")
    plugin = ReportPlugin(
        metadata=make_metadata(),
        components=(first, second),
    )
    assert plugin.components == (first, second)


def test_plugin_requires_at_least_one_component() -> None:
    with pytest.raises(ValueError, match="declares no components"):
        ReportPlugin(metadata=make_metadata(), components=())


def test_plugin_rejects_foreign_prefix() -> None:
    with pytest.raises(ValueError, match="must start with the plugin id"):
        ReportPlugin(
            metadata=make_metadata(id="other"),
            components=(make_component(),),
        )


def test_plugin_rejects_duplicate_component_ids() -> None:
    duplicated = (
        make_component(id="example.quality"),
        make_component(id="example.quality", title="Second copy"),
        make_component(id="example.quality", title="Third copy"),
    )
    with pytest.raises(ValueError, match=r"component ids: 'example\.quality' x3"):
        ReportPlugin(metadata=make_metadata(), components=duplicated)


def test_entry_point_group_name() -> None:
    # The group name is contract: distributions hard-code it in their
    # [project.entry-points] tables.
    assert ENTRY_POINT_GROUP == "workflow_coda.plugins"


def test_plugin_value_semantics() -> None:
    first = make_plugin()
    second = make_plugin()
    assert first == second
    assert hash(first) == hash(second)


def test_plugin_is_frozen_and_slotted() -> None:
    plugin = make_plugin()
    assert_frozen_dataclass(plugin, "metadata")
    with pytest.raises(AttributeError):
        plugin.extra = "nope"  # type: ignore[attr-defined]


def test_plugin_rejects_empty_components_with_specific_message() -> None:
    # Pinned separately: the message points the author at the tuple,
    # not just at "components" the field.
    with pytest.raises(ValueError, match="declares no components"):
        ReportPlugin(
            metadata=make_metadata(),
            components=(),
        )
