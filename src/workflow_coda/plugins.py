"""The plugin contract and entry-point convention for report plugins.

A report plugin is a value, not a class hierarchy: it declares its
identity (:class:`~workflow_coda.components.PluginMetadata`) and the
components it offers (each a :class:`~workflow_coda.components.ReportComponent`
whose ``render`` callable produces its content), bundled in one frozen
:class:`ReportPlugin`.  There is no base class to subclass and no protocol
to implement — an extension package constructs the value in a small
``get_plugin`` function and exposes it through the
``workflow_coda.plugins`` entry-point group:

.. code-block:: toml

   [project.entry-points."workflow_coda.plugins"]
   example_bio = "example_bio_reports.plugin:get_plugin"

Registration-time integrity is enforced here, where the plugin is
assembled — component ids prefixed with the owning plugin's id, ids
unique within a plugin, at least one component — so an authoring mistake
fails in the plugin author's own test run, not as a mystery at report
time.  Cross-plugin concerns (duplicate ids *between* plugins, manifest
schema gating, lookup) belong to the registry.
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from .components import PluginMetadata, ReportComponent

type GetPlugin = Callable[[], "ReportPlugin"]
"""The zero-argument entry-point callable every plugin package provides."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ReportPlugin:
    """A report plugin: metadata plus the components it offers.

    The plugin value is inert data; the framework calls each component's
    ``render`` with the report's context and the component's layout
    parameters when building a report.
    """

    metadata: PluginMetadata
    """The plugin's identity and manifest-schema compatibility gate."""

    components: tuple[ReportComponent, ...]
    """The components this plugin offers."""

    def __post_init__(self) -> None:
        """Enforce registration-time integrity."""
        if not self.components:
            raise ValueError(f"plugin {self.metadata.id!r}: declares no components")
        prefix = f"{self.metadata.id}."
        for component in self.components:
            if not component.id.startswith(prefix):
                raise ValueError(
                    f"plugin {self.metadata.id!r}: component id "
                    f"{component.id!r} must start with the plugin id "
                    f"({prefix!r})"
                )
        counts = Counter(component.id for component in self.components)
        duplicated = sorted(id_ for id_, count in counts.items() if count > 1)
        if duplicated:
            details = ", ".join(f"{id_!r} x{counts[id_]}" for id_ in duplicated)
            raise ValueError(
                f"plugin {self.metadata.id!r}: duplicate component ids: {details}"
            )
