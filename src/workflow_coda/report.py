"""The report document: the builder's output and the renderer's input.

The report builder turns a validated layout, a manifest's artifact
store, and the loaded plugin registry into a :class:`ReportDocument`
— the complete, resolved content of one report.  The document is the
hand-off contract between the report building and report rendering
layers: everything the rendering layer needs, and nothing it should
have to reconstruct.

Two properties shape the model:

**Registry-free.**  Component ids are resolved before the document
exists.  The document's *content tree* mirrors the layout's
composition: tabs hold nodes; row, grid, and card nodes hold children;
and every placement resolves into a :class:`ComponentEntry` carrying
what rendering needs — the resolved title and the render outcome or
failure — so rendering never consults the plugin registry again.  A
diagnostics node in the layout becomes a :class:`DiagnosticsEntry`
marker: the builder records the diagnostics themselves on the
document as it builds, and the renderer fills the marker from the
complete ledger — a plugin bug in the last tab exists by the time
rendering runs, wherever the marker sits.  The theme is loaded, and
the logo and favicon are already embedded as data URIs: the built
report is one self-contained page, holding no paths that only the
build machine could resolve.

**Degradation is still data.**  The outcome model continues unchanged:
a rendered component entry carries its
:class:`~workflow_coda.components.RenderedComponent` with the ``ok``,
``unavailable``, and ``skipped`` statuses intact, and a ``failed``
entry records a plugin bug the builder caught — the tree shows where
the component would have been, and diagnostics carry the details.
Unresolved placements produce no node at all: the ``on_missing``
policy has already turned them into a build failure or diagnostics.
Collapse travels upward: a composition whose children all resolve
away produces no node either, so empty rows, cards, and tabs drop
out of the document — the diagnostics already explain why.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Final

from .components import ComponentChrome, RenderedComponent
from .layout import CardLayoutKind
from .manifest import ReportManifest
from .text import has_visible_text
from .theme import Theme, ThemeToken


class EntryKind(Enum):
    """Why a component entry exists.

    ``RENDERED``
        The component's render call returned an outcome; the entry's
        ``outcome`` carries it, statuses intact.
    ``FAILED``
        The render call raised — a plugin bug.  The builder caught it,
        recorded the details in diagnostics, and placed this entry so
        the tree shows *where* the component would have been.
    """

    RENDERED = "rendered"
    FAILED = "failed"


class DiagnosticKind(Enum):
    """What a diagnostics entry is about.

    ``PLUGIN_EXCLUDED``, ``COMPONENT_MISSING``, and ``PLUGIN_BUG`` name
    problems: plugins gated out by the manifest's schema version,
    placements whose component id resolved to nothing under the
    ``notice`` policy, and render calls that raised.
    ``COMPONENT_UNAVAILABLE`` is a note: an omission under the on_unavailable: skip
    policy — the run, not the author, left the component's data absent; a note, because
    expected pipeline behavior.  ``DEFAULT_THEME``,
    ``LOGO_OMITTED``, and ``FAVICON_OMITTED`` are informational: the
    report is complete, and the message explains how to add what was
    left out.
    """

    PLUGIN_EXCLUDED = "plugin_excluded"
    COMPONENT_MISSING = "component_missing"
    PLUGIN_BUG = "plugin_bug"
    COMPONENT_UNAVAILABLE = "component_unavailable"
    DEFAULT_THEME = "default_theme"
    LOGO_OMITTED = "logo_omitted"
    FAVICON_OMITTED = "favicon_omitted"
    COMPONENT_NOTE = "component_note"

    @property
    def is_problem(self) -> bool:
        """Whether diagnostics of this kind name a problem — rendered
        in the problem group, in the danger color — versus
        informational notes, which explain omissions in an otherwise
        complete report."""
        return self in _PROBLEM_KINDS


_PROBLEM_KINDS: Final[frozenset[DiagnosticKind]] = frozenset(
    {
        DiagnosticKind.PLUGIN_EXCLUDED,
        DiagnosticKind.COMPONENT_MISSING,
        DiagnosticKind.PLUGIN_BUG,
    }
)
"""The kinds that name problems — mirrored from :class:`DiagnosticKind`'s
own docstring, which is the contract."""


@dataclass(frozen=True, slots=True)
class ComponentEntry:
    """One placed component's result within the tree.

    The field pairing is enforced: a ``RENDERED`` entry carries its
    outcome and no error; a ``FAILED`` entry carries a visible error
    message and no outcome.
    """

    kind: EntryKind
    """Whether the component rendered or its render call raised."""

    component_id: str
    """The placed component's globally unique id."""

    title: str
    """The resolved instance title: the placement's own when the layout
    names it, the component declaration's default otherwise."""

    chrome: ComponentChrome = ComponentChrome.CARD
    """Who painted this component's chrome: a ``CARD`` component is
    wrapped by the renderer in the framework's card vocabulary; a
    ``TILE`` component painted its own card, and the renderer
    contributes only the ``data-component`` wrapper.  Degradation —
    an unavailable or failed render — is the framework's own
    notice/failure vocabulary in both modes."""

    outcome: RenderedComponent | None = None
    """The render outcome; set if and only if kind is ``RENDERED``."""

    error: str | None = None
    """What the plugin's render call raised; set if and only if kind is
    ``FAILED``."""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EntryKind):
            raise ValueError(
                f"component entry {self.component_id!r}: kind must be an EntryKind member"
            )
        if self.kind is EntryKind.RENDERED:
            if self.outcome is None:
                raise ValueError(
                    f"component entry {self.component_id!r}: a rendered "
                    f"entry must carry its outcome"
                )
            if not isinstance(self.outcome, RenderedComponent):
                raise ValueError(
                    f"component entry {self.component_id!r}: a rendered "
                    f"entry's outcome must be a RenderedComponent"
                )
            if self.error is not None:
                raise ValueError(
                    f"component entry {self.component_id!r}: a rendered "
                    f"entry takes no error"
                )
        elif self.kind is EntryKind.FAILED:
            if self.error is None or not has_visible_text(self.error):
                raise ValueError(
                    f"component entry {self.component_id!r}: a failed entry "
                    f"must carry a visible error message"
                )
            if self.outcome is not None:
                raise ValueError(
                    f"component entry {self.component_id!r}: a failed entry "
                    f"takes no outcome"
                )


