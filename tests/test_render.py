"""Tests for the report renderer: the document in, the
self-contained page out."""

import importlib.resources
import sys
from html.parser import HTMLParser

import pytest
from factories import make_manifest_payload

from workflow_coda.components import FIGURE_DIV_CLASS, RenderedComponent
from workflow_coda.errors import RenderError
from workflow_coda.manifest import ArtifactStatus, ReportManifest
from workflow_coda.render import render_report
from workflow_coda.report import (
    Diagnostic,
    DiagnosticKind,
    DocumentSection,
    EmbeddedAsset,
    EntryKind,
    ReportDocument,
    SectionEntry,
)
from workflow_coda.theme import DEFAULT_THEME, Theme

# ---------------------------------------------------------------------------
# Fixtures: entries, assets, documents
# ---------------------------------------------------------------------------


def ok_entry(
    html: str = "<p>Rendered.</p>",
    component_id: str = "example_bio.qc",
    title: str = "Sample quality",
) -> SectionEntry:
    """A rendered entry: the shape a successful render produces."""
    return SectionEntry(
        kind=EntryKind.RENDERED,
        component_id=component_id,
        title=title,
        outcome=RenderedComponent.from_html(html),
    )


def figure_entry() -> SectionEntry:
    """A rendered entry carrying the framework figure marker — the
    detection contract, constructed directly: detection keys on the
    marker class, not on Plotly's own output."""
    return ok_entry(html=f'<div class="{FIGURE_DIV_CLASS}"></div>')


def unavailable_entry(message: str = "CheckV was not run") -> SectionEntry:
    return SectionEntry(
        kind=EntryKind.RENDERED,
        component_id="example_bio.qc",
        title="Sample quality",
        outcome=RenderedComponent.unavailable(message),
    )


def skipped_entry() -> SectionEntry:
    return SectionEntry(
        kind=EntryKind.RENDERED,
        component_id="example_bio.qc",
        title="Sample quality",
        outcome=RenderedComponent.skipped(),
    )


def failed_entry(error: str = "ValueError: boom") -> SectionEntry:
    return SectionEntry(
        kind=EntryKind.FAILED,
        component_id="broken.quality",
        title="Broken metric",
        error=error,
    )


def asset(role: str) -> EmbeddedAsset:
    """A minimal valid embedded asset: a tiny data URI."""
    return EmbeddedAsset(
        path=f"{role}.png",
        media_type="image/png",
        data_uri="data:image/png;base64,aGVsbG8=",
    )


def bug_diagnostic(message: str = "rendering raised ValueError: boom") -> Diagnostic:
    return Diagnostic(
        kind=DiagnosticKind.PLUGIN_BUG,
        subject="broken.quality",
        message=message,
    )


def note_diagnostic() -> Diagnostic:
    return Diagnostic(
        kind=DiagnosticKind.LOGO_OMITTED,
        subject="logo",
        message="no logo declared in the layout",
    )


def make_document(
    *,
    title: str = "Metagenomic analysis",
    subtitle: str | None = None,
    author: str | None = None,
    version: str | None = None,
    toc: bool = True,
    logo: EmbeddedAsset | None = None,
    favicon: EmbeddedAsset | None = None,
    theme: Theme = DEFAULT_THEME,
    manifest: ReportManifest | None = None,
    sections: tuple[DocumentSection, ...] = (
        DocumentSection(title="Quality control", entries=(ok_entry(),)),
    ),
    diagnostics: tuple[Diagnostic, ...] = (),
) -> ReportDocument:
    """A complete, valid document; every knob overridable."""
    return ReportDocument(
        title=title,
        subtitle=subtitle,
        author=author,
        version=version,
        theme=theme,
        logo=logo,
        favicon=favicon,
        manifest=manifest
        if manifest is not None
        else ReportManifest.model_validate(make_manifest_payload()),
        sections=sections,
        diagnostics=diagnostics,
        toc=toc,
    )


class _UrlCollector(HTMLParser):
    """Collects every ``href``/``src`` attribute value in a page."""

    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name in ("href", "src") and value is not None:
                self.urls.append(value)


# ---------------------------------------------------------------------------
# The page skeleton
# ---------------------------------------------------------------------------


