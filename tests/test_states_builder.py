"""States document models and build-time expansion.

These tests exercise the expanded tree, not read-time selection.
Markdown's separate variable language is covered by test_markdown_states.
"""

import re
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from factories import (
    make_artifact_payload,
    make_component,
    make_layout_payload,
    make_manifest_payload,
    make_plugin,
    write_manifest_file,
)
from helpers import assert_frozen_dataclass

from workflow_coda.artifact_store import ArtifactStore, JsonValue
from workflow_coda.builder import build_report
from workflow_coda.components import (
    ComponentParameters,
    ComponentRenderer,
    ComponentStatus,
    PlacementInfo,
    RenderedComponent,
)
from workflow_coda.context import RenderContext
from workflow_coda.errors import ComponentUnavailableError, LayoutError, SpecError
from workflow_coda.registry import PluginRegistry
from workflow_coda.report import (
    CardEntry,
    ComponentEntry,
    DiagnosticKind,
    DiagnosticsEntry,
    DocumentNode,
    DocumentTab,
    EntryKind,
    ReportDocument,
    RowEntry,
    StatePanel,
    StatesEntry,
)


def _entry() -> ComponentEntry:
    """A healthy, hashable document leaf."""
    return ComponentEntry(
        kind=EntryKind.RENDERED,
        component_id="example.quality",
        title="Quality",
        outcome=RenderedComponent.from_html("<p>ok</p>"),
    )


def _panel(value: str = "A") -> StatePanel:
    return StatePanel(value=value, children=(_entry(),))


def _placement(**overrides: JsonValue) -> dict[str, JsonValue]:
    node: dict[str, JsonValue] = {"id": "example.quality"}
    node.update(overrides)
    return node


def _states(**overrides: JsonValue) -> dict[str, JsonValue]:
    node: dict[str, JsonValue] = {
        "type": "states",
        "dimension": "batch",
        "children": [_placement()],
    }
    node.update(overrides)
    return node


def _ok_render(
    _context: RenderContext,
    _info: PlacementInfo,
    _parameters: ComponentParameters,
) -> RenderedComponent:
    return RenderedComponent.from_html("<p>ok</p>")


def _selective_render(
    _context: RenderContext,
    _info: PlacementInfo,
    parameters: ComponentParameters,
) -> RenderedComponent:
    """Keep one value healthy and exercise degradation for another."""
    if parameters["label"] == "drop":
        mode = parameters.get("mode", "unavailable")
        if mode == "bug":
            raise ValueError("broken state")
        if mode == "skipped":
            return RenderedComponent.skipped()
        return RenderedComponent.unavailable("data absent for drop")
    return RenderedComponent.from_html("<p>kept</p>")


def _build(
    tmp_path: Path,
    node: dict[str, JsonValue],
    *,
    artifact_types: tuple[str, ...] = (),
    render: ComponentRenderer = _ok_render,
    css: str | None = None,
    js: str | None = None,
    **policies: JsonValue,
) -> ReportDocument:
    """Build through real files and loaders with a fixed plugin.

    Artifact files are deliberately absent: these renderers consume no
    artifacts, and axis derivation reads declarations, not availability.
    """
    artifacts = [
        make_artifact_payload(
            id=f"artifact-{index}",
            type=artifact_type,
            path=f"artifact-{index}.txt",
        )
        for index, artifact_type in enumerate(artifact_types)
    ]
    manifest_path = write_manifest_file(
        tmp_path, make_manifest_payload(artifacts=artifacts)
    )
    store = ArtifactStore.from_manifest_file(manifest_path)
    payload = make_layout_payload(
        tabs=[{"title": "States", "components": [node]}],
        **policies,
    )
    layout_path = tmp_path / "states.yaml"
    layout_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )
    component = make_component(render=render, css=css, js=js)
    registry = PluginRegistry((make_plugin(components=(component,)),))
    return build_report(layout_path, store, registry)


def _only_states(document: ReportDocument) -> StatesEntry:
    (tab,) = document.tabs
    (node,) = tab.nodes
    assert isinstance(node, StatesEntry)
    return node


def _only_component(panel: StatePanel) -> ComponentEntry:
    (node,) = panel.children
    assert isinstance(node, ComponentEntry)
    return node


# ---------------------------------------------------------------------------
# Document values: guards and immutable expanded content
# ---------------------------------------------------------------------------


def test_state_panel_preserves_label_and_child_order() -> None:
    first = _entry()
    second = replace(first, title="Second")
    panel = StatePanel(value=" Run A ", children=(second, first))
    assert panel.value == " Run A "
    assert panel.children == (second, first)


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_state_panel_requires_visible_value(value: str) -> None:
    with pytest.raises(
        ValueError,
        match=re.escape("a state panel's value must contain visible text"),
    ):
        StatePanel(value=value, children=(_entry(),))


