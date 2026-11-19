"""States rendering: complete panels, stable identities, and tree scans.

URL selection enhances complete content. Widgets remain deferred.
"""

import importlib.resources
import re
import sys
from html.parser import HTMLParser

import pytest
from factories import make_manifest_payload, stub_figure
from markupsafe import escape

from workflow_coda.components import RenderedComponent
from workflow_coda.errors import RenderError
from workflow_coda.manifest import ReportManifest
from workflow_coda.render import render_report
from workflow_coda.report import (
    CardEntry,
    ComponentEntry,
    Diagnostic,
    DiagnosticKind,
    DiagnosticsEntry,
    DocumentNode,
    DocumentTab,
    EntryKind,
    GridEntry,
    ReportDocument,
    RowEntry,
    StatePanel,
    StatesEntry,
)
from workflow_coda.theme import DEFAULT_THEME


def _entry(html: str = "<p>Content.</p>") -> ComponentEntry:
    return ComponentEntry(
        kind=EntryKind.RENDERED,
        component_id="example.quality",
        title="Quality",
        outcome=RenderedComponent.from_html(html),
    )


def _states(
    *panels: StatePanel,
    dimension: str = "batch",
    kind: str = "categorical",
) -> StatesEntry:
    assert kind in ("categorical", "ordered")
    return StatesEntry(
        dimension=dimension,
        kind="ordered" if kind == "ordered" else "categorical",
        panels=panels,
    )


def _panel(value: str, *children: DocumentNode) -> StatePanel:
    return StatePanel(value=value, children=children or (_entry(),))


def _document(
    *nodes: DocumentNode,
    diagnostics: tuple[Diagnostic, ...] = (),
    extra_tabs: tuple[DocumentTab, ...] = (),
) -> ReportDocument:
    return ReportDocument(
        title="States report",
        subtitle=None,
        author=None,
        version=None,
        theme=DEFAULT_THEME,
        logo=None,
        favicon=None,
        manifest=ReportManifest.model_validate(make_manifest_payload()),
        tabs=(DocumentTab(title="States", nodes=nodes),) + extra_tabs,
        diagnostics=diagnostics,
    )


class _Elements(HTMLParser):
    """Collect actual markup attributes, not strings in CSS or scripts."""

    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, dict(attrs)))

    def with_class(self, name: str) -> list[dict[str, str | None]]:
        return [
            attrs
            for _, attrs in self.elements
            if name in (attrs.get("class") or "").split()
        ]


def _elements(page: str) -> _Elements:
    parser = _Elements()
    parser.feed(page)
    parser.close()
    return parser


def test_panels_render_in_axis_order_with_all_children_present() -> None:
    page = render_report(
        _document(
            _states(
                _panel("B", _entry("<p>B first</p>"), _entry("<p>B second</p>")),
                _panel("A", _entry("<p>A content</p>")),
                kind="ordered",
            )
        )
    )
    parser = _elements(page)
    assert parser.with_class("coda-states") == [
        {
            "class": "coda-states",
            "data-states-dimension": "batch",
            "data-kind": "ordered",
        }
    ]
    panels = parser.with_class("coda-state")
    assert [panel["data-state-value"] for panel in panels] == ["B", "A"]
    assert [panel["data-state-dimension"] for panel in panels] == ["batch", "batch"]
    assert [panel["id"] for panel in panels] == ["coda-state-1", "coda-state-2"]
    assert page.index("<h3>B</h3>") < page.index("<p>B first</p>")
    assert page.index("<p>B first</p>") < page.index("<p>B second</p>")
    assert page.index("<p>B second</p>") < page.index("<h3>A</h3>")
    assert page.index("<h3>A</h3>") < page.index("<p>A content</p>")
    assert all("hidden" not in panel and "aria-hidden" not in panel for panel in panels)
    # Was zero scripts; now one merged codec/policy/controller block.
    assert page.count("<script>") == 1
    assert "<select" not in page
    assert "<input" not in page
    assert "<button" not in page