@dataclass(frozen=True, slots=True)
class DiagnosticsEntry:
    """A placed diagnostics panel: a marker the renderer fills.

    The builder records diagnostics on the document as it builds; this
    node only marks *where* the panel renders.  It carries no data, so
    the marker cannot drift out of sync with the ledger it points at.
    """


@dataclass(frozen=True, slots=True, kw_only=True)
class ChromeContribution:
    """One component's resolved page chrome, carried by the document.

    The builder collects these from the components whose placements
    rendered — deduplicated by component id, in first-use order — and
    the renderer inlines them: the ``css`` after the framework
    stylesheet, the ``js`` after the framework's own scripts.  The
    declaration (:class:`~workflow_coda.components.ReportComponent`)
    owns the guards — namespacing taught, blank and breakout
    sequences rejected — so this value is already-validated chrome,
    resolved into the document to keep the renderer a pure function
    of it.
    """

    component_id: str
    """The contributing component's id, ``<plugin_id>.<component_name>``,
    carried under the contribution's banner comment in the page."""

    css: str | None = None
    """The component's stylesheet contribution; ``None`` when it
    declared none."""

    js: str | None = None
    """The component's script contribution; ``None`` when it declared
    none."""

    def __post_init__(self) -> None:
        """A contribution carries at least one of css and js."""
        if self.css is None and self.js is None:
            raise ValueError(
                "a ChromeContribution carries at least one of css and "
                "js — a component without page chrome contributes nothing"
            )


@dataclass(frozen=True, slots=True)
class RowEntry:
    """A composed row: children side by side under width ratios."""

    split: tuple[float, ...] | None
    """One ratio per child, or ``None`` for equal widths."""

    children: tuple[DocumentNode, ...]

    def __post_init__(self) -> None:
        if not self.children:
            raise ValueError("a row entry takes at least one child")


@dataclass(frozen=True, slots=True)
class GridEntry:
    """A composed grid: children flowed row-major into ratio columns."""

    split: tuple[float, ...]
    """The column ratios."""

    children: tuple[DocumentNode, ...]

    def __post_init__(self) -> None:
        if not self.children:
            raise ValueError("a grid entry takes at least one child")


@dataclass(frozen=True, slots=True)
class CardEntry:
    """A composed card: a titled grouping with its own arrangement."""

    title: str | None
    """The grouping's optional title."""

    layout: CardLayoutKind
    """How the card arranges its children: stack, row, or grid."""

    split: tuple[float, ...] | None
    """The row or grid ratios; ``None`` for a stack or equal widths."""

    children: tuple[DocumentNode, ...]

    def __post_init__(self) -> None:
        if not self.children:
            raise ValueError("a card entry takes at least one child")


