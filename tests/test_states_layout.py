"""States layout grammar and load-time placeholder boundaries.

The producer's model and loader contracts only: expansion, collapse,
and rendering belong to later test waves.
"""

import re
from pathlib import Path

import pytest
import yaml
from factories import make_layout_payload
from pydantic import ValidationError

from workflow_coda.artifact_store import JsonValue
from workflow_coda.errors import LayoutError
from workflow_coda.layout import (
    CardNode,
    ComponentPlacement,
    DiagnosticsNode,
    GridLayout,
    ReportLayout,
    RowNode,
    StatesNode,
)
from workflow_coda.layout_loader import load_layout

_COMPOSITION_FIX = (
    "placeholders substitute only inside a 'type: states' node; add "
    "one whose dimension it names, or remove the brace"
)
_UNBINDABLE_FIX = (
    "this string sits above the composition, so no states node can "
    "ever bind it; write the literal text"
)


def _placement(**overrides: JsonValue) -> dict[str, JsonValue]:
    """One valid placement, with injectable title and parameters."""
    node: dict[str, JsonValue] = {"id": "example.quality"}
    node.update(overrides)
    return node


def _states(**overrides: JsonValue) -> dict[str, JsonValue]:
    """A derived-axis states node with one template placement."""
    node: dict[str, JsonValue] = {
        "type": "states",
        "dimension": "batch",
        "children": [_placement()],
    }
    node.update(overrides)
    return node


def _payload(node: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return make_layout_payload(tabs=[{"title": "States", "components": [node]}])


def _model(node: dict[str, JsonValue]) -> StatesNode:
    layout = ReportLayout.model_validate(_payload(node))
    (states,) = layout.tabs[0].components
    assert isinstance(states, StatesNode)
    return states


def _write(tmp_path: Path, payload: dict[str, JsonValue]) -> Path:
    path = tmp_path / "states.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8", newline="\n")
    return path


def _load(tmp_path: Path, node: dict[str, JsonValue]) -> ReportLayout:
    return load_layout(_write(tmp_path, _payload(node)))


# ---------------------------------------------------------------------------
# Model: axis shape, declared policy, and honest labels
# ---------------------------------------------------------------------------


def test_states_defaults_to_a_derived_categorical_axis() -> None:
    states = _model(_states())
    assert states.dimension == "batch"
    assert states.kind == "categorical"
    assert states.values is None
    assert len(states.children) == 1
    assert isinstance(states.children[0], ComponentPlacement)


@pytest.mark.parametrize("dimension", ["batch", "sample_id", "batch-2", "a"])
def test_dimension_accepts_the_shared_placeholder_grammar(dimension: str) -> None:
    assert _model(_states(dimension=dimension)).dimension == dimension


@pytest.mark.parametrize(
    "dimension",
    ["Batch", "2batch", "-batch", "sample id", "{batch}", "batch.other", ""],
)
def test_bad_dimension_teaches_its_value_and_fix(dimension: str) -> None:
    teaching = (
        f"not a dimension name: {dimension!r} — a dimension is a "
        "placeholder name, lowercase snake_case like 'batch' or "
        "'sample_id'; its children's strings carry it in braces, "
        'e.g. title: "QC — {batch}"'
    )
    with pytest.raises(ValidationError, match=re.escape(teaching)):
        _model(_states(dimension=dimension))


@pytest.mark.parametrize("kind", ["categorical", "ordered"])
def test_kind_is_declared_and_preserved(kind: str) -> None:
    states = _model(_states(kind=kind, values=["3", "1", "2"]))
    assert states.kind == kind
    assert states.values == ("3", "1", "2")


def test_numeric_looking_labels_do_not_infer_ordered_kind() -> None:
    states = _model(_states(values=["1", "2", "3"]))
    assert states.kind == "categorical"


