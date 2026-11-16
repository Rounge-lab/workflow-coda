"""Tests for the report builder: the happy path, placement resolution
and policy, plugin-bug capture, and declared-then-strict theme and
assets."""

import base64
import re
from pathlib import Path

import pytest
import yaml
from factories import (
    make_component,
    make_layout_payload,
    make_manifest_payload,
    make_metadata,
    make_plugin,
)

from workflow_coda.artifact_store import ArtifactStore, JsonValue
from workflow_coda.builder import build_report
from workflow_coda.components import (
    ComponentParameters,
    ComponentRenderer,
    ComponentStatus,
    PlacementInfo,
    RenderContext,
    RenderedComponent,
)
from workflow_coda.core.plugin import get_plugin
from workflow_coda.errors import ComponentUnavailableError, LayoutError
from workflow_coda.icons import IconLibrary, IconSource
from workflow_coda.manifest import MANIFEST_SCHEMA_VERSION, ReportManifest
from workflow_coda.plugins import ReportPlugin
from workflow_coda.registry import PluginRegistry
from workflow_coda.report import (
    CardEntry,
    ComponentEntry,
    Diagnostic,
    DiagnosticKind,
    DiagnosticsEntry,
    EmbeddedAsset,
    EntryKind,
    GridEntry,
    InlineLogo,
    ReportDocument,
    RowEntry,
)
from workflow_coda.theme import DEFAULT_THEME

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
ICO_MAGIC = b"\x00\x00\x01\x00"
LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    '<path fill="currentColor" d="M12 3l7 18-7-4-7 4z"/>'
    "</svg>"
)
"""A minimal currentColor logo: the file branch's SVG member."""


# ---------------------------------------------------------------------------
# Renderers and the plugins built on them
# ---------------------------------------------------------------------------


def _echo_label(
    _context: RenderContext, _info: PlacementInfo, parameters: ComponentParameters
) -> RenderedComponent:
    """Render the placement's ``label`` parameter, proving parameters
    travel per placement through the builder."""
    return RenderedComponent.from_html(f"<p>{parameters['label']}</p>")


def _raising_render(
    _context: RenderContext, _info: PlacementInfo, _parameters: ComponentParameters
) -> RenderedComponent:
    raise ValueError("boom")


def _garbage_render(
    _context: RenderContext, _info: PlacementInfo, _parameters: ComponentParameters
) -> RenderedComponent:
    # Deliberate contract violation: a render result that is not a
    # RenderedComponent — the builder must collect it as a plugin bug,
    # not let it reach the document.
    return "ok"  # type: ignore[return-value]


def _interrupting_render(
    _context: RenderContext, _info: PlacementInfo, _parameters: ComponentParameters
) -> RenderedComponent:
    raise KeyboardInterrupt


def _unavailable_render(
    _context: RenderContext, _info: PlacementInfo, _parameters: ComponentParameters
) -> RenderedComponent:
    return RenderedComponent.unavailable("the pipeline produced no data")


def _skipping_render(
    _context: RenderContext, _info: PlacementInfo, _parameters: ComponentParameters
) -> RenderedComponent:
    return RenderedComponent.skipped()


def _ok_render(
    _context: RenderContext, _info: PlacementInfo, _parameters: ComponentParameters
) -> RenderedComponent:
    return RenderedComponent.from_html("<p>ok</p>")


def _flaky_render(
    _context: RenderContext, _info: PlacementInfo, parameters: ComponentParameters
) -> RenderedComponent:
    # Raises under a 'boom' parameter, renders OK otherwise — the
    # mixed-outcome fixture for the chrome collection.
    if parameters.get("boom"):
        raise ValueError("boom")
    return RenderedComponent.from_html("<p>ok</p>")


def unavailable_plugin() -> ReportPlugin:
    """Its render returns unavailable: data absence as a run fact."""
    return make_plugin(
        metadata=make_metadata(id="dataless"),
        components=(
            make_component(
                id="dataless.quality",
                title="Dataless metric",
                render=_unavailable_render,
            ),
        ),
    )


def skipping_plugin() -> ReportPlugin:
    """Its render returns skipped: the plugin's deliberate nothing."""
    return make_plugin(
        metadata=make_metadata(id="silent"),
        components=(
            make_component(
                id="silent.quality", title="Silent metric", render=_skipping_render
            ),
        ),
    )


def chromed_plugin() -> ReportPlugin:
    """Two components declaring both css and js: the first-use order
    and dedup fixtures for the chrome collection."""
    return make_plugin(
        metadata=make_metadata(id="styled"),
        components=(
            make_component(
                id="styled.first",
                title="First styled metric",
                render=_ok_render,
                css=".coda-styled-first { color: inherit; }",
                js="console.log('styled.first enhanced');",
            ),
            make_component(
                id="styled.second",
                title="Second styled metric",
                render=_ok_render,
                css=".coda-styled-second { color: inherit; }",
                js="console.log('styled.second enhanced');",
            ),
        ),
    )


def flaky_chromed_plugin() -> ReportPlugin:
    """A chromed component that raises under a ``boom`` parameter and
    renders OK otherwise: the mixed-outcome fixture."""
    return make_plugin(
        metadata=make_metadata(id="flaky"),
        components=(
            make_component(
                id="flaky.quality",
                title="Flaky styled metric",
                render=_flaky_render,
                css=".coda-flaky-quality { color: inherit; }",
                js="console.log('flaky.quality enhanced');",
            ),
        ),
    )


def _chromed_plugin_with_render(
    plugin_id: str, render: ComponentRenderer
) -> ReportPlugin:
    """One chromed component with the given render: the degraded-path
    fixtures share their chrome and differ only in outcome."""
    return make_plugin(
        metadata=make_metadata(id=plugin_id),
        components=(
            make_component(
                id=f"{plugin_id}.quality",
                title=f"{plugin_id} styled metric",
                render=render,
                css=f".coda-{plugin_id}-quality {{ color: inherit; }}",
                js=f"console.log('{plugin_id}.quality enhanced');",
            ),
        ),
    )


def current_plugin() -> ReportPlugin:
    """Supports the manifest's schema version; echoes ``label``."""
    return make_plugin(
        metadata=make_metadata(id="current"),
        components=(
            make_component(
                id="current.quality", title="Sample quality", render=_echo_label
            ),
        ),
    )


