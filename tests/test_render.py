"""Tests for the report renderer: the document in, the
self-contained page out — tabs, composition, the placed
diagnostics panel, and the component page chrome."""

import importlib.resources
import sys
from html.parser import HTMLParser

import pytest
from factories import make_manifest_payload, stub_figure

from workflow_coda.components import ComponentChrome, RenderedComponent
from workflow_coda.errors import RenderError
from workflow_coda.manifest import ArtifactStatus, ReportManifest
from workflow_coda.render import render_report
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
from workflow_coda.theme import DEFAULT_THEME, Theme, ThemeToken


def figure_entry() -> ComponentEntry:
    """A rendered entry carrying the framework figure marker — built
    through the real constructor, so detection is pinned against the
    actual construction path."""
    outcome = RenderedComponent.from_figure(
        stub_figure(), description="Depth per sample"
    )
    assert outcome.html is not None  # OK outcomes always carry html
    return ok_entry(html=outcome.html)


# ---------------------------------------------------------------------------
# Fixtures: entries, tabs, documents
# ---------------------------------------------------------------------------


def ok_entry(
    html: str = "<p>Rendered.</p>",
    component_id: str = "example_bio.qc",
    title: str = "Sample quality",
) -> ComponentEntry:
    """A rendered entry: the shape a successful render produces."""
    return ComponentEntry(
        kind=EntryKind.RENDERED,
        component_id=component_id,
        title=title,
        outcome=RenderedComponent.from_html(html),
    )


def unavailable_entry(message: str = "CheckV was not run") -> ComponentEntry:
    return ComponentEntry(
        kind=EntryKind.RENDERED,
        component_id="example_bio.qc",
        title="Sample quality",
        outcome=RenderedComponent.unavailable(message),
    )


def skipped_entry() -> ComponentEntry:
    return ComponentEntry(
        kind=EntryKind.RENDERED,
        component_id="example_bio.qc",
        title="Sample quality",
        outcome=RenderedComponent.skipped(),
    )


def failed_entry(error: str = "ValueError: boom") -> ComponentEntry:
    return ComponentEntry(
        kind=EntryKind.FAILED,
        component_id="broken.quality",
        title="Broken metric",
        error=error,
    )


def tab(title: str, nodes: tuple[object, ...]) -> DocumentTab:
    """A document tab over the given node tuple."""
    return DocumentTab(title=title, nodes=nodes)  # type: ignore[arg-type]


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
    logo: EmbeddedAsset | InlineLogo | None = None,
    favicon: EmbeddedAsset | None = None,
    theme: Theme = DEFAULT_THEME,
    header_color: ThemeToken | None = None,
    manifest: ReportManifest | None = None,
    tabs: tuple[DocumentTab, ...] = (
        DocumentTab(title="Quality control", nodes=(ok_entry(),)),
    ),
    diagnostics: tuple[Diagnostic, ...] = (),
    chrome: tuple[ChromeContribution, ...] = (),
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
        tabs=tabs,
        diagnostics=diagnostics,
        chrome=chrome,
        header_color=header_color,
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
    assert '<section class="coda-tabpanel" id="1-quality-control">' in html
    assert "<h2>Quality control</h2>" in html
    assert "This report was generated by workflow-coda" in html


def test_header_bar_carries_version_and_subtitle() -> None:
    html = render_report(make_document(subtitle="Sequencing depth", version="1.2.0"))
    assert '<p class="coda-version">1.2.0</p>' in html
    assert '<p class="coda-subtitle">Sequencing depth</p>' in html
    # Absence pins stay element-shaped: the inlined stylesheet
    # legitimately contains every class name.
    absent = render_report(make_document())
    assert '<p class="coda-version">' not in absent
    assert '<p class="coda-subtitle">' not in absent


def test_logo_and_favicon_render_from_data_uris() -> None:
    html = render_report(make_document(logo=asset("logo"), favicon=asset("favicon")))
    assert '<img class="coda-logo" src="data:image/png;base64,aGVsbG8=" alt="">' in html
    assert '<link rel="icon" href="data:image/png;base64,aGVsbG8=">' in html