def test_state_panel_requires_surviving_children() -> None:
    with pytest.raises(
        ValueError, match=re.escape("a state panel takes at least one child")
    ):
        StatePanel(value="A", children=())


def test_states_entry_preserves_kind_and_panel_order() -> None:
    entry = StatesEntry(
        dimension="batch", kind="ordered", panels=(_panel("B"), _panel("A"))
    )
    assert entry.dimension == "batch"
    assert entry.kind == "ordered"
    assert [panel.value for panel in entry.panels] == ["B", "A"]


def test_states_entry_requires_surviving_panels() -> None:
    with pytest.raises(
        ValueError, match=re.escape("a states entry takes at least one panel")
    ):
        StatesEntry(dimension="batch", kind="categorical", panels=())


def test_states_values_compare_hash_and_remain_frozen_and_slotted() -> None:
    panel = _panel()
    entry = StatesEntry(dimension="batch", kind="categorical", panels=(panel,))
    same = StatesEntry(dimension="batch", kind="categorical", panels=(_panel(),))
    assert panel == _panel()
    assert hash(panel) == hash(_panel())
    assert entry == same
    assert hash(entry) == hash(same)
    assert entry != replace(entry, kind="ordered")
    assert entry != replace(entry, panels=(_panel("B"),))
    assert_frozen_dataclass(panel, "value")
    assert_frozen_dataclass(entry, "dimension")
    with pytest.raises(AttributeError):
        panel.extra = "nope"  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        entry.extra = "nope"  # type: ignore[attr-defined]


def test_states_can_nest_as_document_nodes() -> None:
    inner = StatesEntry(dimension="sample", kind="ordered", panels=(_panel("s1"),))
    outer = StatesEntry(
        dimension="batch",
        kind="categorical",
        panels=(StatePanel(value="A", children=(inner, DiagnosticsEntry())),),
    )
    node: DocumentNode = outer
    tab = DocumentTab(title="States", nodes=(node,))
    assert tab.nodes == (outer,)
    assert outer.panels[0].children == (inner, DiagnosticsEntry())


def test_states_empty_wire_value_is_informational() -> None:
    assert DiagnosticKind.STATES_EMPTY.value == "states_empty"
    assert DiagnosticKind("states_empty") is DiagnosticKind.STATES_EMPTY
    assert DiagnosticKind.STATES_EMPTY.is_problem is False


# ---------------------------------------------------------------------------
# Builder: axis policy and recursive, verbatim substitution
# ---------------------------------------------------------------------------


def test_declared_axis_order_and_kind_override_manifest_derivation(
    tmp_path: Path,
) -> None:
    document = _build(
        tmp_path,
        _states(values=["B", "A"], kind="ordered"),
        artifact_types=("org.example.unrelated",),
    )
    entry = _only_states(document)
    assert entry.dimension == "batch"
    assert entry.kind == "ordered"
    assert [panel.value for panel in entry.panels] == ["B", "A"]
    assert all(
        _only_component(panel).kind is EntryKind.RENDERED for panel in entry.panels
    )


def test_derived_axis_follows_manifest_declaration_order_without_reading_files(
    tmp_path: Path,
) -> None:
    # Manifest types are unique by validation. Do not bypass that law
    # to construct duplicate declarations solely for a dedup fixture.
    types = ("org.example.zeta", "org.example.alpha", "org.example.middle")
    document = _build(tmp_path, _states(), artifact_types=types)
    assert [panel.value for panel in _only_states(document).panels] == list(types)
    assert not any(tmp_path.glob("artifact-*.txt"))


def test_empty_derived_axis_collapses_upward_with_an_informational_note(
    tmp_path: Path,
) -> None:
    document = _build(
        tmp_path,
        {
            "type": "row",
            "children": [
                {
                    "type": "card",
                    "children": [
                        {"type": "grid", "split": [1, 1], "children": [_states()]}
                    ],
                }
            ],
        },
    )
    assert document.tabs == ()
    assert [note.kind for note in document.diagnostics] == [
        DiagnosticKind.DEFAULT_THEME,
        DiagnosticKind.LOGO_OMITTED,
        DiagnosticKind.FAVICON_OMITTED,
        DiagnosticKind.STATES_EMPTY,
    ]
    note = document.diagnostics[-1]
    assert note.subject == "batch"
    assert note.kind.is_problem is False
    assert note.message == (
        "states node omitted: its dimension 'batch' derives an empty axis — the "
        "manifest declares no artifacts to derive one from; declare artifacts "
        "in the manifest, or name the axis with 'values:' on the states node"
    )


