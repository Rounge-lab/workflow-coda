"""Tests for the report document: the builder's output model."""

from dataclasses import replace

import pytest
from factories import make_manifest_payload
from helpers import assert_frozen_dataclass

from workflow_coda.components import ComponentChrome, RenderedComponent
from workflow_coda.manifest import ReportManifest
from workflow_coda.report import (
    CardEntry,
    ChromeContribution,
    ComponentEntry,
    Diagnostic,
    DiagnosticKind,
    DiagnosticsEntry,
    DocumentTab,
    EmbeddedAsset,
    EntryKind,
    GridEntry,
    InlineLogo,
    ReportDocument,
    RowEntry,
)
from workflow_coda.theme import DEFAULT_THEME


def rendered_entry(component_id: str = "example_bio.qc") -> ComponentEntry:
    """A valid rendered entry: the shape the builder emits on success."""
    return ComponentEntry(
        kind=EntryKind.RENDERED,
        component_id=component_id,
        title="Sample quality",
        outcome=RenderedComponent.from_html("<p>Rendered.</p>"),
    )


def failed_entry(component_id: str = "example_bio.qc") -> ComponentEntry:
    """A valid failed entry: the shape the builder emits on a plugin bug."""
    return ComponentEntry(
        kind=EntryKind.FAILED,
        component_id=component_id,
        title="Sample quality",
        error="ValueError: bad parameters",
    )


def make_asset(
    path: str = "assets/logo.png",
    media_type: str = "image/png",
    data_uri: str = "data:image/png;base64,iVBORw0KGgo=",
) -> EmbeddedAsset:
    """A valid embedded PNG asset; override any field."""
    return EmbeddedAsset(path=path, media_type=media_type, data_uri=data_uri)


def make_document(chrome: tuple[ChromeContribution, ...] = ()) -> ReportDocument:
    """A minimal complete document: one tab, one node, one
    informational diagnostic; *chrome* overrides the resolved page
    chrome."""
    return ReportDocument(
        title="Metagenomic analysis",
        author=None,
        version=None,
        subtitle=None,
        theme=DEFAULT_THEME,
        logo=None,
        favicon=None,
        manifest=ReportManifest.model_validate(make_manifest_payload()),
        tabs=(DocumentTab(title="Quality control", nodes=(rendered_entry(),)),),
        diagnostics=(
            Diagnostic(
                kind=DiagnosticKind.DEFAULT_THEME,
                subject=DEFAULT_THEME.name,
                message="no theme file declared — rendered with the default",
            ),
        ),
        chrome=chrome,
    )


# ---------------------------------------------------------------------------
# Wire values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "member"),
    [("rendered", EntryKind.RENDERED), ("failed", EntryKind.FAILED)],
)
def test_entry_kind_wire_values(value: str, member: EntryKind) -> None:
    assert member.value == value
    assert EntryKind(value) is member


@pytest.mark.parametrize(
    ("value", "member"),
    [
        ("plugin_excluded", DiagnosticKind.PLUGIN_EXCLUDED),
        ("component_missing", DiagnosticKind.COMPONENT_MISSING),
        ("component_unavailable", DiagnosticKind.COMPONENT_UNAVAILABLE),
        ("plugin_bug", DiagnosticKind.PLUGIN_BUG),
        ("default_theme", DiagnosticKind.DEFAULT_THEME),
        ("logo_omitted", DiagnosticKind.LOGO_OMITTED),
        ("favicon_omitted", DiagnosticKind.FAVICON_OMITTED),
    ],
)
def test_diagnostic_kind_wire_values(value: str, member: DiagnosticKind) -> None:
    assert member.value == value
    assert DiagnosticKind(value) is member


# ---------------------------------------------------------------------------
# ComponentEntry pairing
# ---------------------------------------------------------------------------


def test_rendered_entry_round_trip() -> None:
    entry = rendered_entry()
    assert entry.kind is EntryKind.RENDERED
    assert entry.component_id == "example_bio.qc"
    assert entry.title == "Sample quality"
    assert entry.outcome is not None
    assert entry.outcome.html == "<p>Rendered.</p>"
    assert entry.error is None


def test_failed_entry_round_trip() -> None:
    entry = failed_entry()
    assert entry.kind is EntryKind.FAILED
    assert entry.error == "ValueError: bad parameters"
    assert entry.outcome is None