def test_an_inline_logo_renders_as_svg_in_the_brand() -> None:
    # The logo's second shape: inlined svg markup, not a data-URI
    # <img> — an image is an isolated document whose currentColor
    # can never reach the page, and real markup inherits the
    # header's contrast-picked ink.  The markup rides raw
    # (sanitized at build, upstream of the document), first in the
    # brand block; the scoped sizing rule is the framework
    # stylesheet's own.
    markup = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'class="coda-icon" aria-hidden="true" focusable="false" '
        'width="1em" height="1em">'
        '<path fill="currentColor" d="M12 3l7 18-7-4-7 4z"/></svg>'
    )
    logo = InlineLogo(source="core-arrow-up", markup=markup)
    html = render_report(make_document(logo=logo))
    assert markup in html
    assert '<img class="coda-logo"' not in html
    assert (
        html.index('class="coda-brand"')
        < html.index(markup)
        < html.index('class="coda-brand-text"')
    )
    assert ".coda-brand > svg.coda-icon {" in html  # the scoped sizing rule


# ---------------------------------------------------------------------------
# Tab navigation
# ---------------------------------------------------------------------------


def test_tab_bar_buttons_and_panels_pair_by_anchor() -> None:
    html = render_report(
        make_document(
            tabs=(tab("Quality control", (ok_entry(),)), tab("Taxonomy", (ok_entry(),)))
        )
    )
    assert '<nav class="coda-tabs" role="tablist" aria-label="Report sections">' in html
    assert (
        '<button type="button" class="coda-tab" role="tab" '
        'id="tabbtn-1-quality-control" aria-controls="1-quality-control" '
        'aria-selected="true" tabindex="0" data-target="1-quality-control">'
        "Quality control</button>"
    ) in html
    assert (
        '<button type="button" class="coda-tab" role="tab" '
        'id="tabbtn-2-taxonomy" aria-controls="2-taxonomy" '
        'aria-selected="false" tabindex="-1" data-target="2-taxonomy">'
        "Taxonomy</button>"
    ) in html
    assert (
        '<section class="coda-tabpanel" id="1-quality-control" '
        'role="tabpanel" aria-labelledby="tabbtn-1-quality-control">'
    ) in html


def test_single_tab_renders_no_bar_and_no_script() -> None:
    html = render_report(make_document())
    assert '<nav class="coda-tabs"' not in html
    assert "<script" not in html
    assert '<section class="coda-tabpanel" id="1-quality-control">' in html
    assert "<h2>Quality control</h2>" in html


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
    html = render_report(
        make_document(tabs=tuple(tab(title, (ok_entry(),)) for title in titles))
    )
    for anchor in expected_ids:
        assert f'id="{anchor}"' in html


# ---------------------------------------------------------------------------
# Cards: the honest visual vocabulary
# ---------------------------------------------------------------------------


def test_ok_entry_renders_raw_plugin_html_in_its_card() -> None:
    html = render_report(
        make_document(tabs=(tab("QC", (ok_entry(html="<p>a &lt; b</p>"),)),))
    )
    assert '<article class="coda-card" data-component="example_bio.qc">' in html
    assert "<h3>Sample quality</h3>" in html
    # Plugin html is trusted and rendered verbatim — its own entities
    # must not be double-escaped.
    assert '<div class="coda-card-body"><p>a &lt; b</p></div>' in html
    assert "&amp;lt;" not in html


def test_unavailable_entry_renders_the_notice_card() -> None:
    html = render_report(make_document(tabs=(tab("QC", (unavailable_entry(),)),)))
    assert 'class="coda-card coda-card--notice"' in html
    assert "<p>CheckV was not run</p>" in html


def test_failed_entry_renders_the_failure_card() -> None:
    html = render_report(make_document(tabs=(tab("QC", (failed_entry(),)),)))
    assert 'class="coda-card coda-card--failure"' in html
    assert "<p>ValueError: boom</p>" in html


def test_skipped_entry_renders_nothing() -> None:
    # The tab keeps its heading; the skipped entry renders no card.
    html = render_report(make_document(tabs=(tab("QC", (skipped_entry(),)),)))
    assert "<h2>QC</h2>" in html
    assert '<article class="coda-card' not in html


# ---------------------------------------------------------------------------
# Tiles: the self-chrome contract
# ---------------------------------------------------------------------------


