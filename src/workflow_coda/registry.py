"""The installed-plugin registry: discovery, gating, and lookup.

The registry owns the plugin side of a report build.  It discovers every
plugin registered under the
:data:`~workflow_coda.plugins.ENTRY_POINT_GROUP` entry-point group,
assembles them into one component namespace, and answers the two
questions the report builder asks per report: which plugins understand
this manifest's schema version, and which component a given component
id refers to.

Registration integrity *within* a plugin (id prefixes, unique component
ids, at least one component) is enforced by
:class:`~workflow_coda.plugins.ReportPlugin` at its construction, so
this module only polices what spans plugins: two plugins claiming the
same id.  Component ids cannot collide across plugins without their
plugin ids colliding first — ids are ``<plugin_id>.<name>`` and
prefixes are enforced — but the registry re-checks while building the
lookup anyway, so a future drift of that invariant fails loudly here
instead of silently overwriting a lookup entry.

The registry models the *environment*, not a particular report: it does
not gate schema versions at construction.  The version gate is a
per-report question, answered by :meth:`PluginRegistry.plugins_supporting`
with the manifest's schema version.  Failures raise the
:class:`~workflow_coda.errors.PluginError` family.
"""

from collections import Counter
from collections.abc import Iterable
from importlib import metadata
from typing import Final, Self

from .components import ReportComponent
from .core.verifiers import FRAMEWORK_VERIFIERS
from .errors import (
    ComponentUnavailableError,
    PluginConflictError,
    PluginLoadError,
)
from .manifest import ArtifactFormat, ManifestSchemaVersion
from .plugins import ENTRY_POINT_GROUP, ArtifactVerifier, ReportPlugin

_RESERVED_FORMATS: Final[frozenset[str]] = frozenset(
    fmt.value for fmt in ArtifactFormat
)
"""The agnostic trio — the framework verifies its own formats, and a
plugin claiming one is taught the reservation at assembly, the same
moment cross-plugin collisions are."""


