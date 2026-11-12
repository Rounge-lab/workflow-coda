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

import re
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from .artifact_store import JsonValue
from .components import PluginMetadata, ReportComponent

ENTRY_POINT_GROUP: Final[str] = "workflow_coda.plugins"
"""The entry-point group under which every report plugin registers."""


type GetPlugin = Callable[[], "ReportPlugin"]
"""The zero-argument entry-point callable every plugin package provides."""


_VERIFIER_FORMAT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?:json|txt|bytes|[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+)$"
)
"""Shape of a verifier's claimed format: one of the framework's
agnostic trio, or a namespaced dotted name (``core.tabular``,
``bio.newick``).  The trio is *constructible* here — reservation is
the registry's assembly law, not the declaration's, because the
teaching belongs where the collision is visible."""


@dataclass(frozen=True, slots=True)
class ArtifactVerifier:
    """One plugin's declared verifier for one artifact format.

    The contract behind ``workflow-coda verify``: *bytes in, record
    out*.  The caller owns file IO and computes the checksum over
    exactly the bytes passed here; the verifier checks what it can
    under the format's grammar plus the declared criteria —
    transport the verifier owns, exactly like component parameters —
    and returns its record, which rides the manifest as opaque
    transport.  A failure raises
    :class:`~workflow_coda.errors.VerificationError` with a teaching
    message; anything else it raises is a plugin bug.
    """

    format: str
    """The artifact format this verifier claims: one of the reserved
    trio (rejected at registry assembly if a plugin claims it) or a
    namespaced dotted name whose grammar lives in the owning
    plugin."""

    verify: Callable[[bytes, Mapping[str, JsonValue]], dict[str, JsonValue]]
    """The verify callable: the artifact's bytes and the declared
    criteria in, the verification record out.  Pass the function
    itself, not a call result."""

    def __post_init__(self) -> None:
        """Enforce the format shape and the callable."""
        if _VERIFIER_FORMAT_PATTERN.fullmatch(self.format) is None:
            raise ValueError(
                f"invalid artifact format {self.format!r}: must be one of "
                f"'json', 'txt', 'bytes', or a namespaced dotted name "
                f"(e.g. 'core.tabular', 'bio.newick')"
            )
        if not callable(self.verify):
            raise ValueError(
                f"the verifier for format {self.format!r} must be a "
                f"callable taking (data: bytes, criteria), got "
                f"{self.verify!r} — pass the function itself, not a "
                f"call result"
            )


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

    artifact_verifiers: tuple[ArtifactVerifier, ...] = ()
    """The plugin's artifact verifiers, one per namespaced format it
    owns.  Formats are a shared namespace, not plugin-prefixed by law
    (``bio.*`` may belong to any plugin that owns the grammar), so
    the construction check is uniqueness alone; the registry polices
    what spans plugins — cross-claims, and the reserved trio."""

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
        verifier_formats: list[str] = []
        for verifier in self.artifact_verifiers:
            if verifier.format in verifier_formats:
                raise ValueError(
                    f"plugin {self.metadata.id!r} declares two verifiers "
                    f"for format {verifier.format!r} — one verifier per "
                    f"format"
                )
            verifier_formats.append(verifier.format)