def test_expansion_preserves_raws_and_substitutes_every_parameter_string_leaf(
    tmp_path: Path,
) -> None:
    seen: list[tuple[str, dict[str, JsonValue]]] = []

    def record(
        _context: RenderContext,
        info: PlacementInfo,
        parameters: ComponentParameters,
    ) -> RenderedComponent:
        seen.append((info.title, deepcopy(dict(parameters))))
        return RenderedComponent.from_html("<p>ok</p>")

    document = _build(
        tmp_path,
        _states(
            values=[" Run A ", "run-a"],
            children=[
                {
                    "type": "card",
                    "title": "Group {batch}",
                    "children": [
                        _placement(
                            title="QC {batch}",
                            parameters={
                                "{batch}": {
                                    "nested-{batch}": [
                                        "{batch}",
                                        {"label": "Value {batch}"},
                                        12,
                                        1.5,
                                        True,
                                        None,
                                    ]
                                }
                            },
                        )
                    ],
                }
            ],
        ),
        render=record,
    )
    entry = _only_states(document)
    assert [panel.value for panel in entry.panels] == [" Run A ", "run-a"]
    for panel, (title, parameters) in zip(entry.panels, seen, strict=True):
        raw = panel.value
        assert title == f"QC {raw}"
        assert parameters == {
            raw: {
                f"nested-{raw}": [
                    raw,
                    {"label": f"Value {raw}"},
                    12,
                    1.5,
                    True,
                    None,
                ]
            }
        }
        (card,) = panel.children
        assert isinstance(card, CardEntry)
        assert card.title == f"Group {raw}"
        (component,) = card.children
        assert isinstance(component, ComponentEntry)
        assert component.title == title
        assert component.component_id == "example.quality"


def test_nested_values_take_outer_substitution_before_inner_expansion(
    tmp_path: Path,
) -> None:
    document = _build(
        tmp_path,
        _states(
            values=["B", "A"],
            children=[
                {
                    "type": "row",
                    "children": [
                        _states(
                            dimension="sample",
                            kind="ordered",
                            values=["{batch}-s2", "{batch}-s1"],
                            children=[_placement(title="QC {batch} / {sample}")],
                        )
                    ],
                }
            ],
        ),
    )
    outer = _only_states(document)
    for panel in outer.panels:
        (row,) = panel.children
        assert isinstance(row, RowEntry)
        (inner,) = row.children
        assert isinstance(inner, StatesEntry)
        assert inner.dimension == "sample"
        assert inner.kind == "ordered"
        assert [child.value for child in inner.panels] == [
            f"{panel.value}-s2",
            f"{panel.value}-s1",
        ]
        for sample in inner.panels:
            assert _only_component(sample).title == (
                f"QC {panel.value} / {sample.value}"
            )


def test_outer_round_wins_when_inner_dimension_shadows_it(tmp_path: Path) -> None:
    document = _build(
        tmp_path,
        _states(
            values=["outer"],
            children=[
                _states(
                    values=["inner-2", "inner-1"],
                    children=[_placement(title="QC {batch}")],
                )
            ],
        ),
    )
    (panel,) = _only_states(document).panels
    (inner,) = panel.children
    assert isinstance(inner, StatesEntry)
    assert [child.value for child in inner.panels] == ["inner-2", "inner-1"]
    assert [_only_component(child).title for child in inner.panels] == [
        "QC outer",
        "QC outer",
    ]


@pytest.mark.parametrize("title", ["QC {other}", "Malformed {"])
def test_expansion_errors_name_layout_and_chain_spec_error(
    tmp_path: Path, title: str
) -> None:
    with pytest.raises(LayoutError) as excinfo:
        _build(
            tmp_path,
            _states(values=["A"], children=[_placement(title=title)]),
        )
    error = excinfo.value
    path = tmp_path / "states.yaml"
    assert str(error).startswith(f"{path}:")
    assert str(error).count(str(path)) == 1
    assert repr(title) in str(error)
    assert isinstance(error.__cause__, SpecError)
    assert str(error) == str(error.__cause__)


# ---------------------------------------------------------------------------
# Collapse, degradation, policy, and page-chrome collection
# ---------------------------------------------------------------------------


def _selective_states(mode: str = "unavailable") -> dict[str, JsonValue]:
    return _states(
        values=["drop", "keep"],
        children=[_placement(parameters={"label": "{batch}", "mode": mode})],
    )


