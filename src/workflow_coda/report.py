"""The report document: the builder's output and the renderer's input.

The report builder turns a validated layout, a manifest's artifact
store, and the loaded plugin registry into a :class:`ReportDocument`
— the complete, resolved content of one report.  The document is the
hand-off contract between the report building and report rendering
layers: everything the rendering layer needs, and nothing it should
have to reconstruct.

Two properties shape the model:

**Registry-free.**  Component ids are resolved before the document
exists.  Every section entry carries what rendering needs — the
component's declared title and its render outcome or failure — so
rendering never consults the plugin registry again.  The theme is
loaded, and the logo and favicon are already embedded as data URIs:
the built report is one self-contained page, holding no paths that
only the build machine could resolve.

**Degradation is still data.**  The outcome model continues unchanged:
a ``rendered`` entry carries its
:class:`~workflow_coda.components.RenderedComponent` with the ``ok``,
``unavailable``, and ``skipped`` statuses intact, and a ``failed``
entry records a plugin bug the builder caught — the section shows
where the component would have been, and diagnostics carry the
details.  Unresolved placements produce no entry at all: the
``on_missing`` policy has already turned them into a build failure
or diagnostics, so an entry exists for exactly the placements that
were rendered.
"""

from dataclasses import dataclass
from enum import Enum

from .components import RenderedComponent, has_visible_text
from .manifest import ReportManifest
from .theme import Theme


class EntryKind(Enum):
    """Why a section entry exists.

    ``RENDERED``
        The component's render call returned an outcome; the entry's
        ``outcome`` carries it, statuses intact.
    ``FAILED``
        The render call raised — a plugin bug.  The builder caught it,
        recorded the details in diagnostics, and placed this entry so
        the section shows *where* the component would have been.
    """

    RENDERED = "rendered"
    FAILED = "failed"


class DiagnosticKind(Enum):
    """What a diagnostics entry is about.

    ``PLUGIN_EXCLUDED``, ``COMPONENT_MISSING``, and ``PLUGIN_BUG`` name
    problems: plugins gated out by the manifest's schema version,
    placements whose component id resolved to nothing under the
    ``notice`` policy, and render calls that raised.  ``DEFAULT_THEME``,
    ``LOGO_OMITTED``, and ``FAVICON_OMITTED`` are informational: the
    report is complete, and the message explains how to add what was
    left out.
    """

    PLUGIN_EXCLUDED = "plugin_excluded"
    COMPONENT_MISSING = "component_missing"
    PLUGIN_BUG = "plugin_bug"
    DEFAULT_THEME = "default_theme"
    LOGO_OMITTED = "logo_omitted"
    FAVICON_OMITTED = "favicon_omitted"


@dataclass(frozen=True, slots=True)
class SectionEntry:
    """One placed component's result within a section.

    The field pairing is enforced: a ``RENDERED`` entry carries its
    outcome and no error; a ``FAILED`` entry carries a visible error
    message and no outcome.
    """

    kind: EntryKind
    """Whether the component rendered or its render call raised."""

    component_id: str
    """The placed component's globally unique id."""

    title: str
    """The component's declared title, for the card chrome."""

    outcome: RenderedComponent | None = None
    """The render outcome; set if and only if kind is ``RENDERED``."""

    error: str | None = None
    """What the plugin's render call raised; set if and only if kind is
    ``FAILED``."""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EntryKind):
            raise ValueError(
                f"section entry {self.component_id!r}: kind must be an EntryKind member"
            )
        if self.kind is EntryKind.RENDERED:
            if self.outcome is None:
                raise ValueError(
                    f"section entry {self.component_id!r}: a rendered "
                    f"entry must carry its outcome"
                )
            if not isinstance(self.outcome, RenderedComponent):
                raise ValueError(
                    f"section entry {self.component_id!r}: a rendered "
                    f"entry's outcome must be a RenderedComponent"
                )
            if self.error is not None:
                raise ValueError(
                    f"section entry {self.component_id!r}: a rendered "
                    f"entry takes no error"
                )
        elif self.kind is EntryKind.FAILED:
            if self.error is None or not has_visible_text(self.error):
                raise ValueError(
                    f"section entry {self.component_id!r}: a failed entry "
                    f"must carry a visible error message"
                )
            if self.outcome is not None:
                raise ValueError(
                    f"section entry {self.component_id!r}: a failed entry "
                    f"takes no outcome"
                )


@dataclass(frozen=True, slots=True)
class EmbeddedAsset:
    """An asset embedded into the single-page report as a data URI.

    The builder reads the declared file next to the layout file,
    checks that it is a recognizable image, and embeds its bytes;
    the document never carries a path the report reader's machine
    would have to resolve.
    """

    path: str
    """The declared path, as written in the layout file."""

    media_type: str
    """The detected image media type, e.g. ``image/png``."""

    data_uri: str
    """The embedded bytes as a ``data:<media_type>;base64,...`` URI."""

    def __post_init__(self) -> None:
        prefix = f"data:{self.media_type};base64,"
        if not self.data_uri.startswith(prefix):
            raise ValueError(
                f"embedded asset {self.path!r}: data URI must start with {prefix!r}"
            )


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One line of the report's diagnostics section.

    ``subject`` names what the diagnostic is about (a plugin id, a
    component id, an asset path); ``message`` is the complete
    human-facing sentence.  Message wording is builder policy; the
    model only guarantees visible text on both fields.
    """

    kind: DiagnosticKind
    subject: str
    """What the diagnostic is about: a plugin id, component id, or
    asset path."""

    message: str
    """The complete human-facing sentence."""

    def __post_init__(self) -> None:
        if not has_visible_text(self.subject):
            raise ValueError("diagnostic subject must contain visible text")
        if not has_visible_text(self.message):
            raise ValueError("diagnostic message must contain visible text")


@dataclass(frozen=True, slots=True)
class DocumentSection:
    """A rendered report section: its title and entries, in order.

    Entries may be empty: the ``notice`` policy can resolve away every
    placement in a section.  Whether the builder keeps or drops such a
    section is builder policy, not model policy.
    """

    title: str
    entries: tuple[SectionEntry, ...]


@dataclass(frozen=True, slots=True)
class ReportDocument:
    """One complete report: identity, theme, assets, sections,
    diagnostics.

    Every field is resolved and render-ready: the theme is loaded,
    the assets are embedded, the manifest reference carries the
    provenance the footer renders, and sections hold placed results in
    layout order.  Nothing here reaches back to the filesystem or the
    plugin registry at render time.
    """

    title: str
    """The report's title, from the layout."""

    subtitle: str | None
    """The optional subtitle, from the layout."""

    theme: Theme
    """The loaded theme the report is rendered with."""

    logo: EmbeddedAsset | None
    """The embedded logo, or ``None`` when the layout declared none."""

    favicon: EmbeddedAsset | None
    """The embedded favicon, or ``None`` when the layout declared none."""

    manifest: ReportManifest
    """The report's validated manifest, for the provenance footer."""

    sections: tuple[DocumentSection, ...]
    """The report's sections, in layout order."""

    diagnostics: tuple[Diagnostic, ...]
    """Everything noteworthy the builder recorded, in occurrence
    order."""

    toc: bool = True
    """Whether the rendered report includes the table of contents; a
    layout decision carried in the document so rendering needs
    nothing else."""
