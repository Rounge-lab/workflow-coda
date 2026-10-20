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
