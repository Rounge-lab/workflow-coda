"""Manifest data models for the workflow-coda report framework.

The manifest is the stable interface between an artifact producer (e.g.
workflow manager) and the report framework. Import models from this package
directly. The submodule layout is an implementation detail and may change
without notice.
"""

from .artifact import ArtifactDeclaration, ArtifactFormat, ArtifactStatus
from .envelope import (
    ManifestSchemaVersion,
    ProducerMetadata,
    ReportManifest,
)
from .loader import load_manifest
from .types import (
    ArtifactId,
    ArtifactSchemaVersion,
    ArtifactType,
    ManifestRelativePath,
    NonEmptyStr,
    Sha256Hex,
)

__all__ = [
    "ArtifactDeclaration",
    "ArtifactFormat",
    "ArtifactId",
    "ArtifactSchemaVersion",
    "ArtifactStatus",
    "ArtifactType",
    "ManifestRelativePath",
    "ManifestSchemaVersion",
    "NonEmptyStr",
    "ProducerMetadata",
    "ReportManifest",
    "Sha256Hex",
    "load_manifest",
]