DocumentNode = ComponentEntry | DiagnosticsEntry | RowEntry | GridEntry | CardEntry
"""One node of the document's content tree, wherever nodes go."""


@dataclass(frozen=True, slots=True)
class DocumentTab:
    """One rendered report tab: its title and content tree, in order.

    The builder drops tabs whose trees collapse to nothing, so a
    document tab always carries at least one node.
    """

    title: str
    """The tab's heading — its label in the tab bar."""

    nodes: tuple[DocumentNode, ...]

    def __post_init__(self) -> None:
        if not self.nodes:
            raise ValueError("a document tab takes at least one node")


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

    @property
    def is_inline(self) -> bool:
        """The logo branch marker: a data URI, not inlined markup."""
        return False


@dataclass(frozen=True, slots=True)
class InlineLogo:
    """The report logo inlined as sanitized svg markup.

    The logo a theme can reach: an svg embedded as markup, not a
    data-URI ``<img>`` — an image is an isolated document whose
    ``currentColor`` resolves against the browser default, never the
    page.  Inline, the svg's ``currentColor`` fills and strokes
    resolve against the header's contrast-picked ink, so a logo
    authored for inheritance follows the theme while an explicitly
    colored one keeps its own.  The markup arrives sanitized through
    the icon validator's deny-by-default allowlists — the same
    boundary shipped icons pass — decorative and embed-ready.  Built
    from either source the layout's ``logo`` key addresses: a bundled
    icon by name or an SVG file by path.
    """

    source: str
    """The declared string as written: an icon name or a file path."""

    markup: str
    """The sanitized, embed-ready svg — raw into the page, guarded at
    build like other chrome."""

    @property
    def is_inline(self) -> bool:
        """The logo branch marker: inlined markup, not a data URI."""
        return True

    def __post_init__(self) -> None:
        if not has_visible_text(self.source):
            raise ValueError("inline logo source must contain visible text")
        if not has_visible_text(self.markup):
            raise ValueError("inline logo markup must contain visible markup")


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One line of the report's diagnostics ledger.

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
class ReportDocument:
    """One complete report: identity, theme, assets, tabs,
    diagnostics.

    Every field is resolved and render-ready: the theme is loaded,
    the assets are embedded, the manifest reference carries the
    provenance the footer renders, and tabs hold the walked content
    tree in layout order.  Nothing here reaches back to the
    filesystem or the plugin registry at render time.
    """

    title: str
    """The report's title, from the layout."""

    subtitle: str | None
    """The optional subtitle, from the layout."""

    author: str | None
    """The optional author line, from the layout."""

    version: str | None
    """The optional report version, from the layout."""

    theme: Theme
    """The loaded theme the report is rendered with."""

    logo: EmbeddedAsset | InlineLogo | None
    """The report's logo, or ``None`` when the layout declared none:
    a data-URI asset for raster files, inlined sanitized svg when the
    logo is a bundled icon or an SVG file — so currentColor-authored
    logos inherit the header's ink."""

    favicon: EmbeddedAsset | None
    """The embedded favicon, or ``None`` when the layout declared none."""

    manifest: ReportManifest
    """The report's validated manifest, for the provenance footer."""

    tabs: tuple[DocumentTab, ...]
    """The report's tabs, in layout order; each becomes one tab
    panel, and the tab bar is generated from them."""

    diagnostics: tuple[Diagnostic, ...]
    """Everything noteworthy the builder recorded, in occurrence
    order — rendered wherever the layout places a diagnostics node."""

    chrome: tuple[ChromeContribution, ...] = ()
    """The resolved page chrome: one contribution per component that
    declared css or js and rendered at least one placement ``OK`` —
    deduplicated by component id, in first-use order.  The renderer
    inlines the stylesheets after the framework's own and the scripts
    after the framework's.  Empty by default: a document built from
    chrome-less components inlines no plugin chrome at all."""

    header_color: ThemeToken | None = None
    """The header color's theme token as declared in the layout, or
    ``None`` for the ``primary`` default.  Validated against the
    theme at build; the renderer derives the bar's background and
    its contrast-picked ink from it, unless the theme itself declares
    the ``header-background`` / ``header-text`` tokens — a declared
    token wins, the ``--coda-text`` precedent."""