def test_tile_component_renders_in_a_bare_wrapper() -> None:
    # A TILE component painted its whole card: the framework
    # contributes only the data-component wrapper — no framework
    # title, no card chrome.
    html = render_report(
        make_document(
            tabs=(
                tab(
                    "QC",
                    (
                        ComponentEntry(
                            kind=EntryKind.RENDERED,
                            component_id="example_bio.qc",
                            title="Sample quality",
                            chrome=ComponentChrome.TILE,
                            outcome=RenderedComponent.from_html(
                                '<div class="coda-kpi">painted</div>'
                            ),
                        ),
                    ),
                ),
            )
        )
    )
    assert '<article class="coda-tile" data-component="example_bio.qc">' in html
    assert '<div class="coda-kpi">painted</div></article>' in html
    assert "<h3" not in html  # the plugin owns the title now


def test_tile_degradation_uses_the_framework_notice_card() -> None:
    # Degradation is mode-independent: an unavailable TILE still
    # teaches in place, with the framework rendering the title the
    # plugin never got to paint.
    html = render_report(
        make_document(
            tabs=(
                tab(
                    "QC",
                    (
                        ComponentEntry(
                            kind=EntryKind.RENDERED,
                            component_id="core.kpi",
                            title="Mean depth",
                            chrome=ComponentChrome.TILE,
                            outcome=RenderedComponent.unavailable("no artifact"),
                        ),
                    ),
                ),
            )
        )
    )
    assert 'class="coda-card coda-card--notice"' in html
    assert "<h3>Mean depth</h3>" in html
    assert "<p>no artifact</p>" in html


# ---------------------------------------------------------------------------
# Composition: rows, grids, groups, and the generated split CSS
# ---------------------------------------------------------------------------


def test_rows_render_children_in_ratio_columns() -> None:
    row = RowEntry(
        split=(2.0, 1.0),
        children=(ok_entry(html="<p>A</p>"), ok_entry(html="<p>B</p>")),
    )
    html = render_report(make_document(tabs=(tab("QC", (row,)),)))
    assert '<div class="coda-row coda-split-2-1">' in html
    assert html.index("<p>A</p>") < html.index("<p>B</p>")
    # The generated rules: the ratio under the min-width, the mobile
    # default, and the media block that gates them.
    assert ".coda-split-2-1 { grid-template-columns: 2fr 1fr; }" in html
    assert "grid-template-columns: 1fr;" in html
    assert "@media (min-width: 48rem)" in html


def test_unsplit_rows_declare_equal_widths() -> None:
    row = RowEntry(split=None, children=(ok_entry(), ok_entry()))
    html = render_report(make_document(tabs=(tab("QC", (row,)),)))
    assert '<div class="coda-row coda-split-1-1">' in html
    assert ".coda-split-1-1 { grid-template-columns: 1fr 1fr; }" in html


def test_grids_flow_children_into_ratio_columns() -> None:
    grid = GridEntry(
        split=(1.0, 1.0),
        children=tuple(ok_entry(html=f"<p>{n}</p>") for n in ("A", "B", "C")),
    )
    html = render_report(make_document(tabs=(tab("QC", (grid,)),)))
    assert '<div class="coda-grid coda-split-1-1">' in html
    assert html.index("<p>A</p>") < html.index("<p>C</p>")  # row-major order


def test_groups_render_titled_and_untitled_boxes() -> None:
    titled = CardEntry(
        title="Group", layout="stack", split=None, children=(ok_entry(),)
    )
    untitled = CardEntry(title=None, layout="stack", split=None, children=(ok_entry(),))
    side_by_side = CardEntry(
        title=None, layout="row", split=(2.0, 1.0), children=(ok_entry(), ok_entry())
    )
    html = render_report(
        make_document(tabs=(tab("QC", (titled, untitled, side_by_side)),))
    )
    assert '<div class="coda-group"><h3>Group</h3>' in html
    assert html.count('class="coda-group"') == 3
    assert '<div class="coda-group"><article' in html  # untitled: no heading
    assert '<div class="coda-group"><div class="coda-row coda-split-2-1">' in html