def stale_plugin() -> ReportPlugin:
    """Written against an older manifest schema version: loaded, but
    gated out of reports built from current manifests."""
    return make_plugin(
        metadata=make_metadata(
            id="stale", supported_schema_versions=frozenset({"0.0.9"})
        ),
        components=(make_component(id="stale.old", title="Old metric"),),
    )


def broken_plugin() -> ReportPlugin:
    """Its render call raises: a plugin bug, never a build failure."""
    return make_plugin(
        metadata=make_metadata(id="broken"),
        components=(
            make_component(
                id="broken.quality", title="Broken metric", render=_raising_render
            ),
        ),
    )


def garbage_plugin() -> ReportPlugin:
    """Its render call returns a non-outcome: collected through the
    section-entry guard, not a document that chokes the renderer."""
    return make_plugin(
        metadata=make_metadata(id="garbage"),
        components=(
            make_component(
                id="garbage.echo", title="Garbage echo", render=_garbage_render
            ),
        ),
    )


def interrupting_plugin() -> ReportPlugin:
    """Its render raises ``KeyboardInterrupt`` — a BaseException, which
    the builder's bug boundary must not swallow."""
    return make_plugin(
        metadata=make_metadata(id="interrupt"),
        components=(
            make_component(
                id="interrupt.echo",
                title="Interrupting",
                render=_interrupting_render,
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Wiring helpers
# ---------------------------------------------------------------------------


def make_store(tmp_path: Path) -> ArtifactStore:
    """A store for a minimal manifest, rooted at *tmp_path*.

    Nothing here reads artifacts — the renderers are self-contained —
    so the manifest's files need not exist; the store supplies the
    manifest the builder reads and the context carries."""
    manifest = ReportManifest.model_validate(make_manifest_payload())
    return ArtifactStore(manifest, tmp_path)


def write_layout(tmp_path: Path, **overrides: JsonValue) -> Path:
    """Write a layout file from the payload factory, as real YAML.

    ``yaml.safe_dump`` emits exactly the payload (auto-quoting any trap
    words), so the loader is fully in the loop on every build."""
    payload = make_layout_payload(**overrides)
    path = tmp_path / "report_layout.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def write_asset(tmp_path: Path, name: str, data: bytes) -> None:
    (tmp_path / name).write_bytes(data)


def qc_tab(label: str) -> dict[str, JsonValue]:
    """A tab placing ``current.quality`` with a label parameter."""
    return {
        "title": "Quality control",
        "components": [{"id": "current.quality", "parameters": {"label": label}}],
    }


def build(tmp_path: Path, layout_path: Path, *plugins: ReportPlugin) -> ReportDocument:
    """Build with a fixed registry: the standard test wiring."""
    return build_report(layout_path, make_store(tmp_path), PluginRegistry(plugins))


def diagnostics_of(document: ReportDocument, kind: DiagnosticKind) -> list[Diagnostic]:
    return [d for d in document.diagnostics if d.kind is kind]


def diagnostic_subjects(document: ReportDocument, kind: DiagnosticKind) -> list[str]:
    return [d.subject for d in diagnostics_of(document, kind)]


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_builds_the_minimal_report_document(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    layout_path = write_layout(tmp_path, tabs=[qc_tab("run A")])
    document = build_report(layout_path, store, PluginRegistry((current_plugin(),)))
    assert document.title == "Metagenomic analysis"
    assert document.subtitle is None
    assert document.theme is DEFAULT_THEME
    assert document.logo is None
    assert document.favicon is None
    # The manifest is the store's own, not a copy: the document and the
    # store cannot disagree.
    assert document.manifest is store.manifest
    (tab,) = document.tabs
    assert tab.title == "Quality control"
    (entry,) = tab.nodes
    assert isinstance(entry, ComponentEntry)
    assert entry.kind is EntryKind.RENDERED
    assert entry.component_id == "current.quality"
    assert entry.title == "Sample quality"
    assert entry.error is None
    assert entry.outcome is not None
    assert entry.outcome.html == "<p>run A</p>"
    # Omitted theme and assets: informational diagnostics, in the
    # order the builder records them.
    assert [d.kind for d in document.diagnostics] == [
        DiagnosticKind.DEFAULT_THEME,
        DiagnosticKind.LOGO_OMITTED,
        DiagnosticKind.FAVICON_OMITTED,
    ]


def test_registry_defaults_to_the_installed_environment(tmp_path: Path) -> None:
    layout_path = write_layout(tmp_path, tabs=[qc_tab("run A")])
    with pytest.raises(ComponentUnavailableError, match=re.escape("core.kpi")):
        build_report(layout_path, make_store(tmp_path))


# ---------------------------------------------------------------------------
# Unknown components, under each policy
# ---------------------------------------------------------------------------


def test_unknown_component_fails_by_default(tmp_path: Path) -> None:
    layout_path = write_layout(
        tmp_path,
        tabs=[{"title": "QC", "components": [{"id": "nope.nothing"}]}],
    )
    with pytest.raises(
        ComponentUnavailableError,
        match=re.escape("the layout places component 'nope.nothing'")
        + ".*"
        + re.escape("(available: current.quality)"),
    ):
        build(tmp_path, layout_path, current_plugin())


def test_unknown_component_noticed_and_omitted(tmp_path: Path) -> None:
    layout_path = write_layout(
        tmp_path,
        on_missing="notice",
        tabs=[
            {
                "title": "QC",
                "components": [
                    {"id": "current.quality", "parameters": {"label": "run A"}},
                    {"id": "nope.nothing"},
                ],
            }
        ],
    )
    document = build(tmp_path, layout_path, current_plugin())
    (tab,) = document.tabs
    (entry,) = tab.nodes
    assert isinstance(entry, ComponentEntry)
    assert entry.component_id == "current.quality"
    assert diagnostic_subjects(document, DiagnosticKind.COMPONENT_MISSING) == [
        "nope.nothing"
    ]
    (missing,) = diagnostics_of(document, DiagnosticKind.COMPONENT_MISSING)
    assert "omitted" in missing.message
    assert "current.quality" in missing.message


def test_unknown_component_skipped_silently(tmp_path: Path) -> None:
    # The section's only placement resolves away, so the section is
    # dropped: no entries, and nothing in diagnostics about it.
    layout_path = write_layout(
        tmp_path,
        on_missing="skip",
        tabs=[{"title": "QC", "components": [{"id": "nope.nothing"}]}],
    )
    document = build(tmp_path, layout_path, current_plugin())
    assert document.tabs == ()
    assert diagnostic_subjects(document, DiagnosticKind.COMPONENT_MISSING) == []


# ---------------------------------------------------------------------------
# Schema-excluded plugins, under each policy
# ---------------------------------------------------------------------------


def test_excluded_plugin_fails_with_the_version_story(tmp_path: Path) -> None:
    layout_path = write_layout(
        tmp_path,
        tabs=[{"title": "Old", "components": [{"id": "stale.old"}]}],
    )
    with pytest.raises(
        ComponentUnavailableError,
        match=re.escape(
            "its plugin 'stale' does not support this manifest's "
            f"schema version '{MANIFEST_SCHEMA_VERSION}' (it supports: 0.0.9)"
        ),
    ):
        build(tmp_path, layout_path, current_plugin(), stale_plugin())


def test_excluded_plugin_noticed_with_the_version_story(tmp_path: Path) -> None:
    layout_path = write_layout(
        tmp_path,
        on_missing="notice",
        tabs=[{"title": "Old", "components": [{"id": "stale.old"}]}],
    )
    document = build(tmp_path, layout_path, current_plugin(), stale_plugin())
    assert document.tabs == ()
    assert diagnostic_subjects(document, DiagnosticKind.PLUGIN_EXCLUDED) == ["stale"]
    (excluded,) = diagnostics_of(document, DiagnosticKind.PLUGIN_EXCLUDED)
    assert "0.0.9" in excluded.message
    assert MANIFEST_SCHEMA_VERSION in excluded.message


# ---------------------------------------------------------------------------
# Unavailable outcomes, under each policy
# ---------------------------------------------------------------------------


def test_unavailable_notices_by_default(tmp_path: Path) -> None:
    # The default preserves today's behavior: the entry stands, the
    # renderer paints the notice card, and the ledger records nothing.
    layout_path = write_layout(
        tmp_path, tabs=[{"title": "QC", "components": [{"id": "dataless.quality"}]}]
    )
    document = build(tmp_path, layout_path, unavailable_plugin())
    (tab,) = document.tabs
    (entry,) = tab.nodes
    assert isinstance(entry, ComponentEntry)
    assert entry.kind is EntryKind.RENDERED
    assert entry.outcome is not None
    assert entry.outcome.status is ComponentStatus.UNAVAILABLE
    assert diagnostic_subjects(document, DiagnosticKind.COMPONENT_UNAVAILABLE) == []


def test_unavailable_skip_omits_and_records_the_note(tmp_path: Path) -> None:
    # The component leaves the page, not the ledger — and it is a
    # note: expected pipeline behavior, rendered in the notes group.
    layout_path = write_layout(
        tmp_path,
        on_unavailable="skip",
        tabs=[{"title": "QC", "components": [{"id": "dataless.quality"}]}],
    )
    document = build(tmp_path, layout_path, unavailable_plugin())
    assert document.tabs == ()
    (note,) = diagnostics_of(document, DiagnosticKind.COMPONENT_UNAVAILABLE)
    assert note.subject == "dataless.quality"
    assert "omitted" in note.message
    assert "the pipeline produced no data" in note.message
    assert note.kind.is_problem is False


def test_unavailable_skip_collapses_emptied_compositions(tmp_path: Path) -> None:
    # The walk's upward collapse is shared machinery: a row whose
    # children all skip produces no node, and the emptied tab drops
    # — the notes already explain why.
    layout_path = write_layout(
        tmp_path,
        on_unavailable="skip",
        tabs=[
            {
                "title": "QC",
                "components": [
                    {
                        "type": "row",
                        "children": [
                            {"id": "dataless.quality"},
                            {"id": "dataless.quality"},
                        ],
                    }
                ],
            }
        ],
    )
    document = build(tmp_path, layout_path, unavailable_plugin())
    assert document.tabs == ()
    assert len(diagnostic_subjects(document, DiagnosticKind.COMPONENT_UNAVAILABLE)) == 2


def test_partial_unavailable_skip_keeps_the_survivors(tmp_path: Path) -> None:
    layout_path = write_layout(
        tmp_path,
        on_unavailable="skip",
        tabs=[
            {
                "title": "QC",
                "components": [
                    {
                        "type": "row",
                        "split": [2, 1],
                        "children": [
                            {"id": "dataless.quality"},
                            {"id": "current.quality", "parameters": {"label": "A"}},
                        ],
                    }
                ],
            }
        ],
    )
    document = build(tmp_path, layout_path, current_plugin(), unavailable_plugin())
    (node,) = document.tabs[0].nodes
    assert isinstance(node, RowEntry)
    assert len(node.children) == 1
    assert diagnostic_subjects(document, DiagnosticKind.COMPONENT_UNAVAILABLE) == [
        "dataless.quality"
    ]


def test_unavailable_fail_refuses_the_build(tmp_path: Path) -> None:
    layout_path = write_layout(
        tmp_path,
        on_unavailable="fail",
        tabs=[{"title": "QC", "components": [{"id": "dataless.quality"}]}],
    )
    with pytest.raises(
        ComponentUnavailableError,
        match=re.escape("the layout places component 'dataless.quality'")
        + ".*"
        + re.escape("the pipeline produced no data"),
    ):
        build(tmp_path, layout_path, unavailable_plugin())


def test_skip_does_not_govern_plugin_bugs(tmp_path: Path) -> None:
    # A bug is not a data fact: even under on_unavailable: skip, the
    # failure card stands and the plugin_bug diagnostic is recorded.
    layout_path = write_layout(
        tmp_path,
        on_unavailable="skip",
        tabs=[{"title": "QC", "components": [{"id": "broken.quality"}]}],
    )
    document = build(tmp_path, layout_path, broken_plugin())
    (tab,) = document.tabs
    (entry,) = tab.nodes
    assert isinstance(entry, ComponentEntry)
    assert entry.kind is EntryKind.FAILED
    assert diagnostic_subjects(document, DiagnosticKind.PLUGIN_BUG) == [
        "broken.quality"
    ]


def test_skip_does_not_govern_deliberate_skips(tmp_path: Path) -> None:
    # A plugin's own SKIPPED outcome already renders nothing; the
    # policy adds no diagnostic for it.
    layout_path = write_layout(
        tmp_path,
        on_unavailable="skip",
        tabs=[{"title": "QC", "components": [{"id": "silent.quality"}]}],
    )
    document = build(tmp_path, layout_path, skipping_plugin())
    (entry,) = document.tabs[0].nodes
    assert isinstance(entry, ComponentEntry)
    assert entry.outcome is not None
    assert entry.outcome.status is ComponentStatus.SKIPPED
    assert diagnostic_subjects(document, DiagnosticKind.COMPONENT_UNAVAILABLE) == []


def test_on_missing_does_not_govern_unavailable_data(tmp_path: Path) -> None:
    # The orthogonality your sanity run discovered, pinned: an
    # installed component under on_missing: skip still notices its
    # missing data — resolution succeeded, so the resolution policy
    # has nothing to say.
    layout_path = write_layout(
        tmp_path,
        on_missing="skip",
        tabs=[{"title": "QC", "components": [{"id": "dataless.quality"}]}],
    )
    document = build(tmp_path, layout_path, unavailable_plugin())
    (tab,) = document.tabs
    (entry,) = tab.nodes
    assert isinstance(entry, ComponentEntry)
    assert entry.outcome is not None
    assert entry.outcome.status is ComponentStatus.UNAVAILABLE


# ---------------------------------------------------------------------------
# The chrome collection: page chrome rides the placements that render
# ---------------------------------------------------------------------------


def test_chrome_collects_in_first_use_order(tmp_path: Path) -> None:
    # Two chromed components placed in reverse declaration order: the
    # document's chrome follows placement order, not registry order —
    # the page's style and script blocks appear in the order the
    # report introduces their components.
    layout_path = write_layout(
        tmp_path,
        tabs=[
            {
                "title": "QC",
                "components": [{"id": "styled.second"}, {"id": "styled.first"}],
            }
        ],
    )
    document = build(tmp_path, layout_path, chromed_plugin())
    assert [c.component_id for c in document.chrome] == [
        "styled.second",
        "styled.first",
    ]


def test_chrome_collects_once_per_component(tmp_path: Path) -> None:
    # However many placements render, the component's chrome is
    # inlined once — and the contribution carries the declaration's
    # strings verbatim, resolved through the registry.
    layout_path = write_layout(
        tmp_path,
        tabs=[{"title": "QC", "components": [{"id": "styled.first"}] * 3}],
    )
    document = build(tmp_path, layout_path, chromed_plugin())
    assert len(document.chrome) == 1
    (contribution,) = document.chrome
    assert contribution.component_id == "styled.first"
    assert contribution.css == ".coda-styled-first { color: inherit; }"
    assert contribution.js == "console.log('styled.first enhanced');"


def test_a_bug_placement_does_not_prevent_the_later_ok_from_collecting(
    tmp_path: Path,
) -> None:
    # The predicate records OK outcomes and skips FAILED entries: a
    # component placed boom-first, ok-second collects exactly once,
    # and the failure card stands in the page beside the render that
    # succeeded.
    layout_path = write_layout(
        tmp_path,
        tabs=[
            {
                "title": "QC",
                "components": [
                    {"id": "flaky.quality", "parameters": {"boom": True}},
                    {"id": "flaky.quality"},
                ],
            }
        ],
    )
    document = build(tmp_path, layout_path, flaky_chromed_plugin())
    assert [c.component_id for c in document.chrome] == ["flaky.quality"]
    kinds = [
        node.kind for node in document.tabs[0].nodes if isinstance(node, ComponentEntry)
    ]
    assert kinds == [EntryKind.FAILED, EntryKind.RENDERED]


@pytest.mark.parametrize(
    ("plugin_id", "render"),
    [
        ("styledless", _unavailable_render),
        ("brokenstyled", _raising_render),
        ("silentstyled", _skipping_render),
    ],
)
def test_degraded_only_placements_contribute_no_chrome(
    tmp_path: Path, plugin_id: str, render: ComponentRenderer
) -> None:
    # The predicate is OK-outcomes only.  The unavailable and bug
    # paths render the framework's own notice and failure cards —
    # no plugin chrome needed.  The skip case pins the status clause
    # itself: a RENDERED entry with a SKIPPED outcome must not
    # collect, though a kind-only predicate would let it through.
    layout_path = write_layout(
        tmp_path,
        tabs=[{"title": "QC", "components": [{"id": f"{plugin_id}.quality"}]}],
    )
    document = build(
        tmp_path, layout_path, _chromed_plugin_with_render(plugin_id, render)
    )
    assert document.chrome == ()


def test_chromeless_components_render_without_contributions(tmp_path: Path) -> None:
    # The collection records what rendered; the resolution filters by
    # what was declared — an OK render of a chrome-less component
    # yields an empty chrome tuple.
    layout_path = write_layout(
        tmp_path,
        tabs=[
            {
                "title": "QC",
                "components": [{"id": "current.quality", "parameters": {"label": "A"}}],
            }
        ],
    )
    document = build(tmp_path, layout_path, current_plugin())
    assert document.chrome == ()


# ---------------------------------------------------------------------------
# Per-placement policy overrides
# ---------------------------------------------------------------------------


def test_placement_fail_overrides_the_layout_notice(tmp_path: Path) -> None:
    layout_path = write_layout(
        tmp_path,
        on_missing="notice",
        tabs=[
            {
                "title": "QC",
                "components": [{"id": "nope.nothing", "on_missing": "fail"}],
            }
        ],
    )
    with pytest.raises(
        ComponentUnavailableError,
        match=re.escape("the layout places component 'nope.nothing'"),
    ):
        build(tmp_path, layout_path, current_plugin())


def test_placement_notice_overrides_the_layout_fail(tmp_path: Path) -> None:
    layout_path = write_layout(
        tmp_path,
        tabs=[
            {
                "title": "QC",
                "components": [{"id": "nope.nothing", "on_missing": "notice"}],
            }
        ],
    )
    document = build(tmp_path, layout_path, current_plugin())
    assert diagnostic_subjects(document, DiagnosticKind.COMPONENT_MISSING) == [
        "nope.nothing"
    ]


def test_placement_on_unavailable_fail_overrides_the_layout_notice(
    tmp_path: Path,
) -> None:
    layout_path = write_layout(
        tmp_path,
        on_unavailable="notice",
        tabs=[
            {
                "title": "QC",
                "components": [{"id": "dataless.quality", "on_unavailable": "fail"}],
            }
        ],
    )
    with pytest.raises(
        ComponentUnavailableError,
        match=re.escape("the layout places component 'dataless.quality'"),
    ):
        build(tmp_path, layout_path, unavailable_plugin())


def test_placement_on_unavailable_notice_overrides_the_layout_skip(
    tmp_path: Path,
) -> None:
    layout_path = write_layout(
        tmp_path,
        on_unavailable="skip",
        tabs=[
            {
                "title": "QC",
                "components": [{"id": "dataless.quality", "on_unavailable": "notice"}],
            }
        ],
    )
    document = build(tmp_path, layout_path, unavailable_plugin())
    (tab,) = document.tabs
    (entry,) = tab.nodes
    assert isinstance(entry, ComponentEntry)
    assert entry.outcome is not None
    assert entry.outcome.status is ComponentStatus.UNAVAILABLE
    assert diagnostic_subjects(document, DiagnosticKind.COMPONENT_UNAVAILABLE) == []


# ---------------------------------------------------------------------------
# Placement instances and section assembly
# ---------------------------------------------------------------------------


def test_the_same_component_places_twice_with_its_own_parameters(
    tmp_path: Path,
) -> None:
    layout_path = write_layout(
        tmp_path,
        tabs=[
            {
                "title": "QC",
                "components": [
                    {"id": "current.quality", "parameters": {"label": "run A"}},
                    {"id": "current.quality", "parameters": {"label": "run B"}},
                ],
            }
        ],
    )
    document = build(tmp_path, layout_path, current_plugin())
    (tab,) = document.tabs
    htmls = [
        node.outcome.html
        for node in tab.nodes
        if isinstance(node, ComponentEntry) and node.outcome is not None
    ]
    assert htmls == ["<p>run A</p>", "<p>run B</p>"]


def test_tabs_survive_in_layout_order(tmp_path: Path) -> None:
    layout_path = write_layout(
        tmp_path,
        tabs=[
            qc_tab("one"),
            {
                "title": "Taxonomy",
                "components": [
                    {"id": "current.quality", "parameters": {"label": "two"}}
                ],
            },
        ],
    )
    document = build(tmp_path, layout_path, current_plugin())
    assert [tab.title for tab in document.tabs] == [
        "Quality control",
        "Taxonomy",
    ]


def test_emptied_tabs_are_dropped_rendered_tabs_survive(
    tmp_path: Path,
) -> None:
    layout_path = write_layout(
        tmp_path,
        on_missing="notice",
        tabs=[
            qc_tab("run A"),
            {"title": "Old", "components": [{"id": "nope.nothing"}]},
        ],
    )
    document = build(tmp_path, layout_path, current_plugin())
    [tab] = document.tabs
    assert tab.title == "Quality control"
    assert diagnostic_subjects(document, DiagnosticKind.COMPONENT_MISSING) == [
        "nope.nothing"
    ]


def test_the_render_call_receives_the_resolved_title(tmp_path: Path) -> None:
    # The signature's middle argument: the placement's own title when
    # the layout names the instance, the declaration's default
    # otherwise — a TILE component paints it itself.
    seen: list[str] = []

    def title_echo(
        _context: RenderContext, info: PlacementInfo, _parameters: ComponentParameters
    ) -> RenderedComponent:
        seen.append(info.title)
        return RenderedComponent.from_html("<p>ok</p>")

    titled_plugin = make_plugin(
        metadata=make_metadata(id="current"),
        components=(
            make_component(
                id="current.quality", title="Sample quality", render=title_echo
            ),
        ),
    )
    layout_path = write_layout(
        tmp_path,
        tabs=[
            {
                "title": "QC",
                "components": [
                    {"id": "current.quality", "parameters": {"label": "A"}},
                    {
                        "id": "current.quality",
                        "title": "Override",
                        "parameters": {"label": "B"},
                    },
                ],
            }
        ],
    )
    document = build(tmp_path, layout_path, titled_plugin)
    (one_tab,) = document.tabs
    titles = [node.title for node in one_tab.nodes if isinstance(node, ComponentEntry)]
    assert titles == ["Sample quality", "Override"]
    assert seen == ["Sample quality", "Override"]


# ---------------------------------------------------------------------------
# Plugin bugs
# ---------------------------------------------------------------------------


def test_plugin_bug_becomes_a_failed_entry_and_diagnostic(tmp_path: Path) -> None:
    layout_path = write_layout(
        tmp_path,
        tabs=[
            {
                "title": "QC",
                "components": [
                    {"id": "broken.quality", "parameters": {"label": "run A"}}
                ],
            }
        ],
    )
    document = build(tmp_path, layout_path, broken_plugin())
    (tab,) = document.tabs
    (entry,) = tab.nodes
    assert isinstance(entry, ComponentEntry)
    assert entry.kind is EntryKind.FAILED
    assert entry.component_id == "broken.quality"
    assert entry.title == "Broken metric"
    assert entry.outcome is None
    assert entry.error == "ValueError: boom"
    assert diagnostic_subjects(document, DiagnosticKind.PLUGIN_BUG) == [
        "broken.quality"
    ]
    (bug,) = diagnostics_of(document, DiagnosticKind.PLUGIN_BUG)
    assert "raised ValueError: boom" in bug.message


def test_garbage_render_result_is_collected_as_a_plugin_bug(tmp_path: Path) -> None:
    # The tightened section-entry guard fires inside the builder's
    # try, so a non-outcome render result surfaces as a plugin bug —
    # not as a document the rendering layer would choke on.
    layout_path = write_layout(
        tmp_path,
        tabs=[{"title": "QC", "components": [{"id": "garbage.echo"}]}],
    )
    document = build(tmp_path, layout_path, garbage_plugin())
    (entry,) = document.tabs[0].nodes
    assert isinstance(entry, ComponentEntry)
    assert entry.kind is EntryKind.FAILED
    assert entry.error is not None
    assert "must be a RenderedComponent" in entry.error
    assert diagnostic_subjects(document, DiagnosticKind.PLUGIN_BUG) == ["garbage.echo"]


def test_keyboard_interrupt_propagates_from_render(tmp_path: Path) -> None:
    # The bug boundary is ``Exception``: control-flow interruptions
    # are BaseExceptions and must pass through, never be collected.
    layout_path = write_layout(
        tmp_path,
        tabs=[{"title": "QC", "components": [{"id": "interrupt.echo"}]}],
    )
    with pytest.raises(KeyboardInterrupt):
        build(tmp_path, layout_path, interrupting_plugin())


def test_an_old_signature_renderer_is_collected_as_a_plugin_bug(
    tmp_path: Path,
) -> None:
    # Third-party plugins are not mypy-checked: a renderer still
    # written against the two-argument signature raises TypeError at
    # the builder's call — inside the bug boundary, so it degrades to
    # a visible failure card, never a crash.
    def old_signature_render(
        _context: RenderContext, _parameters: ComponentParameters
    ) -> RenderedComponent:
        return RenderedComponent.skipped()

    old_plugin = make_plugin(
        metadata=make_metadata(id="oldsig"),
        components=(
            make_component(
                id="oldsig.quality",
                title="Old signature",
                render=old_signature_render,  # type: ignore[arg-type]
            ),
        ),
    )
    layout_path = write_layout(
        tmp_path, tabs=[{"title": "QC", "components": [{"id": "oldsig.quality"}]}]
    )
    document = build(tmp_path, layout_path, old_plugin)
    (entry,) = document.tabs[0].nodes
    assert isinstance(entry, ComponentEntry)
    assert entry.kind is EntryKind.FAILED
    assert entry.error is not None
    assert "TypeError" in entry.error
    assert diagnostic_subjects(document, DiagnosticKind.PLUGIN_BUG) == [
        "oldsig.quality"
    ]


# ---------------------------------------------------------------------------
# Declared theme, then strict
# ---------------------------------------------------------------------------


def test_declared_theme_loads_and_displaces_the_default_diagnostic(
    tmp_path: Path,
) -> None:
    # The theme file is derived from the default theme, so the test
    # stays robust to the token set.
    (tmp_path / "custom_theme.yaml").write_text(
        yaml.safe_dump(DEFAULT_THEME.model_dump()), encoding="utf-8"
    )
    layout_path = write_layout(
        tmp_path, theme="custom_theme.yaml", tabs=[qc_tab("run A")]
    )
    document = build(tmp_path, layout_path, current_plugin())
    assert document.theme == DEFAULT_THEME
    assert diagnostics_of(document, DiagnosticKind.DEFAULT_THEME) == []


def test_declared_theme_must_be_readable(tmp_path: Path) -> None:
    layout_path = write_layout(
        tmp_path, theme="missing_theme.yaml", tabs=[qc_tab("run A")]
    )
    with pytest.raises(LayoutError, match="cannot read the theme file"):
        build(tmp_path, layout_path, current_plugin())


def test_declared_theme_must_be_valid(tmp_path: Path) -> None:
    payload = DEFAULT_THEME.model_dump()
    payload["series"] = "not a list"
    (tmp_path / "custom_theme.yaml").write_text(
        yaml.safe_dump(payload), encoding="utf-8"
    )
    layout_path = write_layout(
        tmp_path, theme="custom_theme.yaml", tabs=[qc_tab("run A")]
    )
    with pytest.raises(LayoutError, match=re.escape("is not a valid theme")):
        build(tmp_path, layout_path, current_plugin())


def test_declared_theme_must_be_a_mapping(tmp_path: Path) -> None:
    (tmp_path / "custom_theme.yaml").write_text("- just\n- a list\n", encoding="utf-8")
    layout_path = write_layout(
        tmp_path, theme="custom_theme.yaml", tabs=[qc_tab("run A")]
    )
    with pytest.raises(
        LayoutError, match=re.escape("must be a mapping of theme tokens")
    ):
        build(tmp_path, layout_path, current_plugin())


def test_theme_duplicate_keys_rejected(tmp_path: Path) -> None:
    (tmp_path / "custom_theme.yaml").write_text(
        "name: one\nname: two\n", encoding="utf-8"
    )
    layout_path = write_layout(
        tmp_path, theme="custom_theme.yaml", tabs=[qc_tab("run A")]
    )
    with pytest.raises(
        LayoutError,
        match=re.escape("not valid YAML: duplicate key 'name' on line 2"),
    ):
        build(tmp_path, layout_path, current_plugin())


def test_omitted_header_color_means_primary(tmp_path: Path) -> None:
    # A styling default, not an omission: no diagnostic, and the
    # document carries None — the renderer derives primary.
    layout_path = write_layout(tmp_path, tabs=[qc_tab("run A")])
    document = build(tmp_path, layout_path, current_plugin())
    assert document.header_color is None
    assert not any(d.subject == "header_color" for d in document.diagnostics)


def test_declared_header_color_carries_to_the_document(tmp_path: Path) -> None:
    layout_path = write_layout(tmp_path, header_color="accent", tabs=[qc_tab("run A")])
    document = build(tmp_path, layout_path, current_plugin())
    assert document.header_color == "accent"


def test_unknown_header_color_token_teaches_the_theme_vocabulary(
    tmp_path: Path,
) -> None:
    layout_path = write_layout(tmp_path, header_color="shiny", tabs=[qc_tab("run A")])
    with pytest.raises(
        LayoutError,
        match=re.escape("declares header_color 'shiny'")
        + ".*"
        + re.escape("declare the token in the theme"),
    ):
        build(tmp_path, layout_path, current_plugin())


def test_header_color_literals_teach_the_token_law(tmp_path: Path) -> None:
    # The literal trap, taught by the layout model before any theme
    # is loaded: a color literal is not a token name.
    layout_path = write_layout(tmp_path, header_color="#ff0000", tabs=[qc_tab("run A")])
    with pytest.raises(LayoutError, match="never a color literal"):
        build(tmp_path, layout_path, current_plugin())


# ---------------------------------------------------------------------------
# Declared assets, then strict
# ---------------------------------------------------------------------------


def test_declared_logo_embeds_as_a_data_uri(tmp_path: Path) -> None:
    data = PNG_MAGIC + b"fake-png-payload"
    write_asset(tmp_path, "logo.png", data)
    layout_path = write_layout(tmp_path, logo="logo.png", tabs=[qc_tab("run A")])
    document = build(tmp_path, layout_path, current_plugin())
    assert document.logo is not None
    # The logo is a two-shape union since InlineLogo arrived: this
    # fixture pins the file branch — the data URI — and the assert
    # narrows the union for the attribute reads below; the icon-name
    # branch gets its own tests with the builder feature.
    assert isinstance(document.logo, EmbeddedAsset)
    assert document.logo.path == "logo.png"
    assert document.logo.media_type == "image/png"
    expected = "data:image/png;base64," + base64.b64encode(data).decode("ascii")
    assert document.logo.data_uri == expected
    assert diagnostics_of(document, DiagnosticKind.LOGO_OMITTED) == []


def test_declared_favicon_embeds_as_a_data_uri(tmp_path: Path) -> None:
    data = ICO_MAGIC + b"fake-ico-payload"
    write_asset(tmp_path, "favicon.ico", data)
    layout_path = write_layout(tmp_path, favicon="favicon.ico", tabs=[qc_tab("run A")])
    document = build(tmp_path, layout_path, current_plugin())
    assert document.favicon is not None
    assert document.favicon.media_type == "image/x-icon"
    assert document.favicon.data_uri.startswith("data:image/x-icon;base64,")
    assert diagnostics_of(document, DiagnosticKind.FAVICON_OMITTED) == []


def test_declared_logo_must_exist(tmp_path: Path) -> None:
    layout_path = write_layout(
        tmp_path, logo="missing_logo.png", tabs=[qc_tab("run A")]
    )
    with pytest.raises(
        LayoutError,
        match=re.escape("cannot read the declared logo 'missing_logo.png'"),
    ):
        build(tmp_path, layout_path, current_plugin())


def test_declared_logo_must_have_a_supported_extension(tmp_path: Path) -> None:
    write_asset(tmp_path, "logo.tiff", PNG_MAGIC + b"payload")
    layout_path = write_layout(tmp_path, logo="logo.tiff", tabs=[qc_tab("run A")])
    with pytest.raises(LayoutError, match="not a supported image type"):
        build(tmp_path, layout_path, current_plugin())


def test_declared_logo_must_match_its_extension(tmp_path: Path) -> None:
    write_asset(tmp_path, "logo.png", b"definitely not a png")
    layout_path = write_layout(tmp_path, logo="logo.png", tabs=[qc_tab("run A")])
    with pytest.raises(
        LayoutError, match=re.escape("does not look like a valid image/png file")
    ):
        build(tmp_path, layout_path, current_plugin())


def test_no_informational_diagnostics_when_everything_is_declared(
    tmp_path: Path,
) -> None:
    (tmp_path / "custom_theme.yaml").write_text(
        yaml.safe_dump(DEFAULT_THEME.model_dump()), encoding="utf-8"
    )
    write_asset(tmp_path, "logo.png", PNG_MAGIC + b"payload")
    write_asset(tmp_path, "favicon.ico", ICO_MAGIC + b"payload")
    layout_path = write_layout(
        tmp_path,
        theme="custom_theme.yaml",
        logo="logo.png",
        favicon="favicon.ico",
        tabs=[qc_tab("run A")],
    )
    document = build(tmp_path, layout_path, current_plugin())
    assert document.diagnostics == ()
    assert document.logo is not None
    assert document.favicon is not None


def test_theme_fonts_flow_to_the_document(tmp_path: Path) -> None:
    payload = DEFAULT_THEME.model_dump()
    payload["font_heading"] = "Georgia, serif"
    (tmp_path / "custom_theme.yaml").write_text(
        yaml.safe_dump(payload), encoding="utf-8"
    )
    layout_path = write_layout(
        tmp_path, theme="custom_theme.yaml", tabs=[qc_tab("run A")]
    )
    document = build(tmp_path, layout_path, current_plugin())
    assert document.theme.font_heading == "Georgia, serif"


def test_the_layout_author_carries_to_the_document(tmp_path: Path) -> None:
    layout_path = write_layout(
        tmp_path, author="The Genomics Group", tabs=[qc_tab("run A")]
    )
    document = build(tmp_path, layout_path, current_plugin())
    assert document.author == "The Genomics Group"


def test_the_layout_version_carries_to_the_document(tmp_path: Path) -> None:
    layout_path = write_layout(tmp_path, version="1.2.0", tabs=[qc_tab("run A")])
    document = build(tmp_path, layout_path, current_plugin())
    assert document.version == "1.2.0"


def _core_registry() -> PluginRegistry:
    """The real core plugin's registry: the logo's icon-name branch
    loads through the build's real icon library — the same plugin
    the seam builds through."""
    return PluginRegistry((get_plugin(),))


def _logo_tab() -> dict[str, JsonValue]:
    """A diagnostics-only tab: the logo tests place no components —
    the tab grammar needs one node, and the diagnostics marker
    needs nothing."""
    return {"title": "QC", "components": [{"type": "diagnostics"}]}


def test_icon_named_logo_inlines_the_shipped_markup(tmp_path: Path) -> None:
    # The logo's second vocabulary: a bundled icon's name — no path
    # separators, no dots — loads through the build's library, the
    # same door the KPI's icon parameter reads.  The expected
    # markup derives through the same door: like compared with
    # like.
    layout_path = write_layout(tmp_path, logo="core-arrow-up", tabs=[_logo_tab()])
    document = build_report(layout_path, make_store(tmp_path), _core_registry())
    assert isinstance(document.logo, InlineLogo)
    assert document.logo.source == "core-arrow-up"
    library = IconLibrary([IconSource.for_plugin("core", "workflow_coda.core")])
    assert document.logo.markup == library.load("core-arrow-up").markup


def test_unknown_icon_named_logo_teaches_the_roster(tmp_path: Path) -> None:
    # The icon branch's own typo family: the roster the environment
    # ships rides the teaching.
    layout_path = write_layout(tmp_path, logo="core-arrow-uup", tabs=[_logo_tab()])
    with pytest.raises(
        LayoutError,
        match=re.escape("unknown icon 'core-arrow-uup'")
        + ".*"
        + re.escape("installed plugins ship:")
        + ".*"
        + re.escape("core-arrow-up"),
    ):
        build_report(layout_path, make_store(tmp_path), _core_registry())


def test_svg_file_logo_inlines_through_the_validator(tmp_path: Path) -> None:
    # The file branch's SVG member: a data-URI <img> could never
    # inherit the header's ink — an image is an isolated document —
    # so an SVG file inlines as sanitized markup, the same
    # deny-by-default boundary every shipped icon crosses, with
    # the file's own currentColor riding through.
    write_asset(tmp_path, "logo.svg", LOGO_SVG.encode("utf-8"))
    layout_path = write_layout(tmp_path, logo="logo.svg", tabs=[_logo_tab()])
    document = build(tmp_path, layout_path, current_plugin())
    assert isinstance(document.logo, InlineLogo)
    assert document.logo.source == "logo.svg"
    assert document.logo.markup.startswith("<svg")
    assert 'class="coda-icon"' in document.logo.markup
    assert 'aria-hidden="true"' in document.logo.markup
    assert 'fill="currentColor"' in document.logo.markup


def test_an_svg_file_logo_that_fails_validation_teaches(tmp_path: Path) -> None:
    # The validator is the boundary for user SVGs too: a logo
    # carrying an element outside the allowlist fails the build,
    # the offender named — never ships silently into a report.
    write_asset(
        tmp_path,
        "logo.svg",
        (
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            b"<text>logo</text></svg>"
        ),
    )
    layout_path = write_layout(tmp_path, logo="logo.svg", tabs=[_logo_tab()])
    with pytest.raises(LayoutError, match=re.escape("element <text> is not allowed")):
        build(tmp_path, layout_path, current_plugin())


def test_dotted_logo_names_stay_file_addresses(tmp_path: Path) -> None:
    # The shape law's honest routing: a dot means a file, even when
    # the name looks icon-ish — an icon typo'd with an extension
    # teaches the file branch's own lesson, not a misleading roster.
    layout_path = write_layout(tmp_path, logo="core-arrow-up.svg", tabs=[_logo_tab()])
    with pytest.raises(
        LayoutError,
        match=re.escape("cannot read the declared logo 'core-arrow-up.svg'"),
    ):
        build(tmp_path, layout_path, current_plugin())


# ---------------------------------------------------------------------------
# The composition walk
# ---------------------------------------------------------------------------


def test_row_children_render_in_order(tmp_path: Path) -> None:
    layout_path = write_layout(
        tmp_path,
        tabs=[
            {
                "title": "QC",
                "components": [
                    {
                        "type": "row",
                        "split": [2, 1],
                        "children": [
                            {"id": "current.quality", "parameters": {"label": "A"}},
                            {"id": "current.quality", "parameters": {"label": "B"}},
                        ],
                    }
                ],
            }
        ],
    )
    document = build(tmp_path, layout_path, current_plugin())
    (tab,) = document.tabs
    (node,) = tab.nodes
    assert isinstance(node, RowEntry)
    assert node.split == (2.0, 1.0)
    labels = [
        child.outcome.html
        for child in node.children
        if isinstance(child, ComponentEntry) and child.outcome is not None
    ]
    assert labels == ["<p>A</p>", "<p>B</p>"]


def test_grid_children_flow_with_column_ratios(tmp_path: Path) -> None:
    # Three children in two columns: the split gives columns, not
    # children — the short last row is the design.
    layout_path = write_layout(
        tmp_path,
        tabs=[
            {
                "title": "QC",
                "components": [
                    {
                        "type": "grid",
                        "split": [1, 1],
                        "children": [
                            {"id": "current.quality", "parameters": {"label": n}}
                            for n in ("A", "B", "C")
                        ],
                    }
                ],
            }
        ],
    )
    document = build(tmp_path, layout_path, current_plugin())
    (node,) = document.tabs[0].nodes
    assert isinstance(node, GridEntry)
    assert node.split == (1.0, 1.0)
    assert len(node.children) == 3


def test_composition_collapses_when_all_children_resolve_away(tmp_path: Path) -> None:
    # notice empties the row; an emptied row produces no node, and a
    # tab left with no nodes drops — the collapse rule at every level.
    layout_path = write_layout(
        tmp_path,
        on_missing="notice",
        tabs=[
            {
                "title": "QC",
                "components": [
                    {
                        "type": "row",
                        "children": [{"id": "nope.nothing"}, {"id": "nope.other"}],
                    }
                ],
            }
        ],
    )
    document = build(tmp_path, layout_path, current_plugin())
    assert document.tabs == ()
    assert len(diagnostic_subjects(document, DiagnosticKind.COMPONENT_MISSING)) == 2


def test_partial_collapse_keeps_the_surviving_children(tmp_path: Path) -> None:
    layout_path = write_layout(
        tmp_path,
        on_missing="notice",
        tabs=[
            {
                "title": "QC",
                "components": [
                    {
                        "type": "card",
                        "title": "Group",
                        "children": [
                            {"id": "nope.nothing"},
                            {
                                "id": "current.quality",
                                "parameters": {"label": "A"},
                            },
                        ],
                    }
                ],
            }
        ],
    )
    document = build(tmp_path, layout_path, current_plugin())
    (node,) = document.tabs[0].nodes
    assert isinstance(node, CardEntry)
    assert node.title == "Group"
    assert len(node.children) == 1


def test_diagnostics_marker_placed_in_the_tree(tmp_path: Path) -> None:
    layout_path = write_layout(
        tmp_path,
        tabs=[
            {
                "title": "QC",
                "components": [
                    {"type": "diagnostics"},
                    {"id": "current.quality", "parameters": {"label": "A"}},
                ],
            }
        ],
    )
    document = build(tmp_path, layout_path, current_plugin())
    (tab,) = document.tabs
    marker, rendered = tab.nodes
    assert isinstance(marker, DiagnosticsEntry)
    assert isinstance(rendered, ComponentEntry)


def test_the_marker_and_the_ledger_stay_independent(tmp_path: Path) -> None:
    # No marker in the layout: the panel renders nowhere — and the
    # ledger still records everything, because omission is the
    # feature and recording is unconditional.
    layout_path = write_layout(tmp_path, tabs=[qc_tab("run A")])
    document = build(tmp_path, layout_path, current_plugin())
    assert not any(
        isinstance(node, DiagnosticsEntry) for node in document.tabs[0].nodes
    )
    assert [d.kind for d in document.diagnostics] == [
        DiagnosticKind.DEFAULT_THEME,
        DiagnosticKind.LOGO_OMITTED,
        DiagnosticKind.FAVICON_OMITTED,
    ]