def test_rendered_entry_requires_its_outcome() -> None:
    with pytest.raises(ValueError, match="must carry its outcome"):
        ComponentEntry(
            kind=EntryKind.RENDERED,
            component_id="example_bio.qc",
            title="Sample quality",
        )


def test_rendered_entry_requires_a_real_outcome() -> None:
    # The hole the tightened guard closes: a render call returning
    # garbage must become a collected plugin bug at the boundary, not
    # a document that chokes the rendering layer later.
    with pytest.raises(ValueError, match="must be a RenderedComponent"):
        ComponentEntry(
            kind=EntryKind.RENDERED,
            component_id="example_bio.qc",
            title="Sample quality",
            outcome="ok",  # type: ignore[arg-type]
        )


def test_rendered_entry_takes_no_error() -> None:
    with pytest.raises(ValueError, match="takes no error"):
        ComponentEntry(
            kind=EntryKind.RENDERED,
            component_id="example_bio.qc",
            title="Sample quality",
            outcome=RenderedComponent.skipped(),
            error="should not be here",
        )


def test_failed_entry_requires_a_visible_error() -> None:
    with pytest.raises(ValueError, match="must carry a visible error message"):
        ComponentEntry(
            kind=EntryKind.FAILED,
            component_id="example_bio.qc",
            title="Sample quality",
        )
    with pytest.raises(ValueError, match="must carry a visible error message"):
        ComponentEntry(
            kind=EntryKind.FAILED,
            component_id="example_bio.qc",
            title="Sample quality",
            error="   ",
        )


def test_failed_entry_takes_no_outcome() -> None:
    with pytest.raises(ValueError, match="takes no outcome"):
        ComponentEntry(
            kind=EntryKind.FAILED,
            component_id="example_bio.qc",
            title="Sample quality",
            error="boom",
            outcome=RenderedComponent.skipped(),
        )


def test_entry_kind_must_be_a_member() -> None:
    with pytest.raises(ValueError, match="kind must be an EntryKind member"):
        ComponentEntry(
            kind="rendered",  # type: ignore[arg-type]
            component_id="example_bio.qc",
            title="Sample quality",
        )


def test_entries_compare_by_value_and_hash() -> None:
    assert rendered_entry() == rendered_entry()
    assert hash(rendered_entry()) == hash(rendered_entry())
    assert failed_entry() != rendered_entry()


def test_entries_are_frozen_and_slotted() -> None:
    entry = rendered_entry()
    assert_frozen_dataclass(entry, "title")
    with pytest.raises(AttributeError):
        entry.extra = "nope"  # type: ignore[attr-defined]


def test_component_entry_defaults_to_card_chrome() -> None:
    # The default keeps every CARD-era construction valid; TILE is a
    # declaration, never a surprise.
    assert rendered_entry().chrome is ComponentChrome.CARD


# ---------------------------------------------------------------------------
# EmbeddedAsset
# ---------------------------------------------------------------------------


def test_embedded_asset_round_trip() -> None:
    asset = make_asset()
    assert asset.path == "assets/logo.png"
    assert asset.media_type == "image/png"
    assert asset.data_uri.startswith("data:image/png;base64,")


def test_embedded_asset_requires_the_data_uri_prefix() -> None:
    with pytest.raises(
        ValueError, match="data URI must start with 'data:image/png;base64,'"
    ):
        make_asset(data_uri="https://example.com/logo.png")
    # The prefix must match the declared media type, not just any data URI.
    with pytest.raises(
        ValueError, match="data URI must start with 'data:image/jpeg;base64,'"
    ):
        make_asset(media_type="image/jpeg")


def test_embedded_asset_is_frozen_and_slotted() -> None:
    asset = make_asset()
    assert_frozen_dataclass(asset, "path")
    with pytest.raises(AttributeError):
        asset.extra = "nope"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# InlineLogo
# ---------------------------------------------------------------------------


def test_inline_logo_round_trip() -> None:
    logo = InlineLogo(source="core-arrow-up", markup='<svg viewBox="0 0 24 24"/>')
    assert logo.source == "core-arrow-up"
    assert logo.markup.startswith("<svg")
    assert logo.is_inline is True


