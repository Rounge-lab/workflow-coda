"""The framework's core plugin: the generally useful, field-agnostic
components that ship with workflow-coda itself.

Assembly lives here so each component module stays a pure
implementation.  :func:`get_plugin` is the entry point the registry
loads; the framework's own version is the plugin's version, read from
the installed package metadata so pyproject stays the single source
of truth.
"""

from importlib import metadata

from ..components import ComponentChrome, PluginMetadata, ReportComponent
from ..plugins import ReportPlugin
from .kpi import render_kpi

_KPI = ReportComponent(
    id="core.kpi",
    title="Key metric",
    description="One artifact-backed headline number.",
    render=render_kpi,
    chrome=ComponentChrome.TILE,
)
"""The core plugin's single component; the roster grows per milestone."""


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
            supported_schema_versions=frozenset({"0.1.0"}),
        ),
        components=(_KPI,),
    )
