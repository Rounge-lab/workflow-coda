"""The report manifest envelope.

The manifest envelope declares the manifest schema version, identifies the producer, and
lists the artifact declarations.

The envelope's schema version is gated strictly: a manifest written for an unknown
version fails validation because an unrecognized envelope cannot be validated or
consumed correctly.  The supported version is enumerated by ``ManifestSchemaVersion``
— today, exactly ``0.2.0``, which widened the artifact ``format`` value space to
include namespaced plugin formats; the pre-widening ``0.1.0`` envelope is not read.
"""

from collections import Counter
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from .artifact import ArtifactDeclaration
from .types import NonEmptyStr

# Manifest envelope contract versions accepted by the report framework
type ManifestSchemaVersion = Literal["0.2.0"]

MANIFEST_SCHEMA_VERSION: Final[str] = "0.2.0"
"""The manifest envelope contract version this framework reads and
writes — the axis's single source of truth.  The loader's version
pre-check, the core plugin's declared support, the manifest
factories, and the verify writer all read this constant;
``ManifestSchemaVersion`` beside it is the type-checker's gate, and
the two are pinned in agreement (``tests/test_version_constants.py``).
Bumping the envelope is a clean break: flip this constant and the
Literal together, then green the sweep the flip reddens."""


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
    def _validate_unique_artifact_keys(
        cls, value: tuple[ArtifactDeclaration, ...]
    ) -> tuple[ArtifactDeclaration, ...]:
        """Reject duplicate artifact ids and duplicate artifact types.

        Ids must be unique because they identify artifacts within the
        manifest; types must be unique because the artifact store resolves
        artifacts by type (``require``), where two declarations of the same
        type would make lookup ambiguous.  Both problems are collected and
        reported together so a malformed manifest surfaces every collision
        at once.
        """
        problems: list[str] = []
        id_counts: Counter[str] = Counter(artifact.id for artifact in value)
        duplicated_ids = sorted(id_ for id_, count in id_counts.items() if count > 1)
        if duplicated_ids:
            details = ", ".join(f"{id_!r} x{id_counts[id_]}" for id_ in duplicated_ids)
            problems.append(f"duplicate artifact ids in manifest: {details}")
        type_counts: Counter[str] = Counter(artifact.type for artifact in value)
        duplicated_types = sorted(
            type_ for type_, count in type_counts.items() if count > 1
        )
        if duplicated_types:
            details = ", ".join(
                f"{type_!r} x{type_counts[type_]}" for type_ in duplicated_types
            )
            problems.append(f"duplicate artifact types in manifest: {details}")
        if problems:
            raise ValueError("; ".join(problems))
        return value