def test_split_rules_are_deduplicated() -> None:
    # Two rows, one ratio: one generated rule, two carrying elements.
    rows = (
        RowEntry(split=(2.0, 1.0), children=(ok_entry(), ok_entry())),
        RowEntry(split=(2.0, 1.0), children=(ok_entry(), ok_entry())),
    )
    html = render_report(make_document(tabs=(tab("QC", rows),)))
    assert html.count(".coda-split-2-1 { grid-template-columns: 2fr 1fr; }") == 1
    assert html.count('class="coda-row coda-split-2-1"') == 2


def test_fractional_ratios_name_valid_classes() -> None:
    row = RowEntry(split=(1.5, 1.0), children=(ok_entry(), ok_entry()))
    html = render_report(make_document(tabs=(tab("QC", (row,)),)))
    assert '<div class="coda-row coda-split-1p5-1">' in html
    assert ".coda-split-1p5-1 { grid-template-columns: 1.5fr 1fr; }" in html


def test_documents_without_splits_emit_no_layout_css() -> None:
    html = render_report(make_document())
    assert "coda-split-" not in html


# ---------------------------------------------------------------------------
# The trust boundary: framework text escapes, plugin html does not
# ---------------------------------------------------------------------------


def test_framework_text_is_escaped() -> None:
    html = render_report(
        make_document(
            title='QC <script>alert("x")</script>',
            tabs=(
                tab(
                    "Section <b>title</b>",
                    (DiagnosticsEntry(), ok_entry(title="Card <i>title</i>")),
                ),
                tab("Other", (ok_entry(),)),
            ),
            diagnostics=(bug_diagnostic(message="raised <script>boom"),),
        )
    )
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;title&lt;/b&gt;</button>" in html  # the tab button
    assert "<h2>Section &lt;b&gt;title&lt;/b&gt;</h2>" in html  # the panel heading
    assert "&lt;i&gt;title&lt;/i&gt;" in html
    assert "<script>alert" not in html
    assert "<b>title</b>" not in html
    assert "&lt;script&gt;boom" in html  # the placed panel's message


def test_failed_entry_errors_are_escaped() -> None:
    html = render_report(
        make_document(tabs=(tab("QC", (failed_entry(error="ValueError: <script>"),)),))
    )
    assert "ValueError: &lt;script&gt;" in html


# ---------------------------------------------------------------------------
# Component page chrome: the second raw family
# ---------------------------------------------------------------------------


def contribution(
    component_id: str = "example_bio.qc",
    css: str | None = ".coda-example_bio-qc { color: inherit; }",
    js: str | None = None,
) -> ChromeContribution:
    """One resolved page-chrome contribution; every field overridable,
    css-only by default."""
    return ChromeContribution(component_id=component_id, css=css, js=js)


def test_component_css_inlines_after_the_framework_stylesheet() -> None:
    # One <style> element of its own, banner-commented per
    # contribution, immediately after the framework's block — plugin
    # strings raw like plugin html: the child combinator survives
    # unescaped.
    css = ".coda-example_bio-qc > p { color: inherit; }"
    html = render_report(make_document(chrome=(contribution(css=css),)))
    assert "</style>\n<style>\n/* example_bio.qc */" in html
    assert f"\n{css}\n</style>" in html


def test_chrome_banners_follow_first_use_order() -> None:
    # The document's chrome order is the page's block order — the
    # builder's collection guarantee, held through rendering.
    html = render_report(
        make_document(
            chrome=(
                contribution(component_id="styled.first", css=".coda-styled-f { }"),
                contribution(component_id="styled.second", css=".coda-styled-s { }"),
            )
        )
    )
    assert html.index("/* styled.first */") < html.index("/* styled.second */")


def test_component_js_inlines_after_the_framework_scripts() -> None:
    # One <script> element of its own, after report.js — the DOM is
    # established when plugin code runs — each contribution under its
    # // banner.  The single quotes would become &#39; under
    # autoescape; surviving verbatim is the rawness pin.
    html = render_report(
        make_document(
            tabs=(tab("QC", (ok_entry(),)), tab("Taxonomy", (ok_entry(),))),
            chrome=(contribution(css=None, js="console.log('enhanced');"),),
        )
    )
    assert "</script>\n<script>\n// example_bio.qc" in html
    assert "console.log('enhanced');\n</script>" in html
    # After the framework's own script: the tab IIFE closes first.
    assert html.index("})();") < html.index("// example_bio.qc")
    # The census shifts knowingly: tab script plus component block.
    assert html.count("<script>") == 2