class PluginRegistry:
    """The installed report plugins and the component namespace they define."""

    def __init__(self, plugins: Iterable[ReportPlugin] = ()) -> None:
        """Assemble a registry, rejecting conflicting plugin identities."""
        self._plugins = tuple(plugins)
        id_counts = Counter(plugin.metadata.id for plugin in self._plugins)
        duplicated = sorted(id_ for id_, count in id_counts.items() if count > 1)
        if duplicated:
            details = ", ".join(f"{id_!r} x{id_counts[id_]}" for id_ in duplicated)
            raise PluginConflictError(
                f"multiple loaded plugins claim the same id: {details}"
            )
        self._by_id: dict[str, ReportComponent] = {}
        # The artifact-verifier index: the framework's trio first,
        # then the plugins' claims in discovery order.  The trio is
        # reserved, and one format has one verifier — the component-id
        # law in a second namespace, taught at the same assembly.
        claims = [
            (plugin.metadata.id, verifier)
            for plugin in self._plugins
            for verifier in plugin.artifact_verifiers
        ]
        for plugin_id, verifier in claims:
            if verifier.format in _RESERVED_FORMATS:
                raise PluginConflictError(
                    f"plugin {plugin_id!r} claims a verifier for format "
                    f"{verifier.format!r}, but that format is reserved: "
                    "the framework verifies json, txt, and bytes itself "
                    "— verify a namespaced format instead"
                )
        format_counts = Counter(verifier.format for _, verifier in claims)
        duplicated = sorted(fmt for fmt, count in format_counts.items() if count > 1)
        if duplicated:
            details = ", ".join(f"{fmt!r} x{format_counts[fmt]}" for fmt in duplicated)
            raise PluginConflictError(
                f"multiple loaded plugins claim the same format: {details}"
            )
        self._verifiers: tuple[ArtifactVerifier, ...] = FRAMEWORK_VERIFIERS + tuple(
            verifier for _, verifier in claims
        )
        for plugin in self._plugins:
            for component in plugin.components:
                if component.id in self._by_id:
                    raise PluginConflictError(
                        f"component id {component.id!r} is declared by more "
                        f"than one plugin (invariant drift: component ids "
                        f"are prefixed with unique plugin ids)"
                    )
                self._by_id[component.id] = component

    @classmethod
    def from_entry_points(cls, entry_points: Iterable[metadata.EntryPoint]) -> Self:
        """Load a registry from *entry_points*, wrapping every failure.

        Each entry point must resolve to a
        :data:`~workflow_coda.plugins.GetPlugin` callable that returns a
        :class:`~workflow_coda.plugins.ReportPlugin`.  Import failures,
        raising constructors, and wrong return types surface as
        :class:`~workflow_coda.errors.PluginLoadError` naming the entry
        point.
        """
        plugins: list[ReportPlugin] = []
        for entry_point in entry_points:
            try:
                get_plugin = entry_point.load()
                plugin = get_plugin()
            except Exception as e:
                raise PluginLoadError(
                    f"report plugin entry point {entry_point.name!r} "
                    f"failed to load: {e}"
                ) from e
            if not isinstance(plugin, ReportPlugin):
                raise PluginLoadError(
                    f"report plugin entry point {entry_point.name!r} "
                    f"returned {type(plugin).__name__!r}, expected a "
                    f"ReportPlugin"
                )
            plugins.append(plugin)
        return cls(plugins)

    @classmethod
    def load(cls) -> Self:
        """Discover and load every plugin in the current environment."""
        return cls.from_entry_points(metadata.entry_points(group=ENTRY_POINT_GROUP))

    @property
    def plugins(self) -> tuple[ReportPlugin, ...]:
        """Every loaded plugin, in discovery order."""
        return self._plugins

    @property
    def component_ids(self) -> frozenset[str]:
        """Every component id the loaded plugins offer."""
        return frozenset(self._by_id)

    def find_component(self, component_id: str) -> ReportComponent | None:
        """The component declaring *component_id*, or ``None``.

        Inspection only; :meth:`require_component` is the strict form.
        """
        return self._by_id.get(component_id)

    def require_component(self, component_id: str) -> ReportComponent:
        """The component declaring *component_id*.

        Raises :class:`~workflow_coda.errors.ComponentUnavailableError`
        when no loaded plugin declares it, listing the component ids
        that *are* available — the registry counterpart of the store's
        ``require``.
        """
        component = self._by_id.get(component_id)
        if component is None:
            available = ", ".join(sorted(self._by_id)) or "none"
            raise ComponentUnavailableError(
                f"no loaded plugin offers component {component_id!r} "
                f"(available: {available})"
            )
        return component

    def plugins_supporting(
        self, schema_version: ManifestSchemaVersion
    ) -> tuple[ReportPlugin, ...]:
        """The plugins that understand *schema_version*.

        The report builder calls this with the manifest's
        ``schema_version``; plugins outside the returned subset are
        excluded from the report and named in its diagnostics, together
        with the versions both sides support.
        """
        return tuple(
            plugin
            for plugin in self._plugins
            if schema_version in plugin.metadata.supported_schema_versions
        )

    @property
    def verifiers(self) -> tuple[ArtifactVerifier, ...]:
        """Every loaded artifact verifier: the framework's trio first,
        then the plugins' claims in discovery order."""
        return self._verifiers

    def verifiers_supporting(self, schema_version: str) -> tuple[ArtifactVerifier, ...]:
        """The verifiers usable when writing *schema_version*: the
        trio — the framework's own, ungated by any version — plus the
        claims of the plugins that understand the version, the same
        gate :meth:`plugins_supporting` applies to components.

        The verify command passes the manifest version it writes;
        typed ``str`` because the writer names the version, the
        loader does not gate it here.
        """
        return FRAMEWORK_VERIFIERS + tuple(
            verifier
            for plugin in self.plugins
            if schema_version in plugin.metadata.supported_schema_versions
            for verifier in plugin.artifact_verifiers
        )
