"""Typed exception hierarchy for workflow-coda.

Every exception the framework raises derives from :class:`WorkflowCodaError`,
so callers — above all the report builder — can catch the whole framework
surface with one ``except`` clause.

The hierarchy encodes a distinction that spans the whole system:

* *Expected unavailability* (e.g. :class:`ArtifactUnavailableError`) is a
  normal condition of partial runs; plugins catch it and render
  unavailable-state components.
* *Integrity violations* (e.g. :class:`ArtifactChecksumError`) indicate a
  broken or untrustworthy manifest or bundle and surface loudly.

Import exceptions from this module; do not import them from the modules
that raise them.
"""


class WorkflowCodaError(Exception):
    """Base class for all workflow-coda exceptions."""


class ArtifactStoreError(WorkflowCodaError):
    """Base class for artifact store failures."""


class ArtifactUnavailableError(ArtifactStoreError):
    """An artifact cannot be loaded because it is absent or incomplete.

    Raised when an artifact type is not declared in the manifest, is declared
    with a status other than ``complete``, or its file does not exist.  This
    is the expected condition in partial runs: plugins catch it to render an
    unavailable-state component instead of failing the report.
    """


class ArtifactResolutionError(ArtifactStoreError):
    """An artifact path resolves outside the manifest root, or is not a
    regular file.

    Manifest models already reject absolute paths and ``..`` segments at
    parse time, so this indicates a symbolic link escaping the manifest
    root — an integrity violation, not expected missing data.
    """


class ArtifactChecksumError(ArtifactStoreError):
    """An artifact's contents do not match its declared ``sha256``."""


class ArtifactReadError(ArtifactStoreError):
    """An artifact's contents could not be read, decoded, or parsed."""
