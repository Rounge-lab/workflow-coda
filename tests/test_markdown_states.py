"""Compatibility between states placeholders and markdown variables.

Valid artifact-backed markdown variables are opaque only within
string-valued core.markdown.text. Everything else retains the strict
states opening-brace language.
"""

import json
import re
from pathlib import Path

import pytest
import yaml
from factories import (
    make_artifact_payload,
    make_layout_payload,
    make_manifest_payload,
)

from workflow_coda.artifact_store import ArtifactStore, JsonValue
from workflow_coda.builder import build_report
from workflow_coda.components import ComponentStatus
from workflow_coda.core.plugin import get_plugin
from workflow_coda.errors import LayoutError, SpecError
from workflow_coda.layout import ComponentPlacement, StatesNode
from workflow_coda.layout_loader import load_layout
from workflow_coda.manifest import ReportManifest
from workflow_coda.registry import PluginRegistry
from workflow_coda.report import (
    ComponentEntry,
    DiagnosticKind,
    EntryKind,
    ReportDocument,
    StatesEntry,
)

_COMPOSITION_FIX = (
    "placeholders substitute only inside a 'type: states' node; add "
    "one whose dimension it names, or remove the brace"
)
"""Transcribed from the loader's shipped composition teaching."""


def _write_layout(tmp_path: Path, node: dict[str, JsonValue]) -> Path:
    """Write one node in one tab through the serialized layout factory."""
    payload = make_layout_payload(
        tabs=[{"title": "Prose", "components": [node]}]
    )
    path = tmp_path / "report_layout.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def _markdown(text: JsonValue) -> dict[str, JsonValue]:
    """A markdown placement whose original text key owns the exemption."""
    return {"id": "core.markdown", "parameters": {"text": text}}


def _states(
    dimension: str,
    values: list[str],
    child: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    """One declared states axis containing one template child."""
    axis: list[JsonValue] = list(values)
    return {
        "type": "states",
        "dimension": dimension,
        "values": axis,
        "children": [child],
    }


def _core_registry() -> PluginRegistry:
    """Render through the real core roster, not a markdown stand-in."""
    return PluginRegistry((get_plugin(),))


def _store(
    tmp_path: Path, records: list[tuple[str, int | float]]
) -> ArtifactStore:
    """Declare and write real JSON artifacts in the supplied order."""
    artifacts: list[dict[str, object]] = []
    for index, (artifact_type, depth) in enumerate(records):
        filename = f"stats-{index}.json"
        (tmp_path / filename).write_text(
            json.dumps({"depth": depth}), encoding="utf-8"
        )
        artifacts.append(
            make_artifact_payload(
                id=f"stats-{index}",
                type=artifact_type,
                path=filename,
                format="json",
            )
        )
    manifest = ReportManifest.model_validate(
        make_manifest_payload(artifacts=artifacts)
    )
    return ArtifactStore(manifest, tmp_path)


def _build(
    tmp_path: Path,
    node: dict[str, JsonValue],
    records: list[tuple[str, int | float]],
) -> ReportDocument:
    """Build through the real loader, store, registry, and component."""
    path = _write_layout(tmp_path, node)
    return build_report(path, _store(tmp_path, records), _core_registry())


def _rendered_html(entry: ComponentEntry) -> str:
    """Require a healthy markdown render before inspecting its content."""
    assert entry.component_id == "core.markdown"
    assert entry.kind is EntryKind.RENDERED
    assert entry.error is None
    assert entry.outcome is not None
    assert entry.outcome.status is ComponentStatus.OK
    assert entry.outcome.html is not None
    return entry.outcome.html


def _assert_no_plugin_bugs(document: ReportDocument) -> None:
    assert not any(
        diagnostic.kind is DiagnosticKind.PLUGIN_BUG
        for diagnostic in document.diagnostics
    )


# ---------------------------------------------------------------------------
# Loader: only valid variables in a string-valued markdown text are opaque
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "{{depth}}",
        "{{ depth }}",
        "{{ Stats.mean-depth }}",
        "Depth {{depth}}, mean {{ Stats.mean-depth }}.",
        "A lone } rides unchanged.",
    ],
)
def test_loader_preserves_markdown_text(tmp_path: Path, text: str) -> None:
    layout = load_layout(_write_layout(tmp_path, _markdown(text)))
    (placement,) = layout.tabs[0].components
    assert isinstance(placement, ComponentPlacement)
    assert placement.parameters["text"] == text