def test_state_labels_escape_in_headings_and_attributes_without_normalization() -> None:
    raw = " Run <script>alert(\"x\")</script> & 'quoted' "
    page = render_report(_document(_states(_panel(raw))))
    assert f"<h3>{escape(raw)}</h3>" in page
    assert f'data-state-value="{escape(raw)}"' in page
    assert _elements(page).with_class("coda-state")[0]["data-state-value"] == raw
    assert '<script>alert("x")</script>' not in page


def test_panel_ids_are_unique_depth_first_and_reset_for_each_render() -> None:
    inner = _states(_panel("Run A"), _panel("run-a"), dimension="sample")
    outer = _states(_panel("outer", inner), _panel("second"))
    document = _document(
        outer,
        _states(_panel("Run A"), _panel("run-a")),
        extra_tabs=(
            DocumentTab(
                title="Other",
                nodes=(_states(_panel("Run A")),),
            ),
        ),
    )
    first = render_report(document)
    assert render_report(document) == first
    panels = _elements(first).with_class("coda-state")
    assert [panel["id"] for panel in panels] == [
        f"coda-state-{index}" for index in range(1, 8)
    ]
    assert [panel["data-state-value"] for panel in panels] == [
        "outer",
        "Run A",
        "run-a",
        "second",
        "Run A",
        "run-a",
        "Run A",
    ]
    all_ids = [attrs["id"] for _, attrs in _elements(first).elements if "id" in attrs]
    assert len(all_ids) == len(set(all_ids))
    unrelated = render_report(_document(_states(_panel("unrelated"))))
    assert _elements(unrelated).with_class("coda-state")[0]["id"] == "coda-state-1"


def test_states_preserve_existing_component_outcome_rendering() -> None:
    unavailable = ComponentEntry(
        kind=EntryKind.RENDERED,
        component_id="example.quality",
        title="Unavailable",
        outcome=RenderedComponent.unavailable("Missing <data>"),
    )
    failed = ComponentEntry(
        kind=EntryKind.FAILED,
        component_id="example.quality",
        title="Failed",
        error="ValueError: <bad>",
    )
    skipped = ComponentEntry(
        kind=EntryKind.RENDERED,
        component_id="example.quality",
        title="Skipped",
        outcome=RenderedComponent.skipped(),
    )
    page = render_report(
        _document(
            _states(
                _panel(
                    "A",
                    _entry("<p>a &lt; b</p>"),
                    unavailable,
                    failed,
                    skipped,
                )
            )
        )
    )
    assert "<p>a &lt; b</p>" in page
    assert "&amp;lt;" not in page
    assert "Missing &lt;data&gt;" in page
    assert "ValueError: &lt;bad&gt;" in page
    assert len(_elements(page).with_class("coda-card")) == 3
    assert "<h3>Skipped</h3>" not in page


def test_split_scan_descends_through_nested_states_and_deduplicates_rules() -> None:
    row = RowEntry(split=(2.0, 1.0), children=(_entry(), _entry()))
    grid = GridEntry(split=(1.5, 1.0), children=(_entry(),))
    card = CardEntry(
        title="Group",
        layout="row",
        split=None,
        children=(_entry(), _entry()),
    )
    inner = _states(_panel("s1", row, grid, card), dimension="sample")
    outer = _states(_panel("A", inner), _panel("B", row))
    page = render_report(_document(outer))
    assert page.count(".coda-split-2-1 { grid-template-columns: 2fr 1fr; }") == 1
    assert page.count('class="coda-row coda-split-2-1"') == 2
    assert ".coda-split-1p5-1 { grid-template-columns: 1.5fr 1fr; }" in page
    assert ".coda-split-1-1 { grid-template-columns: 1fr 1fr; }" in page
    assert 'class="coda-grid coda-split-1p5-1"' in page
    assert '<div class="coda-group"><h3>Group</h3>' in page