def test_css_only_and_js_only_contributions_emit_one_block_each() -> None:
    # The renderer splits by kind.  The js-only case also pins
    # independence from the tab bar: a single-tab, script-free
    # report still carries the component's script block.
    css_only = render_report(make_document(chrome=(contribution(js=None),)))
    assert css_only.count("<style>") == 2
    assert "<script" not in css_only
    js_only = render_report(
        make_document(chrome=(contribution(css=None, js="console.log('hi');"),))
    )
    assert js_only.count("<style>") == 1
    assert js_only.count("<script>") == 1


def test_chromeless_documents_inline_no_component_blocks() -> None:
    # The channel is opt-in end to end: without contributions the
    # page is shaped as before — one framework style block, and the
    # boundary shape never appears.
    html = render_report(make_document())
    assert html.count("<style>") == 1
    assert "</style>\n<style>" not in html


# ---------------------------------------------------------------------------
# Diagnostics: placed, or absent by choice
# ---------------------------------------------------------------------------


def test_diagnostics_marker_renders_the_panel_in_place() -> None:
    html = render_report(
        make_document(
            tabs=(tab("QC", (DiagnosticsEntry(), ok_entry())),),
            diagnostics=(bug_diagnostic(), note_diagnostic()),
        )
    )
    assert '<section class="coda-diagnostics" aria-label="Diagnostics">' in html
    assert "<h2>Diagnostics</h2>" in html
    assert html.index("Problems") < html.index("Notes")
    # The exact badge element — the stylesheet also contains the class
    # names, so a bare class pin would match CSS, not content.
    assert '<span class="coda-badge coda-badge--plugin_bug">plugin_bug</span>' in html
    assert (
        '<span class="coda-badge coda-badge--logo_omitted">logo_omitted</span>' in html
    )
    assert "rendering raised ValueError: boom" in html
    assert "no logo declared in the layout" in html


def test_no_marker_renders_no_panel() -> None:
    # Omission is the feature: diagnostics recorded but placed nowhere
    # appear nowhere — the element-shaped pin stays CSS-safe.
    html = render_report(
        make_document(diagnostics=(bug_diagnostic(), note_diagnostic()))
    )
    assert '<section class="coda-diagnostics"' not in html


def test_empty_ledger_shows_no_issues() -> None:
    # A placed panel is always predictable: an empty ledger shows the
    # muted state, not a blank.
    html = render_report(make_document(tabs=(tab("QC", (DiagnosticsEntry(),)),)))
    assert '<p class="coda-diagnostics__empty">No issues.</p>' in html


def test_repeated_markers_repeat_the_panel() -> None:
    html = render_report(
        make_document(
            tabs=(tab("QC", (DiagnosticsEntry(), DiagnosticsEntry())),),
            diagnostics=(bug_diagnostic(),),
        )
    )
    assert html.count('<section class="coda-diagnostics"') == 2


# ---------------------------------------------------------------------------
# The theme, as generated CSS
# ---------------------------------------------------------------------------


def test_default_theme_becomes_custom_properties() -> None:
    # Palette pins derive from the theme: a theme edit is never a
    # test sweep.  The boundary pins derive too — the first and
    # last series entries emit, the index one past the end does
    # not — so the palette's length is free to change.  And
    # --coda-text is derived, not declared (the retired token): the
    # loop over the theme's colors can no longer cover it, so the
    # derivation is pinned directly — the theme's light-or-dark
    # pair, contrast-picked against the page background.
    html = render_report(make_document())
    for token, color in DEFAULT_THEME.colors.items():
        assert f"--coda-{token}: {color};" in html
    body_ink = DEFAULT_THEME.text_on(DEFAULT_THEME.colors["background"])
    assert f"--coda-text: {body_ink};" in html
    assert f"--coda-series-1: {DEFAULT_THEME.series[0]};" in html
    assert (
        f"--coda-series-{len(DEFAULT_THEME.series)}: {DEFAULT_THEME.series[-1]};"
        in html
    )
    assert f"--coda-series-{len(DEFAULT_THEME.series) + 1}:" not in html
    assert "system-ui" in html