def test_the_logo_branch_markers() -> None:
    # The template's dispatch: an inline logo is markup, an embedded
    # asset is a data URI — one marker property tells the two shapes
    # apart.
    assert make_asset().is_inline is False


def test_inline_logo_requires_visible_source_and_markup() -> None:
    with pytest.raises(
        ValueError, match="inline logo source must contain visible text"
    ):
        InlineLogo(source="   ", markup="<svg/>")
    with pytest.raises(
        ValueError, match="inline logo markup must contain visible markup"
    ):
        InlineLogo(source="core-arrow-up", markup="   ")


def test_inline_logo_is_frozen_and_slotted() -> None:
    logo = InlineLogo(source="core-arrow-up", markup="<svg/>")
    assert_frozen_dataclass(logo, "source")
    with pytest.raises(AttributeError):
        logo.extra = "nope"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Diagnostic
# ---------------------------------------------------------------------------


def test_diagnostic_round_trip() -> None:
    diagnostic = Diagnostic(
        kind=DiagnosticKind.PLUGIN_BUG,
        subject="example_bio.qc",
        message="rendering component 'example_bio.qc' raised ValueError: boom",
    )
    assert diagnostic.kind is DiagnosticKind.PLUGIN_BUG
    assert diagnostic.subject == "example_bio.qc"
    assert diagnostic.message.startswith("rendering component")


def test_diagnostic_requires_visible_subject_and_message() -> None:
    with pytest.raises(
        ValueError, match="diagnostic subject must contain visible text"
    ):
        Diagnostic(kind=DiagnosticKind.PLUGIN_BUG, subject="   ", message="m")
    with pytest.raises(
        ValueError, match="diagnostic message must contain visible text"
    ):
        Diagnostic(kind=DiagnosticKind.PLUGIN_BUG, subject="s", message="   ")


def test_diagnostic_is_frozen_and_slotted() -> None:
    diagnostic = Diagnostic(kind=DiagnosticKind.PLUGIN_BUG, subject="s", message="m")
    assert_frozen_dataclass(diagnostic, "subject")
    with pytest.raises(AttributeError):
        diagnostic.extra = "nope"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# DocumentTab
# ---------------------------------------------------------------------------


def test_tab_round_trip_and_rejects_empty_nodes() -> None:
    # The inversion from the old section rule: the builder now drops
    # emptied tabs, so a document tab always carries at least one
    # node — the model enforces what the walk guarantees.
    node_tab = DocumentTab(title="Quality control", nodes=(rendered_entry(),))
    assert node_tab.title == "Quality control"
    assert len(node_tab.nodes) == 1
    with pytest.raises(ValueError, match="a document tab takes at least one node"):
        DocumentTab(title="Empty", nodes=())


def test_tab_value_semantics() -> None:
    first = DocumentTab(title="QC", nodes=(rendered_entry(),))
    second = DocumentTab(title="QC", nodes=(rendered_entry(),))
    assert first == second
    assert hash(first) == hash(second)


def test_tab_is_frozen_and_slotted() -> None:
    node_tab = DocumentTab(title="QC", nodes=(rendered_entry(),))
    assert_frozen_dataclass(node_tab, "title")
    with pytest.raises(AttributeError):
        node_tab.extra = "nope"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Composition entries: markers, rows, grids, groups
# ---------------------------------------------------------------------------


def test_diagnostics_marker_is_an_empty_value() -> None:
    # The marker carries no data, so it cannot drift from the ledger
    # it points at; any two markers are the same value.
    assert DiagnosticsEntry() == DiagnosticsEntry()
    assert hash(DiagnosticsEntry()) == hash(DiagnosticsEntry())
    with pytest.raises(AttributeError):
        DiagnosticsEntry().extra = "nope"  # type: ignore[attr-defined]


def test_row_round_trip_and_optional_split() -> None:
    row = RowEntry(split=None, children=(rendered_entry(), rendered_entry()))
    assert row.split is None  # equal widths, decided at render time
    assert len(row.children) == 2


def test_row_rejects_empty_children() -> None:
    with pytest.raises(ValueError, match="a row entry takes at least one child"):
        RowEntry(split=(1.0, 1.0), children=())