def test_renders_the_page_skeleton() -> None:
    html = render_report(make_document())
    assert html.lstrip().startswith("<!doctype html>")
    assert '<meta charset="utf-8">' in html
    assert "<title>Metagenomic analysis</title>" in html
    assert ":root {" in html
    assert '<header class="coda-headerbar">' in html
    assert "<h1>Metagenomic analysis</h1>" in html
    assert '<section class="coda-section" id="1-quality-control">' in html
    assert "<h2>Quality control</h2>" in html
    assert "This report was generated by workflow-coda" in html


def test_header_bar_carries_version_and_subtitle() -> None:
    html = render_report(make_document(subtitle="Sequencing depth", version="1.2.0"))
    assert '<p class="coda-version">1.2.0</p>' in html
    assert '<p class="coda-subtitle">Sequencing depth</p>' in html
    # Optional identity fields render nothing when unset.  The absence
    # pins are element-shaped: the inlined stylesheet legitimately
    # contains every class name, so bare class-name checks would match
    # CSS selectors.
    absent = render_report(make_document())
    assert '<p class="coda-version">' not in absent
    assert '<p class="coda-subtitle">' not in absent


def test_logo_and_favicon_render_from_data_uris() -> None:
    html = render_report(make_document(logo=asset("logo"), favicon=asset("favicon")))
    # The pin matches the template's img exactly, alt attribute included.
    assert '<img class="coda-logo" src="data:image/png;base64,aGVsbG8=" alt="">' in html
    assert '<link rel="icon" href="data:image/png;base64,aGVsbG8=">' in html


# ---------------------------------------------------------------------------
# Tabs and anchors
# ---------------------------------------------------------------------------


def test_tabs_link_to_section_anchors_and_diagnostics() -> None:
    html = render_report(
        make_document(
            sections=(
                DocumentSection(title="Quality control", entries=(ok_entry(),)),
                DocumentSection(title="Taxonomy", entries=(ok_entry(),)),
            ),
            diagnostics=(bug_diagnostic(),),
        )
    )
    assert '<nav class="coda-tabs"' in html
    assert '<a href="#1-quality-control">Quality control</a>' in html
    assert '<a href="#2-taxonomy">Taxonomy</a>' in html
    assert '<a href="#diagnostics">Diagnostics</a>' in html
    # The tab target exists: same anchor expression, same result.
    assert 'id="1-quality-control"' in html
    assert 'id="2-taxonomy"' in html
    assert 'id="diagnostics"' in html


def test_toc_false_omits_the_tabs_but_keeps_sections() -> None:
    html = render_report(make_document(toc=False))
    assert '<nav class="coda-tabs"' not in html
    assert 'id="1-quality-control"' in html


@pytest.mark.parametrize(
    ("titles", "expected_ids"),
    [
        (("Quality control",), ("1-quality-control",)),
        (("Results", "Results"), ("1-results", "2-results")),
        (("!!! ???",), ("1-section",)),
    ],
)
def test_anchor_ids_are_index_prefixed_and_unique(
    titles: tuple[str, ...], expected_ids: tuple[str, ...]
) -> None:
    # Duplicate titles stay distinct (the index prefixes); a title with
    # no anchor-able characters anchors as "section".
    sections = tuple(
        DocumentSection(title=title, entries=(ok_entry(),)) for title in titles
    )
    html = render_report(make_document(sections=sections))
    for anchor in expected_ids:
        assert f'id="{anchor}"' in html


# ---------------------------------------------------------------------------
# Cards: the honest visual vocabulary
# ---------------------------------------------------------------------------


def test_ok_entry_renders_raw_plugin_html_in_its_card() -> None:
    html = render_report(
        make_document(
            sections=(
                DocumentSection(
                    title="QC",
                    entries=(ok_entry(html="<p>a &lt; b</p>"),),
                ),
            )
        )
    )
    assert '<article class="coda-card" data-component="example_bio.qc">' in html
    assert "<h3>Sample quality</h3>" in html
    # Plugin html is trusted and rendered verbatim — including its own
    # entities, which must not be double-escaped.
    assert '<div class="coda-card-body"><p>a &lt; b</p></div>' in html
    assert "&amp;lt;" not in html


def test_unavailable_entry_renders_the_notice_card() -> None:
    html = render_report(
        make_document(
            sections=(DocumentSection(title="QC", entries=(unavailable_entry(),)),)
        )
    )
    assert 'class="coda-card coda-card--notice"' in html
    assert "<p>CheckV was not run</p>" in html