@pytest.mark.parametrize(
    "text",
    [
        "Batch {batch}: {{ depth }}",
        "a {{ b",
    ],
)
def test_loader_rejects_unprotected_braces_outside_states(
    tmp_path: Path, text: str
) -> None:
    # Direct component rendering permits unclosed '{{', but layouts
    # retain their strict opening-brace rule.
    path = _write_layout(tmp_path, _markdown(text))
    with pytest.raises(LayoutError, match=re.escape(_COMPOSITION_FIX)) as excinfo:
        load_layout(path)
    message = str(excinfo.value)
    assert str(path) in message
    assert repr(text) in message


@pytest.mark.parametrize(
    ("placement", "where"),
    [
        (
            {"id": "example.prose", "parameters": {"text": "{{ depth }}"}},
            "parameter 'text'",
        ),
        (
            {
                "id": "core.markdown",
                "parameters": {"text": "Static", "artifact": "{{ depth }}"},
            },
            "parameter 'artifact'",
        ),
        (
            {
                "id": "core.markdown",
                "title": "{{ depth }}",
                "parameters": {"text": "Static"},
            },
            "'s title",
        ),
        (
            {
                "id": "core.markdown",
                "parameters": {"text": "Static", "{{ depth }}": "value"},
            },
            "parameter key '{{ depth }}'",
        ),
        (
            {"id": "core.markdown", "parameters": {"text": ["{{ depth }}"]}},
            "parameter 'text'[0]",
        ),
    ],
)
def test_loader_does_not_extend_the_markdown_exemption(
    tmp_path: Path, placement: dict[str, JsonValue], where: str
) -> None:
    path = _write_layout(tmp_path, placement)
    with pytest.raises(LayoutError, match=re.escape(_COMPOSITION_FIX)) as excinfo:
        load_layout(path)
    message = str(excinfo.value)
    assert str(path) in message
    assert where in message
    assert "{{ depth }}" in message


def test_loader_leaves_mixed_states_text_for_the_builder(tmp_path: Path) -> None:
    text = "Batch {batch}: {{ depth }}"
    path = _write_layout(tmp_path, _states("batch", ["A"], _markdown(text)))
    layout = load_layout(path)
    (states,) = layout.tabs[0].components
    assert isinstance(states, StatesNode)
    (placement,) = states.children
    assert isinstance(placement, ComponentPlacement)
    assert placement.parameters["text"] == text


# ---------------------------------------------------------------------------
# Builder: artifact-backed markdown survives every states expansion round
# ---------------------------------------------------------------------------


def test_static_markdown_variables_render_outside_states(tmp_path: Path) -> None:
    document = _build(
        tmp_path,
        {
            "id": "core.markdown",
            "parameters": {
                "artifact": "org.example.stats",
                "text": "Depth **{{ depth }}**",
            },
        },
        [("org.example.stats", 12.5)],
    )
    (entry,) = document.tabs[0].nodes
    assert isinstance(entry, ComponentEntry)
    assert "<strong>12.5</strong>" in _rendered_html(entry)
    _assert_no_plugin_bugs(document)


