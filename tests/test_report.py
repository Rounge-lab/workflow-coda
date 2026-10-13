"""Tests for the report document: the builder's output model."""

from dataclasses import replace

import pytest
from factories import make_manifest_payload
from helpers import assert_frozen_dataclass

from workflow_coda.components import RenderedComponent
from workflow_coda.manifest import ReportManifest
from workflow_coda.report import (
    Diagnostic,
    DiagnosticKind,
    DocumentSection,
    EmbeddedAsset,
    EntryKind,
    ReportDocument,
    SectionEntry,
)
from workflow_coda.theme import DEFAULT_THEME


def rendered_entry(component_id: str = "example_bio.qc") -> SectionEntry:
    """A valid rendered entry: the shape the builder emits on success."""
    return SectionEntry(
        kind=EntryKind.RENDERED,
        component_id=component_id,
        title="Sample quality",
        outcome=RenderedComponent.from_html("<p>Rendered.</p>"),
    )


def failed_entry(component_id: str = "example_bio.qc") -> SectionEntry:
    """A valid failed entry: the shape the builder emits on a plugin bug."""
    return SectionEntry(
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


def make_document() -> ReportDocument:
    """A minimal complete document: one section, one entry, one
    informational diagnostic."""
    return ReportDocument(
        title="Metagenomic analysis",
        subtitle=None,
        theme=DEFAULT_THEME,
        logo=None,
        favicon=None,
        manifest=ReportManifest.model_validate(make_manifest_payload()),
        sections=(
            DocumentSection(title="Quality control", entries=(rendered_entry(),)),
        ),
        diagnostics=(
            Diagnostic(
                kind=DiagnosticKind.DEFAULT_THEME,
                subject=DEFAULT_THEME.name,
                message="no theme file declared — rendered with the default",
            ),
        ),
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
# SectionEntry pairing
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
        SectionEntry(
            kind=EntryKind.RENDERED,
            component_id="example_bio.qc",
            title="Sample quality",
        )


def test_rendered_entry_requires_a_real_outcome() -> None:
    # The hole the tightened guard closes: a render call returning
    # garbage must become a collected plugin bug at the boundary, not
    # a document that chokes the rendering layer later.
    with pytest.raises(ValueError, match="must be a RenderedComponent"):
        SectionEntry(
            kind=EntryKind.RENDERED,
            component_id="example_bio.qc",
            title="Sample quality",
            outcome="ok",  # type: ignore[arg-type]
        )


def test_rendered_entry_takes_no_error() -> None:
    with pytest.raises(ValueError, match="takes no error"):
        SectionEntry(
            kind=EntryKind.RENDERED,
            component_id="example_bio.qc",
            title="Sample quality",
            outcome=RenderedComponent.skipped(),
            error="should not be here",
        )


def test_failed_entry_requires_a_visible_error() -> None:
    with pytest.raises(ValueError, match="must carry a visible error message"):
        SectionEntry(
            kind=EntryKind.FAILED,
            component_id="example_bio.qc",
            title="Sample quality",
        )
    with pytest.raises(ValueError, match="must carry a visible error message"):
        SectionEntry(
            kind=EntryKind.FAILED,
            component_id="example_bio.qc",
            title="Sample quality",
            error="   ",
        )


def test_failed_entry_takes_no_outcome() -> None:
    with pytest.raises(ValueError, match="takes no outcome"):
        SectionEntry(
            kind=EntryKind.FAILED,
            component_id="example_bio.qc",
            title="Sample quality",
            error="boom",
            outcome=RenderedComponent.skipped(),
        )


def test_entry_kind_must_be_a_member() -> None:
    with pytest.raises(ValueError, match="kind must be an EntryKind member"):
        SectionEntry(
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
# DocumentSection
# ---------------------------------------------------------------------------


def test_section_round_trip_and_permits_no_entries() -> None:
    section = DocumentSection(title="Quality control", entries=(rendered_entry(),))
    assert section.title == "Quality control"
    assert len(section.entries) == 1
    # Empty sections are model-legal: the notice policy can resolve away
    # every placement; dropping them is builder policy, tested there.
    assert DocumentSection(title="Empty", entries=()).entries == ()


def test_section_value_semantics() -> None:
    first = DocumentSection(title="QC", entries=(rendered_entry(),))
    second = DocumentSection(title="QC", entries=(rendered_entry(),))
    assert first == second
    assert hash(first) == hash(second)


def test_section_is_frozen_and_slotted() -> None:
    section = DocumentSection(title="QC", entries=(rendered_entry(),))
    assert_frozen_dataclass(section, "title")
    with pytest.raises(AttributeError):
        section.extra = "nope"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# ReportDocument
# ---------------------------------------------------------------------------


def test_document_round_trip() -> None:
    document = make_document()
    assert document.title == "Metagenomic analysis"
    assert document.subtitle is None
    assert document.theme is DEFAULT_THEME
    assert document.logo is None
    assert document.favicon is None
    assert document.manifest == ReportManifest.model_validate(make_manifest_payload())
    (section,) = document.sections
    assert section.title == "Quality control"
    (entry,) = section.entries
    assert entry.kind is EntryKind.RENDERED
    (diagnostic,) = document.diagnostics
    assert diagnostic.kind is DiagnosticKind.DEFAULT_THEME


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


def test_document_carries_the_toc_flag() -> None:
    document = make_document()
    assert document.toc is True
    without_toc = replace(document, toc=False)
    assert without_toc.toc is False
    assert without_toc != document
