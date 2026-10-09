"""Manifest data models for the workflow-coda report framework.

The manifest is the stable interface between an artifact producer (e.g.
workflow manager) and the report framework. Import models from this package
directly. The submodule layout is an implementation detail and may change
without notice.
"""

from .artifact import ArtifactDeclaration, ArtifactFormat, ArtifactStatus
from .envelope import (
    SUPPORTED_MANIFEST_SCHEMA_VERSIONS,
    ProducerMetadata,
    ReportManifest,
)
from .types import (
    ArtifactId,
    ArtifactType,
    ManifestRelativePath,
    NonEmptyStr,
    SchemaVersion,
    Sha256Hex,
)

__all__ = [
    "ArtifactDeclaration",
    "ArtifactFormat",
    "ArtifactId",
    "ArtifactStatus",
    "ArtifactType",
    "ManifestRelativePath",
    "NonEmptyStr",
    "ProducerMetadata",
    "ReportManifest",
    "SUPPORTED_MANIFEST_SCHEMA_VERSIONS",
    "SchemaVersion",
    "Sha256Hex",
]
