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
    PlacementInfo,
    RenderContext,
    RenderedComponent,
)
from workflow_coda.errors import ComponentUnavailableError, LayoutError
from workflow_coda.manifest import ReportManifest
from workflow_coda.plugins import ReportPlugin
from workflow_coda.registry import PluginRegistry
from workflow_coda.report import (
    CardEntry,
    ComponentEntry,
    Diagnostic,
    DiagnosticKind,
    DiagnosticsEntry,
    EntryKind,
    GridEntry,
    ReportDocument,
    RowEntry,
)
from workflow_coda.theme import DEFAULT_THEME

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
ICO_MAGIC = b"\x00\x00\x01\x00"


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
            "schema version '0.1.0' (it supports: 0.0.9)"
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
    assert "'0.1.0'" in excluded.message


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


# ---------------------------------------------------------------------------
# Declared assets, then strict
# ---------------------------------------------------------------------------


def test_declared_logo_embeds_as_a_data_uri(tmp_path: Path) -> None:
    data = PNG_MAGIC + b"fake-png-payload"
    write_asset(tmp_path, "logo.png", data)
    layout_path = write_layout(tmp_path, logo="logo.png", tabs=[qc_tab("run A")])
    document = build(tmp_path, layout_path, current_plugin())
    assert document.logo is not None
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
