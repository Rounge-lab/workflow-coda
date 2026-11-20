"""Executable URL codec and selection-policy tests.

Node.js is a test-time runtime only, never a report dependency.
A skipped suite means JavaScript behavior has not been verified.
DOM/controller interaction still needs a browser check.
"""

import importlib.resources
import json
import shutil
import subprocess
from typing import Any

import pytest


def _execute(body: str) -> Any:
    node = shutil.which("node")
    if node is None:
        pytest.skip("install Node.js to execute selection JavaScript behavior tests")
    root = importlib.resources.files("workflow_coda") / "templates"
    source = "var window = {};\n"
    for name in ("selection_url.js", "selection_policy.js"):
        source += (root / name).read_text(encoding="utf-8") + "\n"
    source += body
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
    return json.loads(completed.stdout)


def _node(
    dimension: str,
    values: list[str],
    *,
    kind: str = "categorical",
    ancestors: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "dimension": dimension,
        "kind": kind,
        "values": values,
        "ancestors": ancestors or [],
    }


def _evaluate(nodes: list[dict[str, object]], fragment: str = "") -> Any:
    return _execute(
        "console.log(JSON.stringify(window.codaSelectionPolicy.evaluate("
        + json.dumps(nodes)
        + ", window.codaSelectionURL.parse("
        + json.dumps(fragment)
        + "))));"
    )


@pytest.mark.parametrize(
    "raw",
    [" Run A ", "run-a", "a+b", "a&b=c", "λ/雪", "__proto__", "100%"],
)
def test_codec_round_trips_raw_values_and_tab(raw: str) -> None:
    result = _execute(
        "var raw = "
        + json.dumps(raw)
        + "; var hash = window.codaSelectionURL.format('2-results', {batch: raw});"
        "console.log(JSON.stringify({hash: hash, "
        "parsed: window.codaSelectionURL.parse(hash)}));"
    )
    assert result["parsed"]["tab"] == "2-results"
    assert result["parsed"]["states"] == {"batch": raw}
    assert result["parsed"]["issues"] == []
    assert result["hash"].startswith("#tab=2-results&state.batch=")


def test_codec_accepts_legacy_tab_anchor() -> None:
    result = _execute(
        "console.log(JSON.stringify(window.codaSelectionURL.parse('#2-results')));"
    )
    assert result["legacy"] is True
    assert result["tab"] == "2-results"


@pytest.mark.parametrize(
    "fragment",
    [
        "#state.batch=%ZZ",
        "#state.batch=",
        "#state.batch=A&state.batch=B",
    ],
)
def test_bad_state_directives_stack_only_the_affected_dimension(fragment: str) -> None:
    result = _evaluate(
        [_node("batch", ["A", "B"]), _node("sample", ["s1", "s2"])],
        fragment,
    )
    assert result["selections"] == {"batch": None, "sample": "s1"}
    assert result["issues"]


def test_malformed_fragment_stacks_all_dimensions() -> None:
    result = _evaluate(
        [_node("batch", ["A", "B"])],
        "#unknown=value",
    )
    assert result["selections"]["batch"] is None
    assert "Unknown fragment directive" in result["issues"][0]


def test_shared_axis_union_preserves_first_appearance() -> None:
    result = _evaluate(
        [_node("batch", ["B", "A"]), _node("batch", ["A", "C"])],
        "#state.batch=C",
    )
    assert result["axes"]["batch"] == ["B", "A", "C"]
    assert result["selections"]["batch"] == "C"
    assert result["active"] == [True, True]
    assert result["issues"] == []


def test_unavailable_explicit_selection_stacks_dimension_and_teaches() -> None:
    result = _evaluate(
        [_node("batch", ["A", "B"])],
        "#state.batch=missing",
    )
    assert result["selections"]["batch"] is None
    assert '"missing"' in result["issues"][0]
    assert "remove its directive" in result["issues"][0]


def test_nested_choices_follow_outer_context_without_replacing_explicit_value() -> None:
    nodes = [
        _node("batch", ["A", "B"]),
        _node(
            "sample",
            ["a2", "a1"],
            ancestors=[{"dimension": "batch", "value": "A"}],
        ),
        _node(
            "sample",
            ["b2", "b1"],
            ancestors=[{"dimension": "batch", "value": "B"}],
        ),
    ]
    default = _evaluate(nodes, "#state.batch=B")
    assert default["selections"] == {"batch": "B", "sample": "b2"}
    assert default["axes"]["sample"] == ["b2", "b1"]
    assert default["active"] == [True, False, True]
    explicit = _evaluate(nodes, "#state.batch=B&state.sample=a1")
    assert explicit["selections"] == {"batch": "B", "sample": None}
    assert '"a1"' in explicit["issues"][0]


@pytest.mark.parametrize(
    "nodes",
    [
        [
            _node("batch", ["A", "B"]),
            _node("batch", ["A", "B"], kind="ordered"),
        ],
        [
            _node("batch", ["A", "B"], kind="ordered"),
            _node("batch", ["B", "A"], kind="ordered"),
        ],
    ],
)
def test_conflicting_shared_axes_disable_selection(
    nodes: list[dict[str, object]],
) -> None:
    result = _evaluate(nodes)
    assert result["disabled"]["batch"] is True
    assert result["selections"]["batch"] is None
    assert "correct the shared states declarations" in result["issues"][0]


def test_compatible_ordered_axes_merge_without_reversing_declared_order() -> None:
    result = _evaluate(
        [
            _node("batch", ["A", "C"], kind="ordered"),
            _node("batch", ["A", "B", "C"], kind="ordered"),
        ]
    )
    assert result["axes"]["batch"] == ["A", "B", "C"]
    assert result["selections"]["batch"] == "A"


def test_cyclic_nested_dimensions_stack_instead_of_guessing_defaults() -> None:
    result = _evaluate(
        [
            _node(
                "batch",
                ["A", "B"],
                ancestors=[{"dimension": "sample", "value": "s1"}],
            ),
            _node(
                "sample",
                ["s1", "s2"],
                ancestors=[{"dimension": "batch", "value": "A"}],
            ),
        ]
    )
    assert result["selections"] == {"batch": None, "sample": None}
    assert len(result["issues"]) == 2
    assert all("cyclic dependencies" in issue for issue in result["issues"])
