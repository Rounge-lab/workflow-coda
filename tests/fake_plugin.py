"""A minimal, importable report plugin for entry-point loading tests.

This module is the reference "smallest possible plugin": a ``get_plugin``
function returning a :class:`~workflow_coda.plugins.ReportPlugin`,
registered under an entry point whose value is
``fake_plugin:get_plugin``.  The deliberately broken variants exercise the
registry's load-failure paths.
"""

from workflow_coda.components import (
    ComponentParameters,
    PlacementInfo,
    PluginMetadata,
    RenderedComponent,
    ReportComponent,
)
from workflow_coda.context import RenderContext
from workflow_coda.plugins import ReportPlugin


def _render_noop(
    _context: RenderContext, _info: PlacementInfo, _parameters: ComponentParameters
) -> RenderedComponent:
    """The do-nothing renderer; every outcome is a skip."""
    return RenderedComponent.skipped()


def get_plugin() -> ReportPlugin:
    """A valid plugin whose ids are unique to this module."""
    return ReportPlugin(
        metadata=PluginMetadata(
            id="fake",
            name="Fake plugin",
            version="0.1.0",
            description="Entry-point loading test fixture.",
            supported_schema_versions=frozenset({"0.1.0"}),
        ),
        components=(
            ReportComponent(
                id="fake.loaded",
                title="Loaded component",
                render=_render_noop,
            ),
        ),
    )


def get_plugin_exploding() -> ReportPlugin:
    """Simulates a plugin whose construction fails at load time."""
    raise RuntimeError("plugin construction failed")


def get_wrong_type() -> object:
    """Simulates an entry point resolving to something that is not a plugin."""
    return None
