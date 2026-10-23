"""Artifact entry models for a report manifest.

Each artifact entry in the manifest JSON is parsed into an
:class:`ArtifactDeclaration`.

Declarations are manifest *data*: they describe where an artifact lives and
what it claims to be.  Resolving and reading artifact contents is the job of
the artifact store (``workflow_coda.artifact_store``), which resolves ``path``
against the manifest location and verifies checksums when present.
"""

from enum import StrEnum
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, field_validator

from .types import (
    ArtifactId,
    ArtifactSchemaVersion,
    ArtifactType,
    ManifestRelativePath,
    NamespacedArtifactFormat,
    Sha256Hex,
)


class ArtifactFormat(StrEnum):
    """The framework's own artifact format values.

    Deliberately minimal and agnostic: ``json`` is an interpreted
    claim with a store reader; ``txt`` and ``bytes`` are
    interpretation-free claims — UTF-8 text and raw bytes — served
    by ``read_text`` and ``read_bytes`` for consumers with their own
    parsers.  Table-shaped and domain formats are claims their
    owners define: a plugin's artifacts are declared with its
    namespaced convention (``core.table``, ``bio.newick`` — see
    :data:`~workflow_coda.manifest.NamespacedArtifactFormat`), whose
    grammar lives in the owning plugin, never in the framework.
    """

    JSON = "json"
    TXT = "txt"
    BYTES = "bytes"


class ArtifactStatus(StrEnum):
    """Lifecycle status of a declared artifact.

    Only :attr:`COMPLETE` artifacts are guaranteed to be loadable.  The other
    statuses describe artifacts that a partial or failed run declared but did
    not fully produce; per the design docs these are expected missing data
    and must not be treated as fatal report-build errors.
    """

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    MISSING = "missing"


class ArtifactDeclaration(BaseModel):
    """A single artifact entry in a report manifest.

    This models the declaration only.  Filesystem containment, existence,
    and checksum verification happen when the artifact store resolves the
    declaration, since a declaration has no filesystem context on its own.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: ArtifactId
    """Unique identifier of the artifact within the manifest."""

    type: ArtifactType
    """Namespaced artifact type, e.g. ``org.example.sample_metrics``."""

    schema_version: ArtifactSchemaVersion
    """Version of the artifact's content schema."""

    path: ManifestRelativePath
    """Location of the artifact, relative to the manifest that declares it."""

    format: ArtifactFormat | NamespacedArtifactFormat
    """The artifact's format: a core value, or a namespaced plugin
    convention.  A claim, not a service — the store never dispatches
    on it; the reading component chooses its reader, and the plugin
    that owns a convention format (``core.table``, ``bio.newick``)
    reads and teaches it itself."""

    status: ArtifactStatus
    """Lifecycle status of the artifact."""

    sha256: Sha256Hex | None = None
    """Optional SHA-256 integrity checksum of the artifact file."""

    @field_validator("path")
    @classmethod
    def _validate_path_shape(cls, value: str) -> str:
        """Reject non-relative paths and paths that could escape the manifest."""
        if "\\" in value:
            raise ValueError(f"artifact path must use forward slashes, got {value!r}")
        path = PurePosixPath(value)
        if path.is_absolute():
            raise ValueError(f"artifact path must be relative, got {value!r}")
        if not path.parts:
            raise ValueError(f"artifact path must name a file, got {value!r}")
        if ".." in path.parts:
            raise ValueError(
                f"artifact path must not contain '..' segments, got {value!r}"
            )
        return value