def test_custom_theme_tokens_and_series_length() -> None:
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


def test_the_header_pair_derives_from_the_layouts_token() -> None:
    # The header derives like --coda-text: the background from the
    # layout's token — primary when the layout is silent, a core
    # token every theme carries — and the ink contrast-picked
    # against it, so the bar reads on any theme without the author
    # choosing.  The stylesheet wires the bar to the pair.
    html = render_report(make_document())
    primary = DEFAULT_THEME.colors["primary"]
    assert f"--coda-header-background: {primary};" in html
    assert f"--coda-header-text: {DEFAULT_THEME.text_on(primary)};" in html
    assert "background: var(--coda-header-background);" in html
    assert "color: var(--coda-header-text);" in html
    accent = DEFAULT_THEME.colors["accent"]
    declared = render_report(make_document(header_color="accent"))
    assert f"--coda-header-background: {accent};" in declared
    assert f"--coda-header-text: {DEFAULT_THEME.text_on(accent)};" in declared


def test_declared_header_tokens_win_over_the_derivation() -> None:
    # The declared-token-wins law, --coda-text's precedent: a theme
    # that declares its own header-background / header-text tokens
    # outranks the derivation — and the layout's token with it; the
    # theme is the design authority, the layout borrows its
    # vocabulary.  The pair appears exactly once.  The ink still
    # derives when the theme declares the background alone,
    # contrast-picked against the declared color.
    payload = DEFAULT_THEME.model_dump()
    payload["colors"]["header-background"] = "#123456"
    payload["colors"]["header-text"] = "#654321"
    both = Theme.model_validate(payload)
    html = render_report(make_document(theme=both, header_color="accent"))
    assert "--coda-header-background: #123456;" in html
    assert "--coda-header-text: #654321;" in html
    assert html.count("--coda-header-background:") == 1
    assert html.count("--coda-header-text:") == 1
    payload = DEFAULT_THEME.model_dump()
    payload["colors"]["header-background"] = "#123456"
    background_only = Theme.model_validate(payload)
    page = render_report(make_document(theme=background_only))
    assert "--coda-header-background: #123456;" in page
    assert f"--coda-header-text: {background_only.text_on('#123456')};" in page
    assert page.count("--coda-header-background:") == 1


# ---------------------------------------------------------------------------
# Inlined scripts: each exactly when it is needed
# ---------------------------------------------------------------------------


def test_figures_inline_the_plotly_bundle_once() -> None:
    plotly_js = (
        importlib.resources.files("plotly") / "package_data" / "plotly.min.js"
    ).read_text(encoding="utf-8")
    html = render_report(make_document(tabs=(tab("Figures", (figure_entry(),)),)))
    assert plotly_js in html
    assert html.count("<script>") == 1
    assert 'class="coda-figure"' in html


def test_tab_bar_inlines_the_navigation_script() -> None:
    html = render_report(
        make_document(tabs=(tab("QC", (ok_entry(),)), tab("Taxonomy", (ok_entry(),))))
    )
    assert html.count("<script>") == 1
    assert 'document.documentElement.classList.add("coda-js")' in html


def test_tab_activation_dispatches_the_shown_event() -> None:
    # The plugin-script event contract: activation dispatches
    # "coda:tab-shown" on the panel, bubbling to document — content
    # reveals enhance themselves (a hidden figure resizing, a table
    # reflowing) without reaching into the panels.  Content pin, the
    # house class: the contract ships inside the inlined script.
    html = render_report(
        make_document(tabs=(tab("QC", (ok_entry(),)), tab("Taxonomy", (ok_entry(),))))
    )
    assert '"coda:tab-shown"' in html
    assert "bubbles: true" in html
    # The event exists only with a tab bar: a single-tab report
    # inlines no script and dispatches nothing.
    single = render_report(make_document())
    assert '"coda:tab-shown"' not in single