def test_failed_entry_renders_the_failure_card() -> None:
    html = render_report(
        make_document(
            sections=(DocumentSection(title="QC", entries=(failed_entry(),)),)
        )
    )
    assert 'class="coda-card coda-card--failure"' in html
    assert "<p>ValueError: boom</p>" in html


def test_skipped_entry_renders_nothing() -> None:
    # The section keeps its heading — the reader sees where the
    # component would have been — but the skipped entry renders no
    # card at all.
    html = render_report(
        make_document(
            sections=(DocumentSection(title="QC", entries=(skipped_entry(),)),)
        )
    )
    assert "<h2>QC</h2>" in html
    assert '<article class="coda-card' not in html


# ---------------------------------------------------------------------------
# The trust boundary: framework text escapes, plugin html does not
# ---------------------------------------------------------------------------


def test_framework_text_is_escaped() -> None:
    html = render_report(
        make_document(
            title='QC <script>alert("x")</script>',
            sections=(
                DocumentSection(
                    title="Section <b>title</b>",
                    entries=(
                        SectionEntry(
                            kind=EntryKind.RENDERED,
                            component_id="example_bio.qc",
                            title="Card <i>title</i>",
                            outcome=RenderedComponent.from_html("<p>body</p>"),
                        ),
                    ),
                ),
            ),
            diagnostics=(bug_diagnostic(message="raised <script>boom"),),
        )
    )
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;title&lt;/b&gt;" in html
    assert "&lt;i&gt;title&lt;/i&gt;" in html
    assert "<script>alert" not in html
    assert "<b>title</b>" not in html
    assert "&lt;script&gt;boom" in html


def test_failed_entry_errors_are_escaped() -> None:
    # The failed entry's error string is framework-rendered (in the
    # failure card), so a plugin's exception message cannot inject.
    html = render_report(
        make_document(
            sections=(
                DocumentSection(
                    title="QC",
                    entries=(failed_entry(error="ValueError: <script>"),),
                ),
            )
        )
    )
    assert "ValueError: &lt;script&gt;" in html


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def test_diagnostics_render_problems_then_notes() -> None:
    html = render_report(
        make_document(diagnostics=(bug_diagnostic(), note_diagnostic()))
    )
    assert 'id="diagnostics"' in html
    assert "<h2>Diagnostics</h2>" in html
    assert html.index("Problems") < html.index("Notes")
    assert "coda-badge--plugin_bug" in html
    assert "coda-badge--logo_omitted" in html
    assert "rendering raised ValueError: boom" in html
    assert "no logo declared in the layout" in html


def test_no_diagnostics_renders_no_diagnostics_section() -> None:
    html = render_report(make_document())
    assert 'id="diagnostics"' not in html
    assert "<h2>Diagnostics</h2>" not in html
    assert 'href="#diagnostics"' not in html


# ---------------------------------------------------------------------------
# The theme, as generated CSS
# ---------------------------------------------------------------------------


def test_default_theme_becomes_custom_properties() -> None:
    html = render_report(make_document())
    for token, color in DEFAULT_THEME.colors.items():
        assert f"--coda-{token}: {color};" in html
    assert "--coda-series-1: #0d6efd;" in html
    assert "--coda-series-5: #6610f2;" in html
    assert "--coda-series-6" not in html
    assert "system-ui" in html


def test_custom_theme_tokens_and_series_length() -> None:
    # Theme tokens are lowercase letters, digits and hyphens by
    # contract (^[a-z][a-z0-9-]*$) — exactly the characters valid in a
    # CSS identifier, which is what makes the generated :root block
    # sound by construction.  The additional token uses the
    # contract's own spelling.
    payload = DEFAULT_THEME.model_dump()
    payload["colors"]["chart-grid"] = "#112233"
    payload["series"] = ["#111111", "#222222"]
    payload["font_body"] = "Georgia, serif"
    theme = Theme.model_validate(payload)
    html = render_report(make_document(theme=theme))
    assert "--coda-chart-grid: #112233;" in html
    assert "--coda-series-1: #111111;" in html
    assert "--coda-series-2: #222222;" in html
    assert "--coda-series-3" not in html
    assert "--coda-font-body: Georgia, serif;" in html


# ---------------------------------------------------------------------------
# Plotly.js: inlined exactly when a figure exists
# ---------------------------------------------------------------------------