def test_grid_round_trip_and_required_split() -> None:
    # A grid without column ratios is just a stack: the field is
    # required, not defaulted.
    with pytest.raises(TypeError):
        GridEntry(children=(rendered_entry(),))  # type: ignore[call-arg]
    grid = GridEntry(split=(1.0, 2.0), children=(rendered_entry(),) * 3)
    assert grid.split == (1.0, 2.0)
    assert len(grid.children) == 3


def test_grid_rejects_empty_children() -> None:
    with pytest.raises(ValueError, match="a grid entry takes at least one child"):
        GridEntry(split=(1.0, 1.0), children=())


def test_card_round_trip() -> None:
    card = CardEntry(
        title="Group",
        layout="row",
        split=(2.0, 1.0),
        children=(rendered_entry(), rendered_entry()),
    )
    assert card.title == "Group"
    assert card.layout == "row"
    assert card.split == (2.0, 1.0)
    assert len(card.children) == 2


def test_card_rejects_empty_children() -> None:
    with pytest.raises(ValueError, match="a card entry takes at least one child"):
        CardEntry(title=None, layout="stack", split=None, children=())


def test_composition_entries_compare_by_value() -> None:
    row = RowEntry(split=(1.0, 1.0), children=(rendered_entry(),))
    same = RowEntry(split=(1.0, 1.0), children=(rendered_entry(),))
    assert row == same
    assert hash(row) == hash(same)
    assert row != RowEntry(split=(2.0, 1.0), children=(rendered_entry(),))


def test_composition_entries_are_frozen_and_slotted() -> None:
    row = RowEntry(split=(1.0, 1.0), children=(rendered_entry(),))
    assert_frozen_dataclass(row, "split")
    card = CardEntry(
        title=None, layout="stack", split=None, children=(rendered_entry(),)
    )
    assert_frozen_dataclass(card, "layout")
    with pytest.raises(AttributeError):
        row.extra = "nope"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# ChromeContribution: the resolved page chrome the document carries
# ---------------------------------------------------------------------------


def make_contribution(
    component_id: str = "example_bio.qc",
    css: str | None = ".coda-example_bio-qc { color: inherit; }",
    js: str | None = None,
) -> ChromeContribution:
    """A valid resolved contribution; override any field."""
    return ChromeContribution(component_id=component_id, css=css, js=js)


def test_contribution_round_trip() -> None:
    # The value is already-guarded, resolved chrome: the document
    # carries it verbatim, and the model interprets nothing of it.
    # All three legal shapes: css alone, js alone, both.
    css_only = make_contribution()
    assert css_only.component_id == "example_bio.qc"
    assert css_only.css == ".coda-example_bio-qc { color: inherit; }"
    assert css_only.js is None
    js_only = ChromeContribution(
        component_id="core.table", js="console.log('core.table enhanced');"
    )
    assert js_only.css is None
    assert js_only.js == "console.log('core.table enhanced');"
    both = ChromeContribution(
        component_id="core.kpi",
        css=".coda-kpi { color: inherit; }",
        js="console.log('core.kpi enhanced');",
    )
    assert both.css == ".coda-kpi { color: inherit; }"
    assert both.js == "console.log('core.kpi enhanced');"


def test_a_contribution_carries_at_least_one_of_css_and_js() -> None:
    # The builder's collection predicate guarantees this by
    # construction; the model states its own invariant at the value,
    # so a future producer that gets the predicate wrong fails loudly
    # at the construction site, not silently in the page.
    with pytest.raises(ValueError, match="carries at least one of css and js"):
        ChromeContribution(component_id="example_bio.qc")


def test_contributions_compare_by_value_and_hash() -> None:
    assert make_contribution() == make_contribution()
    assert hash(make_contribution()) == hash(make_contribution())
    assert make_contribution() != make_contribution(js="console.log('x');")
    assert make_contribution() != make_contribution(component_id="core.kpi")


def test_contribution_is_frozen_and_slotted() -> None:
    contribution = make_contribution()
    assert_frozen_dataclass(contribution, "component_id")
    with pytest.raises(AttributeError):
        contribution.extra = "nope"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# ReportDocument
# ---------------------------------------------------------------------------


