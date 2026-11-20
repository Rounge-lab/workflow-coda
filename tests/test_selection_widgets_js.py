"""Executable selector-planning tests.

Selection is global; control visibility is tab- and context-local.
The widget planner is unregistered during this bounded step.

Node.js is a test-time runtime, not a report dependency. Skipped
tests do not establish JavaScript correctness. DOM controls and
focus behavior belong to the subsequent controller integration.
"""

import importlib.resources
import json
import shutil
import subprocess
from typing import Any

import pytest


def _record(
    dimension: str,
    values: list[str],
    tab_id: str,
    *,
    kind: str = "categorical",
    ancestors: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "dimension": dimension,
        "kind": kind,
        "values": values,
        "ancestors": ancestors or [],
        "tabId": tab_id,
    }


def _plan(
    records: list[dict[str, object]],
    tab_id: str | None,
    fragment: str = "",
) -> Any:
    """Execute the real policy and planner without a fabricated result."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("install Node.js to execute selector-planning tests")

    root = importlib.resources.files("workflow_coda") / "templates"
    source = "var window = {};\n"
    for name in (
        "selection_url.js",
        "selection_policy.js",
        "selection_widgets.js",
    ):
        source += (root / name).read_text(encoding="utf-8") + "\n"

    source += (
        "var records = "
        + json.dumps(records)
        + ";\nvar directive = window.codaSelectionURL.parse("
        + json.dumps(fragment)
        + ");\nvar result = window.codaSelectionPolicy.evaluate(records, directive);\n"
        "var before = JSON.stringify({records: records, result: result});\n"
        "var controls = window.codaSelectionWidgets.plan(records, result, "
        + json.dumps(tab_id)
        + ");\nvar after = JSON.stringify({records: records, result: result});\n"
        "console.log(JSON.stringify({controls: controls, unchanged: before === after}));\n"
    )
    completed = subprocess.run(
        [node, "-"],
        input=source,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    output = json.loads(completed.stdout)
    assert output["unchanged"] is True
    return output["controls"]


def test_only_dimensions_relevant_to_the_active_tab_have_controls() -> None:
    records = [
        _record("batch", ["A", "B"], "1-results"),
        _record("sample", ["s1", "s2"], "2-samples"),
    ]
    controls = _plan(records, "1-results")
    assert controls == [
        {
            "dimension": "batch",
            "kind": "categorical",
            "values": ["A", "B"],
            "selected": "A",
        }
    ]
    assert _plan(records, "3-methods") == []


def test_tab_changes_preserve_the_shared_selection_and_global_choices() -> None:
    records = [
        _record("batch", ["A", "B"], "1-results"),
        _record("batch", ["B", "C"], "2-results"),
    ]
    first = _plan(records, "1-results", "#state.batch=C")
    second = _plan(records, "2-results", "#state.batch=C")
    assert first == second
    assert first[0]["values"] == ["A", "B", "C"]
    assert first[0]["selected"] == "C"


def test_locally_singleton_node_retains_access_to_a_shared_selector() -> None:
    records = [
        _record("batch", ["A"], "1-results"),
        _record("batch", ["A", "B"], "2-results"),
    ]
    controls = _plan(records, "1-results", "#state.batch=B")
    assert len(controls) == 1
    assert controls[0]["values"] == ["A", "B"]
    assert controls[0]["selected"] == "B"


def test_genuinely_singleton_axis_has_no_selector() -> None:
    records = [
        _record("batch", ["A"], "1-results"),
        _record("batch", ["A"], "2-results"),
    ]
    assert _plan(records, "1-results") == []


def test_repeated_nodes_share_one_control_per_dimension() -> None:
    records = [
        _record("batch", ["B", "A"], "1-results"),
        _record("batch", ["A", "C"], "1-results"),
        _record("sample", ["s2", "s1"], "1-results"),
    ]
    controls = _plan(records, "1-results")
    assert [control["dimension"] for control in controls] == ["batch", "sample"]
    assert controls[0]["values"] == ["B", "A", "C"]


def test_nested_selector_visibility_follows_outer_context() -> None:
    records = [
        _record("batch", ["A", "B"], "1-results"),
        _record(
            "sample",
            ["s1", "s2"],
            "1-results",
            ancestors=[{"dimension": "batch", "value": "A"}],
        ),
    ]
    first = _plan(records, "1-results", "#state.batch=A")
    assert [control["dimension"] for control in first] == ["batch", "sample"]

    second = _plan(records, "1-results", "#state.batch=B")
    assert [control["dimension"] for control in second] == ["batch"]
    # The parent selector remains available: selecting A restores
    # the context containing the sample panels.


def test_nested_choices_preserve_unavailable_explicit_selection_as_null() -> None:
    records = [
        _record("batch", ["A", "B"], "1-results"),
        _record(
            "sample",
            ["a1", "a2"],
            "1-results",
            ancestors=[{"dimension": "batch", "value": "A"}],
        ),
        _record(
            "sample",
            ["b1", "b2"],
            "1-results",
            ancestors=[{"dimension": "batch", "value": "B"}],
        ),
    ]
    controls = _plan(
        records,
        "1-results",
        "#state.batch=B&state.sample=a1",
    )
    assert controls[1] == {
        "dimension": "sample",
        "kind": "categorical",
        "values": ["b1", "b2"],
        "selected": None,
    }


def test_disabled_shared_dimension_has_no_selection_control() -> None:
    records = [
        _record("batch", ["A", "B"], "1-results"),
        _record("batch", ["A", "B"], "2-results", kind="ordered"),
        _record("sample", ["s1", "s2"], "1-results"),
    ]
    controls = _plan(records, "1-results")
    assert [control["dimension"] for control in controls] == ["sample"]


def test_ordered_selector_uses_the_resolved_global_axis() -> None:
    records = [
        _record("step", ["A", "C"], "1-results", kind="ordered"),
        _record("step", ["A", "B", "C"], "2-results", kind="ordered"),
    ]
    controls = _plan(records, "1-results", "#state.step=B")
    assert controls == [
        {
            "dimension": "step",
            "kind": "ordered",
            "values": ["A", "B", "C"],
            "selected": "B",
        }
    ]


def test_stacked_tabs_offer_controls_relevant_to_any_displayed_tab() -> None:
    records = [
        _record("batch", ["A", "B"], "1-results"),
        _record("sample", ["s1", "s2"], "2-results"),
    ]
    controls = _plan(records, None)
    assert [control["dimension"] for control in controls] == ["batch", "sample"]


def test_raw_labels_and_distinct_spellings_survive_planning() -> None:
    values = [" Run A ", "run-a", "λ/雪", "__proto__"]
    controls = _plan(
        [_record("batch", values, "1-results")],
        "1-results",
        "#state.batch=%20Run%20A%20",
    )
    assert controls[0]["values"] == values
    assert controls[0]["selected"] == " Run A "


def test_empty_report_has_no_controls() -> None:
    assert _plan([], None) == []