def test_figures_inline_the_plotly_bundle_once() -> None:
    # The same source the renderer reads — the installed package's
    # bundled plotly.min.js — must appear in the page, whole.
    plotly_js = (
        importlib.resources.files("plotly") / "package_data" / "plotly.min.js"
    ).read_text(encoding="utf-8")
    html = render_report(
        make_document(
            sections=(DocumentSection(title="Figures", entries=(figure_entry(),)),)
        )
    )
    assert plotly_js in html
    assert html.count("<script>") == 1
    assert 'class="coda-figure"' in html


def test_no_figures_means_no_scripts() -> None:
    html = render_report(make_document())
    assert "<script" not in html


def test_missing_plotly_raises_the_render_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A None entry in sys.modules halts re-import, so the renderer's
    # bundle read fails exactly as it would without plotly installed.
    monkeypatch.setitem(sys.modules, "plotly", None)
    with pytest.raises(RenderError, match="Install plotly"):
        render_report(
            make_document(
                sections=(DocumentSection(title="Figures", entries=(figure_entry(),)),)
            )
        )


# ---------------------------------------------------------------------------
# Provenance and attribution
# ---------------------------------------------------------------------------


def test_provenance_lines_come_from_the_manifest() -> None:
    manifest = ReportManifest.model_validate(make_manifest_payload())
    html = render_report(make_document(manifest=manifest))
    assert f"Produced by {manifest.producer.name} {manifest.producer.version}" in html
    assert f"Manifest schema version {manifest.schema_version}" in html
    complete = sum(
        1
        for artifact in manifest.artifacts
        if artifact.status is ArtifactStatus.COMPLETE
    )
    assert f"{complete} of {len(manifest.artifacts)} artifacts completed" in html


def test_provenance_module_and_run_lines_when_declared() -> None:
    # Built through full validation: pydantic's model_copy(update=)
    # bypasses validation, and updating with a raw dict would poison
    # the document.  The producer payload is narrowed to a dict before
    # the merge — make_manifest_payload is typed dict[str, object], so
    # payload["producer"] is object until the assert narrows it (and
    # doubles as a fixture sanity pin).
    payload = make_manifest_payload()
    producer = payload["producer"]
    assert isinstance(producer, dict)
    producer["module_id"] = "qc-module"
    producer["run_id"] = "run-42"
    declared = ReportManifest.model_validate(payload)
    html = render_report(make_document(manifest=declared))
    assert "<li>Workflow module: qc-module</li>" in html
    assert "<li>Run: run-42</li>" in html
    # Without the optional fields, their lines are absent.
    plain_manifest = ReportManifest.model_validate(make_manifest_payload())
    if (
        plain_manifest.producer.module_id is None
        and plain_manifest.producer.run_id is None
    ):
        plain = render_report(make_document(manifest=plain_manifest))
        assert "Workflow module:" not in plain
        assert "Run:" not in plain


def test_footer_carries_the_author_and_attribution() -> None:
    html = render_report(make_document(author="The Genomics Group"))
    assert '<p class="coda-author">The Genomics Group</p>' in html
    assert "This report was generated by workflow-coda" in html


# ---------------------------------------------------------------------------
# The self-containment invariant
# ---------------------------------------------------------------------------


def test_the_report_is_self_contained() -> None:
    """The promise, enforced: a worst-case document — logo, favicon,
    a figure (Plotly inlined), tabs, diagnostics, provenance — and
    every link or resource the page references is either embedded
    data or an in-page fragment.  The check is attribute-scoped
    parsing, not substring scanning, because the inlined Plotly.js
    legitimately contains URL-shaped strings inside its code.

    Plugin-supplied html is trusted by design; these fixtures contain
    no URLs, so the pin is exactly: the framework contributes none.
    """
    document = make_document(
        logo=asset("logo"),
        favicon=asset("favicon"),
        sections=(
            DocumentSection(title="Figures", entries=(figure_entry(),)),
            DocumentSection(title="Quality control", entries=(ok_entry(),)),
        ),
        diagnostics=(bug_diagnostic(), note_diagnostic()),
    )
    html = render_report(document)
    collector = _UrlCollector()
    collector.feed(html)
    assert len(collector.urls) >= 5, "the worst case must exercise links"
    for url in collector.urls:
        assert url.startswith(("data:", "#")), f"external reference: {url}"