def test_document_round_trip() -> None:
    document = make_document()
    assert document.title == "Metagenomic analysis"
    assert document.subtitle is None
    assert document.author is None
    assert document.version is None
    assert document.theme is DEFAULT_THEME
    assert document.logo is None
    assert document.favicon is None
    assert document.manifest == ReportManifest.model_validate(make_manifest_payload())
    assert document.chrome == ()
    (node_tab,) = document.tabs
    assert node_tab.title == "Quality control"
    (node,) = node_tab.nodes
    assert isinstance(node, ComponentEntry)
    assert node.kind is EntryKind.RENDERED
    (diagnostic,) = document.diagnostics
    assert diagnostic.kind is DiagnosticKind.DEFAULT_THEME


def test_document_carries_resolved_chrome() -> None:
    # The channel is opt-in end to end: the default document carries
    # no plugin chrome.  The tuple travels verbatim — dedup and
    # first-use order are the builder's, pinned there — and value
    # semantics mean a chromed document is not its chrome-less twin.
    assert make_document().chrome == ()
    contribution = make_contribution()
    chromed = make_document(chrome=(contribution,))
    assert chromed.chrome == (contribution,)
    assert chromed != make_document()


def test_documents_compare_by_value() -> None:
    # Equality only, deliberately: the document holds pydantic values
    # (theme, manifest) that are not hashable, so the document is not a
    # hash key — nothing needs it to be one.
    assert make_document() == make_document()


def test_document_is_frozen_and_slotted() -> None:
    document = make_document()
    assert_frozen_dataclass(document, "title")
    with pytest.raises(AttributeError):
        document.extra = "nope"  # type: ignore[attr-defined]


def test_document_carries_the_author_line() -> None:
    document = make_document()
    assert document.author is None
    authored = replace(document, author="The Genomics Group")
    assert authored.author == "The Genomics Group"
    assert authored != document


def test_document_carries_the_report_version() -> None:
    document = make_document()
    assert document.version is None
    versioned = replace(document, version="1.2.0")
    assert versioned.version == "1.2.0"
    assert versioned != document


def test_document_carries_the_header_color_token() -> None:
    # The styling-default contract: omission rides as None — the
    # renderer derives primary — and a declared token rides as
    # written, validated against the loaded theme upstream at build.
    document = make_document()
    assert document.header_color is None
    colored = replace(document, header_color="accent")
    assert colored.header_color == "accent"
    assert colored != document


def test_document_header_styling_defaults() -> None:
    document = ReportDocument(
        title="Report",
        subtitle=None,
        author=None,
        version=None,
        theme=DEFAULT_THEME,
        logo=None,
        favicon=None,
        manifest=ReportManifest.model_validate(make_manifest_payload()),
        tabs=(),
        diagnostics=(),
    )

    assert document.header_color is None
    assert document.header_variant == "fill"


def test_document_carries_gradient_header_styling() -> None:
    document = ReportDocument(
        title="Report",
        subtitle=None,
        author=None,
        version=None,
        theme=DEFAULT_THEME,
        logo=None,
        favicon=None,
        manifest=ReportManifest.model_validate(make_manifest_payload()),
        tabs=(),
        diagnostics=(),
    )
    gradient = replace(
        document,
        header_variant="gradient",
        header_color=("primary", "accent"),
    )

    assert gradient.header_variant == "gradient"
    assert gradient.header_color == ("primary", "accent")
    assert document.header_variant == "fill"
    assert document.header_color is None


@pytest.mark.parametrize(
    ("kind", "is_problem"),
    [
        (DiagnosticKind.PLUGIN_EXCLUDED, True),
        (DiagnosticKind.COMPONENT_MISSING, True),
        (DiagnosticKind.PLUGIN_BUG, True),
        (DiagnosticKind.COMPONENT_UNAVAILABLE, False),
        (DiagnosticKind.DEFAULT_THEME, False),
        (DiagnosticKind.LOGO_OMITTED, False),
        (DiagnosticKind.FAVICON_OMITTED, False),
    ],
)
def test_diagnostic_kinds_split_into_problems_and_notes(
    kind: DiagnosticKind, is_problem: bool
) -> None:
    # The placed diagnostics panel renders problems first, in the
    # danger color; informational notes after.  The enum carries the
    # split.
    assert kind.is_problem is is_problem