@pytest.mark.parametrize("kind", ["subset", "Ordered", "unknown"])
def test_unknown_kind_is_rejected(kind: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _model(_states(kind=kind))
    message = str(excinfo.value)
    assert "kind" in message
    assert "categorical" in message
    assert "ordered" in message


def test_axis_preserves_order_case_whitespace_and_distinct_spellings() -> None:
    states = _model(_states(values=[" Run A ", "run-a", "Run A", "B"]))
    assert states.values == (" Run A ", "run-a", "Run A", "B")


def test_declared_empty_axis_teaches_the_derived_door() -> None:
    teaching = (
        "a states node's 'values' must name at least one "
        "state — an empty axis renders nothing; omit "
        "'values' to derive the axis from the manifest"
    )
    with pytest.raises(ValidationError, match=re.escape(teaching)):
        _model(_states(values=[]))


def test_duplicate_axis_value_teaches_the_offender_and_removal() -> None:
    teaching = (
        "a states node's 'values' names 'B' twice "
        "— states are unique; remove the duplicate"
    )
    with pytest.raises(ValidationError, match=re.escape(teaching)):
        _model(_states(values=["A", "B", "B"]))


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_axis_values_require_visible_text(value: str) -> None:
    with pytest.raises(ValidationError, match="must contain visible text"):
        _model(_states(values=[value]))


@pytest.mark.parametrize("value", [1, True])
def test_axis_values_refuse_non_string_labels(value: JsonValue) -> None:
    with pytest.raises(ValidationError):
        _model(_states(values=[value]))


def test_states_requires_at_least_one_template_child() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        _model(_states(children=[]))


@pytest.mark.parametrize(
    ("key", "value"),
    [("title", "Selector"), ("split", [1, 1]), ("sanitize", True)],
)
def test_states_rejects_undeclared_keys(key: str, value: JsonValue) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _model(_states(**{key: value}))


def test_states_model_is_frozen() -> None:
    states = _model(_states(values=["A"]))
    with pytest.raises(ValidationError, match="frozen"):
        states.dimension = "sample"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Loader: real YAML, recursive composition, and load-time boundaries
# ---------------------------------------------------------------------------


def test_states_nests_through_existing_compositions_and_loads(tmp_path: Path) -> None:
    inner = _states(
        dimension="sample_id",
        values=["{batch}-s1", "{batch}-s2"],
        children=[
            _placement(
                title="QC {batch} {sample_id}",
                parameters={"{batch}": {"label": "{sample_id}"}},
            ),
            {"type": "diagnostics"},
        ],
    )
    outer = _states(
        values=["A", "B"],
        children=[
            {
                "type": "card",
                "title": "Batch {batch}",
                "children": [
                    {
                        "type": "grid",
                        "split": [1, 1],
                        "children": [{"type": "row", "children": [inner]}],
                    }
                ],
            }
        ],
    )
    layout = _load(
        tmp_path,
        {"type": "row", "children": [outer]},
    )
    (row,) = layout.tabs[0].components
    assert isinstance(row, RowNode)
    (states,) = row.children
    assert isinstance(states, StatesNode)
    assert states.values == ("A", "B")
    (card,) = states.children
    assert isinstance(card, CardNode)
    assert card.title == "Batch {batch}"
    (grid,) = card.children
    assert isinstance(grid, GridLayout)
    (nested_row,) = grid.children
    assert isinstance(nested_row, RowNode)
    (nested_states,) = nested_row.children
    assert isinstance(nested_states, StatesNode)
    assert nested_states.values == ("{batch}-s1", "{batch}-s2")
    placement, marker = nested_states.children
    assert isinstance(placement, ComponentPlacement)
    assert placement.title == "QC {batch} {sample_id}"
    assert placement.parameters == {"{batch}": {"label": "{sample_id}"}}
    assert isinstance(marker, DiagnosticsNode)


@pytest.mark.parametrize(
    "node",
    [
        _placement(title="QC {batch}"),
        _placement(parameters={"label": "{batch}"}),
        _placement(parameters={"{batch}": "value"}),
        _placement(parameters={"nested": [{"label": "{batch}"}]}),
        {"type": "card", "title": "QC {batch}", "children": [_placement()]},
        _placement(title="Malformed {"),
    ],
)
def test_orphan_composition_strings_teach_wrapping(
    tmp_path: Path, node: dict[str, JsonValue]
) -> None:
    path = _write(tmp_path, _payload(node))
    with pytest.raises(LayoutError, match=re.escape(_COMPOSITION_FIX)) as excinfo:
        load_layout(path)
    assert str(path) in str(excinfo.value)
    assert "{" in str(excinfo.value)


@pytest.mark.parametrize("field", ["title", "subtitle", "author", "version"])
def test_report_identity_teaches_literal_text_not_wrapping(
    tmp_path: Path, field: str
) -> None:
    payload = _payload(_states(values=["A"]))
    payload[field] = "Report {batch}"
    path = _write(tmp_path, payload)
    with pytest.raises(LayoutError, match=re.escape(_UNBINDABLE_FIX)) as excinfo:
        load_layout(path)
    message = str(excinfo.value)
    assert str(path) in message
    assert "Report {batch}" in message
    assert _COMPOSITION_FIX not in message


def test_tab_title_cannot_be_bound_by_its_states_child(tmp_path: Path) -> None:
    payload = make_layout_payload(
        tabs=[{"title": "Batch {batch}", "components": [_states(values=["A"])]}]
    )
    path = _write(tmp_path, payload)
    with pytest.raises(LayoutError, match=re.escape(_UNBINDABLE_FIX)) as excinfo:
        load_layout(path)
    assert str(path) in str(excinfo.value)
    assert "Batch {batch}" in str(excinfo.value)


@pytest.mark.parametrize("inside_states", [False, True])
def test_placement_id_refuses_placeholders_at_load(
    tmp_path: Path, inside_states: bool
) -> None:
    # The supplied model rejects this id before the loader's orphan
    # walk runs. Pin that actual boundary, not the unreachable helper.
    placement = _placement(id="example.{batch}")
    node = _states(values=["A"], children=[placement]) if inside_states else placement
    path = _write(tmp_path, _payload(node))
    with pytest.raises(LayoutError, match="not a component id") as excinfo:
        load_layout(path)
    message = str(excinfo.value)
    assert str(path) in message
    assert "example.{batch}" in message


def test_lone_closing_brace_is_literal_outside_states(tmp_path: Path) -> None:
    layout = _load(
        tmp_path,
        _placement(title="QC }", parameters={"label": "literal }"}),
    )
    (placement,) = layout.tabs[0].components
    assert isinstance(placement, ComponentPlacement)
    assert placement.title == "QC }"
    assert placement.parameters == {"label": "literal }"}


def test_scoped_malformed_placeholder_is_left_for_build_time(tmp_path: Path) -> None:
    layout = _load(
        tmp_path,
        _states(values=["A"], children=[_placement(title="Malformed {")]),
    )
    (states,) = layout.tabs[0].components
    assert isinstance(states, StatesNode)
    (placement,) = states.children
    assert isinstance(placement, ComponentPlacement)
    assert placement.title == "Malformed {"


def test_declared_empty_axis_fails_through_the_real_loader(tmp_path: Path) -> None:
    path = _write(tmp_path, _payload(_states(values=[])))
    with pytest.raises(LayoutError, match="omit 'values' to derive") as excinfo:
        load_layout(path)
    assert str(path) in str(excinfo.value)
