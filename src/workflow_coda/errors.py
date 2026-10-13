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

The plugin family is raised by the registry when the installed plugin
environment is broken or a component id resolves to nothing.

Import exceptions from this module; do not import them from the modules
that raise them.
"""


class WorkflowCodaError(Exception):
    """Base class for all workflow-coda exceptions."""


class ManifestError(WorkflowCodaError):
    """A report manifest could not be read, parsed, or validated.

    Raised when a manifest file is unreadable, is not strict UTF-8, is not
    valid JSON, or does not conform to the manifest envelope contract.
    The original exception, when there is one, is attached as ``__cause__``.
    """


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


class PluginError(WorkflowCodaError):
    """Root of the plugin family: failures discovering, loading, or
    resolving report plugins and their components at report build time.

    Contrast with the plain ``ValueError`` raised by the component
    contracts: those fire at plugin authoring time, in the plugin
    author's own test run.  These fire while building a report, when
    only typed framework errors may reach the user.
    """


class PluginLoadError(PluginError):
    """A plugin entry point failed to import or did not yield a
    :class:`~workflow_coda.plugins.ReportPlugin`."""


class PluginConflictError(PluginError):
    """Two loaded plugins claim the same id, making the component
    namespace ambiguous."""


class ComponentUnavailableError(PluginError):
    """No loaded plugin offers the requested component id.

    The registry counterpart of :class:`ArtifactUnavailableError`: an
    expected-missing condition that report building can handle as
    policy rather than as a failure.
    """


class LayoutError(WorkflowCodaError):
    """A report layout could not be loaded or is not valid.

    The layout is the framework's human-authored input, so its loader
    raises this for every authoring failure — an unreadable file,
    invalid YAML, a duplicate mapping key, a document that is not a
    mapping, or a layout model violation — with a message naming the
    file and, wherever the format provides one, the location inside it.

    A single class, like :class:`ManifestError`: every instance has the
    same correction clock (fix the file), so nothing downstream needs
    to distinguish the failure kinds.

    The report builder raises the same error when a theme file or image
    asset *declared* in a valid layout cannot be loaded at build time:
    same correction clock — fix the file, then build again.
    """
