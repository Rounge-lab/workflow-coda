"""The small states tutorial builds from exactly the files the docs include.

This pins build-time content and enhancement wiring. Native browser
controls, keyboard behavior, no-JS presentation, and print layout still
require browser inspection.
"""

import json
import shutil
from html.parser import HTMLParser
from pathlib import Path

from workflow_coda.artifact_store import ArtifactStore
from workflow_coda.builder import build_report
from workflow_coda.components import ComponentStatus
from workflow_coda.core.plugin import get_plugin
from workflow_coda.registry import PluginRegistry
from workflow_coda.render import render_report
from workflow_coda.report import ComponentEntry, DiagnosticKind, EntryKind, StatesEntry

EXAMPLE = Path(__file__).resolve().parents[1] / "docs" / "examples" / "states-report"
"""The shipped bundle included verbatim in the report-authoring tutorial."""


class _Markup(HTMLParser):
    """Inspect HTML elements without matching class names inside scripts."""

    def __init__(self) -> None:
        super().__init__()
        self.panels: list[dict[str, str | None]] = []
        self.resources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if "coda-state" in (attributes.get("class") or "").split():
            self.panels.append(attributes)
        for name in ("href", "src"):
            value = attributes.get(name)
            if value is not None:
                self.resources.append(value)


def test_states_tutorial_builds_two_complete_batches(tmp_path: Path) -> None:
    # Copy the actual shipped files, never reconstructed payloads:
    # the docs and test therefore exercise the same bundle.
    for name in ("manifest.json", "layout.yaml", "depth-a.json", "depth-b.json"):
        shutil.copy(EXAMPLE / name, tmp_path / name)

    store = ArtifactStore.from_manifest_file(tmp_path / "manifest.json")
    document = build_report(
        tmp_path / "layout.yaml",
        store,
        PluginRegistry((get_plugin(),)),
    )
    assert document.title == "Batch summary"
    assert len(store.manifest.artifacts) == 2
    assert all(
        artifact.path.startswith("depth-") for artifact in store.manifest.artifacts
    )

    (tab,) = document.tabs
    assert tab.title == "Headlines"
    (states,) = tab.nodes
    assert isinstance(states, StatesEntry)
    assert states.dimension == "batch"
    assert states.kind == "categorical"
    assert [panel.value for panel in states.panels] == ["a", "b"]

    page = render_report(document)
    for panel in states.panels:
        raw = panel.value
        (entry,) = panel.children
        assert isinstance(entry, ComponentEntry)
        assert entry.kind is EntryKind.RENDERED
        assert entry.component_id == "core.kpi"
        assert entry.title == f"Mean depth — batch {raw}"
        assert entry.error is None
        assert entry.outcome is not None
        assert entry.outcome.status is ComponentStatus.OK

        artifact_type = f"org.example.sample_metrics-{raw}"
        assert store.require(artifact_type).read_json() == json.loads(
            (tmp_path / f"depth-{raw}.json").read_text(encoding="utf-8")
        )
        assert entry.title in page

    assert not any(
        note.kind
        in (
            DiagnosticKind.PLUGIN_BUG,
            DiagnosticKind.COMPONENT_MISSING,
            DiagnosticKind.COMPONENT_UNAVAILABLE,
        )
        for note in document.diagnostics
    )
    assert "42.7" in page
    assert "18.3" in page
    assert "2 of 2 artifacts completed" in page
    assert 'role="tablist"' not in page
    assert '<section class="coda-diagnostics"' not in page

    markup = _Markup()
    markup.feed(page)
    markup.close()
    assert [panel["data-state-value"] for panel in markup.panels] == ["a", "b"]
    assert [panel["data-state-dimension"] for panel in markup.panels] == [
        "batch",
        "batch",
    ]
    assert [panel["id"] for panel in markup.panels] == [
        "coda-state-1",
        "coda-state-2",
    ]
    assert all("aria-hidden" not in panel for panel in markup.panels)
    assert [
        resource for resource in markup.resources if not resource.startswith("#")
    ] == []

    # Theme controller plus merged navigation, and a component block
    # exactly when the real declarations contribute JavaScript.
    component_scripts = int(any(item.js is not None for item in document.chrome))
    assert page.count("<script>") == 2 + component_scripts
    assert page.count("window.codaSelectionWidgets = Object.freeze") == 1
    assert 'button.setAttribute("role", "combobox")' in page
    assert 'list.setAttribute("role", "listbox")' in page
    assert '<template id="coda-dropdown-icon">' in page
    assert "<select" not in page
    assert "{batch}" not in page


def test_tutorial_includes_the_shipped_states_files() -> None:
    tutorial = (
        EXAMPLE.parents[1] / "source" / "user" / "tutorials" / "hello-report.rst"
    ).read_text(encoding="utf-8")
    for name in ("depth-a.json", "depth-b.json", "manifest.json", "layout.yaml"):
        assert f".. literalinclude:: ../../../examples/states-report/{name}" in tutorial