def test_unavailable_skip_drops_only_the_empty_panel(tmp_path: Path) -> None:
    document = _build(
        tmp_path,
        _selective_states(),
        render=_selective_render,
        on_unavailable="skip",
    )
    assert [panel.value for panel in _only_states(document).panels] == ["keep"]
    notes = [
        note
        for note in document.diagnostics
        if note.kind is DiagnosticKind.COMPONENT_UNAVAILABLE
    ]
    assert len(notes) == 1
    assert notes[0].is_problem if False else not notes[0].kind.is_problem
    assert "data absent for drop" in notes[0].message
    assert not any(
        note.kind is DiagnosticKind.STATES_EMPTY for note in document.diagnostics
    )


def test_unavailable_notice_keeps_both_panels(tmp_path: Path) -> None:
    document = _build(tmp_path, _selective_states(), render=_selective_render)
    entry = _only_states(document)
    assert [panel.value for panel in entry.panels] == ["drop", "keep"]
    statuses = []
    for panel in entry.panels:
        outcome = _only_component(panel).outcome
        assert outcome is not None
        statuses.append(outcome.status)
    assert statuses == [ComponentStatus.UNAVAILABLE, ComponentStatus.OK]


def test_unavailable_fail_still_refuses_states_build(tmp_path: Path) -> None:
    with pytest.raises(ComponentUnavailableError, match="data absent for drop"):
        _build(
            tmp_path,
            _selective_states(),
            render=_selective_render,
            on_unavailable="fail",
        )


def test_all_unavailable_panels_collapse_states_and_parent_grid(
    tmp_path: Path,
) -> None:
    node = _selective_states()
    node["values"] = ["drop"]
    document = _build(
        tmp_path,
        {"type": "grid", "split": [1, 1], "children": [node]},
        render=_selective_render,
        on_unavailable="skip",
    )
    assert document.tabs == ()
    assert (
        sum(
            note.kind is DiagnosticKind.COMPONENT_UNAVAILABLE
            for note in document.diagnostics
        )
        == 1
    )
    assert not any(
        note.kind is DiagnosticKind.STATES_EMPTY for note in document.diagnostics
    )


def test_missing_components_collapse_each_panel_under_notice(tmp_path: Path) -> None:
    document = _build(
        tmp_path,
        _states(
            values=["B", "A"],
            children=[{"id": "missing.quality"}],
        ),
        on_missing="notice",
    )
    assert document.tabs == ()
    missing = [
        note
        for note in document.diagnostics
        if note.kind is DiagnosticKind.COMPONENT_MISSING
    ]
    assert [note.subject for note in missing] == [
        "missing.quality",
        "missing.quality",
    ]


@pytest.mark.parametrize(
    ("mode", "kind", "status"),
    [
        ("bug", EntryKind.FAILED, None),
        ("skipped", EntryKind.RENDERED, ComponentStatus.SKIPPED),
    ],
)
def test_plugin_bugs_and_deliberate_skips_do_not_collapse_panels(
    tmp_path: Path,
    mode: str,
    kind: EntryKind,
    status: ComponentStatus | None,
) -> None:
    # Deliberate SKIPPED outcomes stay as document entries, matching
    # the existing builder contract; only rendering suppresses them.
    document = _build(
        tmp_path,
        _selective_states(mode),
        render=_selective_render,
        on_unavailable="skip",
    )
    entry = _only_states(document)
    assert [panel.value for panel in entry.panels] == ["drop", "keep"]
    degraded = _only_component(entry.panels[0])
    assert degraded.kind is kind
    if status is None:
        assert degraded.error == "ValueError: broken state"
        assert any(
            note.kind is DiagnosticKind.PLUGIN_BUG for note in document.diagnostics
        )
    else:
        assert degraded.outcome is not None
        assert degraded.outcome.status is status


def test_chrome_collects_once_after_a_degraded_state_then_a_healthy_state(
    tmp_path: Path,
) -> None:
    css = ".coda-example-quality { color: inherit; }"
    js = "console.log('example.quality enhanced');"
    document = _build(
        tmp_path,
        _selective_states("bug"),
        render=_selective_render,
        css=css,
        js=js,
    )
    assert len(document.chrome) == 1
    contribution = document.chrome[0]
    assert contribution.component_id == "example.quality"
    assert contribution.css == css
    assert contribution.js == js


def test_degraded_only_states_contribute_no_plugin_chrome(tmp_path: Path) -> None:
    node = _selective_states("bug")
    node["values"] = ["drop"]
    document = _build(
        tmp_path,
        node,
        render=_selective_render,
        css=".coda-example-quality { color: inherit; }",
    )
    assert len(_only_states(document).panels) == 1
    assert document.chrome == ()
