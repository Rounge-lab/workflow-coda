"""The report manifest envelope.

The manifest envelope declares the manifest schema version, identifies the producer, and
lists the artifact declarations.

The envelope's schema version is gated strictly: a manifest written for an unknown
version fails validation because an unrecognized envelope cannot be validated or
consumed correctly.  The supported versions are enumerated by ``ManifestSchemaVersion``:
"""

from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from .artifact import ArtifactDeclaration
from .types import NonEmptyStr

# Manifest envelope contract versions accepted by the report framework
type ManifestSchemaVersion = Literal["0.1.0"]


class ProducerMetadata(BaseModel):
    """Identity of the system that produced a manifest and its artifacts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: NonEmptyStr
    """Human-readable name of the producing workflow or application."""

    version: NonEmptyStr
    """Version of the producer, e.g. a release number."""

    module_id: NonEmptyStr | None = None
    """Optional identifier of the specific workflow module that produced the artifacts."""

    run_id: NonEmptyStr | None = None
    """Optional identifier of the specific run that produced the artifacts."""


class ReportManifest(BaseModel):
    """Top-level envelope of a report manifest.

    The model enforces the envelope-level invariants that cannot live on a
    single artifact declaration:

    * the manifest schema version is one this framework supports, and
    * artifact ids and types are unique across the manifest.

    Filesystem concerns (path resolution, existence, checksum verification)
    belong to the artifact store, not to this data model.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: ManifestSchemaVersion
    """Version of the manifest envelope contract this file complies with."""

    producer: ProducerMetadata
    """The workflow or application that produced this manifest."""

    artifacts: tuple[ArtifactDeclaration, ...]
    """Artifact entries in declaration order. May be empty ([]) for a partial run."""

    @field_validator("artifacts")
    @classmethod
    def _validate_unique_ids(
        cls, value: tuple[ArtifactDeclaration, ...]
    ) -> tuple[ArtifactDeclaration, ...]:
        """Reject manifests that declare the same artifact id more than once."""
        counts: Counter[str] = Counter(artifact.id for artifact in value)
        duplicated = sorted(id_ for id_, count in counts.items() if count > 1)
        if duplicated:
            details = ", ".join(f"{id_!r} x{counts[id_]}" for id_ in duplicated)
            raise ValueError(f"duplicate artifact ids in manifest: {details}")
        return value

    @field_validator("artifacts")
    @classmethod
    def _validate_unique_types(
        cls, value: tuple[ArtifactDeclaration, ...]
    ) -> tuple[ArtifactDeclaration, ...]:
        """Reject manifests that declare the same artifact type more than once.

        The artifact store resolves artifacts *by type* (``require(type)``),
        so two declarations of the same type would make lookup ambiguous.
        Requiring type uniqueness keeps the store API single-valued.
        """
        counts: Counter[str] = Counter(artifact.type for artifact in value)
        duplicated = sorted(type_ for type_, count in counts.items() if count > 1)
        if duplicated:
            details = ", ".join(f"{type_!r} x{counts[type_]}" for type_ in duplicated)
            raise ValueError(f"duplicate artifact types in manifest: {details}")
        return value