def _nested_figure_document() -> ReportDocument:
    figure = ComponentEntry(
        kind=EntryKind.RENDERED,
        component_id="example.quality",
        title="Figure",
        outcome=RenderedComponent.from_figure(stub_figure()),
    )
    return _document(
        _states(
            _panel(
                "A",
                CardEntry(
                    title=None,
                    layout="stack",
                    split=None,
                    children=(_states(_panel("s1", figure), dimension="sample"),),
                ),
            ),
            _panel("B", figure),
        )
    )


def test_figures_inside_nested_states_inline_plotly_once() -> None:
    plotly_js = (
        importlib.resources.files("plotly") / "package_data" / "plotly.min.js"
    ).read_text(encoding="utf-8")
    page = render_report(_nested_figure_document())
    assert page.count(plotly_js) == 1
    # Was one Plotly script; now Plotly plus merged navigation.
    # Stub figures still carry no bootstrap scripts.
    assert page.count("<script>") == 2
    assert len(_elements(page).with_class("coda-figure")) == 2


def test_missing_plotly_is_detected_for_figures_inside_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "plotly", None)
    with pytest.raises(RenderError, match="Install plotly"):
        render_report(_nested_figure_document())


def test_states_empty_diagnostic_renders_as_an_escaped_note_in_each_marker() -> None:
    note = Diagnostic(
        kind=DiagnosticKind.STATES_EMPTY,
        subject="batch",
        message="Empty axis <batch>: declare values.",
    )
    page = render_report(
        _document(
            _states(
                _panel("A", DiagnosticsEntry()),
                _panel("B", DiagnosticsEntry()),
            ),
            diagnostics=(note,),
        )
    )
    assert len(_elements(page).with_class("coda-diagnostics")) == 2
    assert page.count("<h3>Notes</h3>") == 2
    assert "<h3>Problems</h3>" not in page
    assert (
        page.count(
            '<span class="coda-badge coda-badge--states_empty">states_empty</span>'
        )
        == 2
    )
    assert page.count("Empty axis &lt;batch&gt;: declare values.") == 2


def test_states_style_is_progressive_and_print_keeps_panels_visible() -> None:
    page = render_report(_document(_states(_panel("A"), _panel("B"))))
    assert ".coda-states {" in page
    assert ".coda-state {" in page
    assert ".coda-state > h3 {" in page
    print_blocks = re.findall(
        r"@media print\s*\{((?:[^{}]|\{[^{}]*\})*)\}",
        page,
    )
    assert any(
        re.search(
            r"\.coda-state\s*\{\s*display:\s*block\s*!important\s*;\s*\}",
            block,
        )
        for block in print_blocks
    )
    # Was no selection hiding; now enhancement-only hiding with a
    # stronger print restoration rule.
    assert ".coda-js .coda-state.coda-state--hidden {\n  display: none;" in page
    assert any(
        re.search(
            r"\.coda-js \.coda-state\.coda-state--hidden\s*\{\s*"
            r"display:\s*block\s*!important\s*;\s*\}",
            block,
        )
        for block in print_blocks
    )
    assert len(_elements(page).with_class("coda-state")) == 2
    assert page.count("<script>") == 1


def test_navigation_helpers_inline_once_in_dependency_order() -> None:
    page = render_report(
        _document(
            _states(_panel("A")),
            _states(_panel("B")),
            extra_tabs=(DocumentTab(title="Other", nodes=(_entry(),)),),
        )
    )
    assert page.count("<script>") == 1
    assert page.count("window.codaSelectionURL = Object.freeze") == 1
    assert page.count("window.codaSelectionPolicy = Object.freeze") == 1
    assert page.index("window.codaSelectionURL = Object.freeze") < page.index(
        "window.codaSelectionPolicy = Object.freeze"
    )
    assert page.index("window.codaSelectionPolicy = Object.freeze") < page.index(
        "var codec = window.codaSelectionURL"
    )
    assert 'window.addEventListener("hashchange", apply)' in page
    assert '"coda:state-shown"' in page
    assert "notice.textContent" not in page
    assert "missing[index].textContent" in page
    assert ".removeChild(" not in page
    assert ".innerHTML" not in page