def test_tab_shown_event_resizes_plotly_figures() -> None:
    # Verify that the framework’s own listener (report.js) resizes any
    # Plotly figure inside the newly shown panel.  The test checks the
    # exact strings that are inlined from the shipped script – a source
    # pin that will break if the selector or resize call changes.
    html = render_report(
        make_document(
            tabs=(
                tab("QC", (ok_entry(),)),
                tab("Figures", (figure_entry(),)),
            )
        )
    )
    # The listener is registered exactly once.
    assert html.count("document.addEventListener('coda:tab-shown'") == 1
    # The selector targets the Plotly graph container inside the figure.
    assert (
        "var figures = panel.querySelectorAll('.coda-figure .plotly-graph-div');"
        in html
    )
    # Resize is deferred to the next animation frame.
    assert "requestAnimationFrame(function () {" in html
    # And the Plotly resize API is invoked.
    assert "Plotly.Plots.resize(f);" in html


def test_no_figures_and_one_tab_mean_no_scripts() -> None:
    html = render_report(make_document())
    assert "<script" not in html


def test_missing_plotly_raises_the_render_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A None entry in sys.modules halts re-import, so the renderer's
    # bundle read fails exactly as it would without plotly installed.
    monkeypatch.setitem(sys.modules, "plotly", None)
    with pytest.raises(RenderError, match="Install plotly"):
        render_report(make_document(tabs=(tab("Figures", (figure_entry(),)),)))


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
    payload = make_manifest_payload()
    producer = payload["producer"]
    assert isinstance(producer, dict)
    producer["module_id"] = "qc-module"
    producer["run_id"] = "run-42"
    declared = ReportManifest.model_validate(payload)
    html = render_report(make_document(manifest=declared))
    assert "<li>Workflow module: qc-module</li>" in html
    assert "<li>Run: run-42</li>" in html
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
    """The promise, enforced on a worst-case document: logo, favicon,
    a figure (Plotly inlined), a tab bar (report.js inlined), a placed
    diagnostics panel, provenance — and attribute-scoped parsing finds
    every referenced resource is embedded data.  The pin is exact now:
    the tab bar's buttons carry no hrefs, so the two data URIs are the
    complete set."""
    logo = asset("logo")
    favicon = asset("favicon")
    document = make_document(
        logo=logo,
        favicon=favicon,
        tabs=(
            tab("Figures", (figure_entry(),)),
            tab("Quality control", (DiagnosticsEntry(), ok_entry())),
        ),
        diagnostics=(bug_diagnostic(), note_diagnostic()),
    )
    html = render_report(document)
    assert html.count("<script>") == 2  # Plotly.js and the tab script
    collector = _UrlCollector()
    collector.feed(html)
    assert collector.urls == [favicon.data_uri, logo.data_uri]


def test_the_page_declares_its_content_security_policy() -> None:
    # Self-containment enforced at read time: the reader's browser
    # blocks every network request the page — or a plugin's style or
    # script — could attempt.  Inline style and script are inherent
    # to the single-file architecture; the CSP's target is the
    # network, closed by default-src 'none'.  First head child: the
    # posture is declared before anything else in the page loads.
    html = render_report(make_document())
    expected = (
        '<meta http-equiv="Content-Security-Policy" '
        "content=\"default-src 'none'; img-src data:; "
        "style-src 'unsafe-inline'; script-src 'unsafe-inline'\">"
    )
    assert expected in html
    assert html.index("Content-Security-Policy") < html.index("<meta charset")


def test_plugin_chrome_stays_within_the_containment_envelope() -> None:
    """The worst case plus the second raw family: a component's css
    and js inlined alongside Plotly.js, the tab script, and both
    data URIs — attribute-scoped parsing still finds every referenced
    resource embedded, and the block census is accounted: two style
    blocks (framework, component) and three scripts (Plotly.js, the
    tab script, the component block)."""
    logo = asset("logo")
    favicon = asset("favicon")
    document = make_document(
        logo=logo,
        favicon=favicon,
        tabs=(
            tab("Figures", (figure_entry(),)),
            tab("Quality control", (DiagnosticsEntry(), ok_entry())),
        ),
        diagnostics=(bug_diagnostic(), note_diagnostic()),
        chrome=(
            contribution(
                component_id="core.table",
                css=".coda-core-table { width: 100%; }",
                js="console.log('core.table enhanced');",
            ),
        ),
    )
    html = render_report(document)
    assert html.count("<style>") == 2
    assert html.count("<script>") == 3
    collector = _UrlCollector()
    collector.feed(html)
    assert collector.urls == [favicon.data_uri, logo.data_uri]