def test_mixed_states_and_markdown_variables_render(tmp_path: Path) -> None:
    document = _build(
        tmp_path,
        _states(
            "batch",
            ["A", "B"],
            {
                "id": "core.markdown",
                "parameters": {
                    "artifact": "org.example.stats-{batch}",
                    "text": "Batch {batch}: **{{ depth }}**",
                },
            },
        ),
        [
            ("org.example.stats-A", 12.5),
            ("org.example.stats-B", 20.5),
        ],
    )
    (states,) = document.tabs[0].nodes
    assert isinstance(states, StatesEntry)
    assert [panel.value for panel in states.panels] == ["A", "B"]
    for panel, depth in zip(states.panels, (12.5, 20.5), strict=True):
        (entry,) = panel.children
        assert isinstance(entry, ComponentEntry)
        html = _rendered_html(entry)
        assert f"Batch {panel.value}: <strong>{depth}</strong>" in html
        assert "{batch}" not in html
        assert "{{" not in html
    _assert_no_plugin_bugs(document)


def test_nested_states_preserve_markdown_variables_in_both_rounds(
    tmp_path: Path,
) -> None:
    document = _build(
        tmp_path,
        _states(
            "batch",
            ["A", "B"],
            _states(
                "sample",
                ["S1", "S2"],
                {
                    "id": "core.markdown",
                    "parameters": {
                        "artifact": "org.example.stats-{batch}-{sample}",
                        "text": (
                            "Batch {batch}, sample {sample}: **{{ depth }}**"
                        ),
                    },
                },
            ),
        ),
        [
            ("org.example.stats-A-S1", 1),
            ("org.example.stats-A-S2", 2),
            ("org.example.stats-B-S1", 3),
            ("org.example.stats-B-S2", 4),
        ],
    )
    (outer,) = document.tabs[0].nodes
    assert isinstance(outer, StatesEntry)
    assert [panel.value for panel in outer.panels] == ["A", "B"]
    depth = 0
    for batch in outer.panels:
        (inner,) = batch.children
        assert isinstance(inner, StatesEntry)
        assert [panel.value for panel in inner.panels] == ["S1", "S2"]
        for sample in inner.panels:
            depth += 1
            (entry,) = sample.children
            assert isinstance(entry, ComponentEntry)
            html = _rendered_html(entry)
            assert (
                f"Batch {batch.value}, sample {sample.value}: "
                f"<strong>{depth}</strong>"
            ) in html
            assert "{batch}" not in html
            assert "{sample}" not in html
            assert "{{" not in html
    assert depth == 4
    _assert_no_plugin_bugs(document)


@pytest.mark.parametrize(
    "placement",
    [
        {"id": "example.prose", "parameters": {"text": "{{ depth }}"}},
        {
            "id": "core.markdown",
            "title": "{{ depth }}",
            "parameters": {"text": "Static"},
        },
        _markdown("{{ depth }} {other}"),
        _markdown("a {{ b"),
        {
            "id": "core.markdown",
            "parameters": {"text": "Static", "{{ depth }}": "value"},
        },
        _markdown(["{{ depth }}"]),
        {
            "id": "core.markdown",
            "parameters": {"text": "Static", "artifact": "{{ depth }}"},
        },
    ],
)
def test_states_reject_unprotected_braces_before_component_rendering(
    tmp_path: Path,
    placement: dict[str, JsonValue],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_layout(tmp_path, _states("batch", ["A"], placement))

    def unexpected_render(*args: object, **kwargs: object) -> None:
        pytest.fail("a component rendered before invalid expansion was rejected")

    monkeypatch.setattr("workflow_coda.builder._render", unexpected_render)
    with pytest.raises(LayoutError) as excinfo:
        build_report(path, _store(tmp_path, []), _core_registry())
    assert str(path) in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, SpecError)


def test_expanded_parameter_key_does_not_gain_the_text_exemption(
    tmp_path: Path,
) -> None:
    # Eligibility belongs to the original key. Expanding '{batch}'
    # into 'text' must not turn arbitrary parameter data into markdown.
    placement: dict[str, JsonValue] = {
        "id": "core.markdown",
        "parameters": {"{batch}": "{{ depth }}"},
    }
    path = _write_layout(tmp_path, _states("batch", ["text"], placement))
    with pytest.raises(LayoutError) as excinfo:
        build_report(path, _store(tmp_path, []), _core_registry())
    assert str(path) in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, SpecError)
