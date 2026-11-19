"""Controller integration for tab/context-aware selection widgets.

The shipped JavaScript executes against a minimal DOM fixture.
These tests cover planning, controls, URL writes, and focus targets.
They do not simulate browser layout, native control behavior,
accessibility-tree interpretation, printing, or Plotly.
"""

import importlib.resources
import json
import re
import shutil
import subprocess
from typing import Any

import pytest
from factories import make_manifest_payload

from workflow_coda.components import RenderedComponent
from workflow_coda.manifest import ReportManifest
from workflow_coda.render import render_report
from workflow_coda.report import (
    ComponentEntry,
    DocumentTab,
    EntryKind,
    ReportDocument,
    StatePanel,
    StatesEntry,
)
from workflow_coda.theme import DEFAULT_THEME

_DOM = r"""
var window = {location: {hash: ""}};
var calls = [];
var writes = [];
var created = [];
var windowListeners = {};

function element(classes, attributes, parent, tag) {
  var names = classes ? classes.split(" ") : [];
  var attrs = attributes || {};
  var value = {
    id: attrs.id || "",
    tagName: tag || "div",
    children: [],
    parentElement: parent || null,
    listeners: {},
    textContent: "",
    className: classes || "",
    value: "",
    classList: {
      contains: function (name) { return names.indexOf(name) >= 0; },
      add: function (name) {
        if (names.indexOf(name) < 0) { names.push(name); }
      },
      toggle: function (name, enabled) {
        var index = names.indexOf(name);
        if (enabled && index < 0) { names.push(name); }
        if (!enabled && index >= 0) { names.splice(index, 1); }
      }
    },
    getAttribute: function (name) {
      return Object.prototype.hasOwnProperty.call(attrs, name)
        ? attrs[name] : null;
    },
    setAttribute: function (name, text) { attrs[name] = text; },
    appendChild: function (child) {
      child.parentElement = value;
      value.children.push(child);
    },
    replaceChildren: function () {
      value.children.forEach(function (child) { child.parentElement = null; });
      value.children = [];
    },
    insertBefore: function (child, before) {
      child.parentElement = value;
      value.children.splice(value.children.indexOf(before), 0, child);
    },
    addEventListener: function (name, handler) {
      value.listeners[name] = handler;
    },
    focus: function () { document.activeElement = value; },
    querySelectorAll: function () { return []; }
  };
  if (parent) { parent.children.push(value); }
  return value;
}

var main = element("");
var panels = [
  element("coda-tabpanel", {id: "1-results"}, main),
  element("coda-tabpanel", {id: "2-results"}, main),
  element("coda-tabpanel", {id: "3-methods"}, main)
];
var tabs = panels.map(function (panel) {
  return element("coda-tab", {"data-target": panel.id});
});
var wrappers = [];

function states(dimension, values, parent) {
  var wrapper = element("coda-states", {
    "data-states-dimension": dimension,
    "data-kind": "categorical"
  }, parent);
  wrappers.push(wrapper);
  values.forEach(function (raw) {
    element("coda-state", {
      "data-state-dimension": dimension,
      "data-state-value": raw
    }, wrapper);
  });
  return wrapper;
}

var batch = states("batch", ["A", "B"], panels[0]);
states("sample", ["s1", "s2"], batch.children[0]);
states("batch", ["A"], panels[1]);

var document = {
  activeElement: null,
  documentElement: element(""),
  querySelectorAll: function (selector) {
    if (selector === ".coda-tab") { return tabs; }
    if (selector === ".coda-tabpanel") { return panels; }
    if (selector === ".coda-states") { return wrappers; }
    throw new Error("Unexpected selector: " + selector);
  },
  createElement: function (tag) {
    created.push(tag);
    return element("", {}, null, tag);
  },
  addEventListener: function () {}
};
window.addEventListener = function (name, handler) {
  windowListeners[name] = handler;
};
window.history = {
  replaceState: function (state, title, fragment) {
    writes.push(fragment);
    window.location.hash = fragment;
  }
};

function controlsArea() {
  return main.children.filter(function (child) {
    return child.className === "coda-selection-controls";
  })[0];
}

function inputFor(dimension) {
  var found = null;
  controlsArea().children.forEach(function (container) {
    container.children.forEach(function (child) {
      if (child.getAttribute("data-selection-dimension") === dimension) {
        found = child;
      }
    });
  });
  return found;
}

function widgetSnapshot() {
  return controlsArea().children.map(function (container) {
    var input = container.children[1];
    var output = container.children[2];
    return {
      dimension: input.getAttribute("data-selection-dimension"),
      label: container.children[0].textContent,
      labelFor: container.children[0].getAttribute("for"),
      id: input.id,
      tag: input.tagName,
      type: input.type || null,
      value: input.value,
      min: input.min || null,
      max: input.max || null,
      step: input.step || null,
      valueText: input.getAttribute("aria-valuetext"),
      describedBy: input.getAttribute("aria-describedby"),
      outputId: output ? output.id : null,
      output: output ? output.textContent : null,
      options: input.children.map(function (option) {
        return {
          value: option.value,
          text: option.textContent,
          disabled: option.disabled || false
        };
      })
    };
  });
}
"""


def _execute(
    initial_hash: str,
    actions: str = "",
    *,
    setup: str = "",
) -> Any:
    node = shutil.which("node")
    if node is None:
        pytest.skip("install Node.js to execute controller-widget integration tests")

    root = importlib.resources.files("workflow_coda") / "templates"
    source = _DOM + "\n" + setup + "\n"
    source += "window.location.hash = " + json.dumps(initial_hash) + ";\n"
    for name in (
        "selection_url.js",
        "selection_policy.js",
        "selection_widgets.js",
    ):
        source += (root / name).read_text(encoding="utf-8") + "\n"
    source += """
var realPlan = window.codaSelectionWidgets.plan;
window.codaSelectionWidgets = {
  plan: function (records, result, tabId) {
    var controls = realPlan(records, result, tabId);
    calls.push(JSON.parse(JSON.stringify({
      records: records, tab: tabId, controls: controls
    })));
    return controls;
  }
};
"""
    source += (root / "report.js").read_text(encoding="utf-8") + "\n"
    source += actions + "\n"
    source += """
console.log(JSON.stringify({
  calls: calls,
  writes: writes,
  hash: window.location.hash,
  created: created,
  widgets: widgetSnapshot(),
  controlsVisible: controlsArea().classList.contains(
    "coda-selection-controls--visible"
  ),
  focused: document.activeElement
    ? document.activeElement.id ||
      document.activeElement.getAttribute("data-target")
    : null,
  hidden: wrappers.map(function (wrapper) {
    return wrapper.children.filter(function (child) {
      return child.classList.contains("coda-state");
    }).map(function (panel) {
      return panel.classList.contains("coda-state--hidden");
    });
  })
}));
"""
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


def test_controller_plans_initial_context_and_creates_labeled_dropdowns() -> None:
    output = _execute("")
    assert output["writes"] == []
    assert output["hash"] == ""
    assert len(output["calls"]) == 1
    call = output["calls"][0]
    assert call["tab"] == "1-results"
    assert [record["tabId"] for record in call["records"]] == [
        "1-results",
        "1-results",
        "2-results",
    ]
    assert call["records"][1]["ancestors"] == [{"dimension": "batch", "value": "A"}]
    assert [control["dimension"] for control in call["controls"]] == [
        "batch",
        "sample",
    ]
    assert output["hidden"] == [[False, True], [False, True], [False]]
    # Was planning only; now two actual labeled categorical controls.
    assert [widget["dimension"] for widget in output["widgets"]] == [
        "batch",
        "sample",
    ]
    assert output["controlsVisible"] is True
    for widget in output["widgets"]:
        assert widget["tag"] == "select"
        assert widget["label"] == widget["dimension"]
        assert widget["labelFor"] == widget["id"]
    assert output["widgets"][0]["value"] == "A"
    assert output["focused"] is None


def test_hashchange_replans_nested_context_and_preserves_explicit_url() -> None:
    fragment = "#tab=1-results&state.batch=B&state.sample=s1"
    output = _execute(
        "",
        "window.location.hash = "
        + json.dumps(fragment)
        + "; windowListeners.hashchange();",
    )
    assert len(output["calls"]) == 2
    assert output["calls"][-1]["controls"] == [
        {
            "dimension": "batch",
            "kind": "categorical",
            "values": ["A", "B"],
            "selected": "B",
        }
    ]
    assert [widget["dimension"] for widget in output["widgets"]] == ["batch"]
    assert output["writes"] == []
    assert output["hash"] == fragment


def test_tab_activation_replans_and_keeps_shared_selection_for_singleton_node() -> None:
    output = _execute(
        "#state.batch=B",
        "tabs[1].listeners.click();",
    )
    assert len(output["calls"]) == 2
    assert output["writes"] == ["#tab=2-results&state.batch=B"]
    call = output["calls"][-1]
    assert call["tab"] == "2-results"
    assert call["controls"] == [
        {
            "dimension": "batch",
            "kind": "categorical",
            "values": ["A", "B"],
            "selected": "B",
        }
    ]
    assert output["hidden"][-1] == [True]
    assert output["widgets"][0]["value"] == "B"


def test_tab_without_states_hides_controls() -> None:
    output = _execute("", "tabs[2].listeners.click();")
    assert output["calls"][-1]["tab"] == "3-methods"
    assert output["calls"][-1]["controls"] == []
    assert output["widgets"] == []
    assert output["controlsVisible"] is False


def test_invalid_tab_plans_for_all_stacked_tabs_without_rewriting_url() -> None:
    output = _execute("#tab=missing")
    assert output["calls"][0]["tab"] is None
    assert [control["dimension"] for control in output["calls"][0]["controls"]] == [
        "batch",
        "sample",
    ]
    assert output["writes"] == []
    assert output["hash"] == "#tab=missing"


def test_dropdown_change_preserves_other_directives_and_focus() -> None:
    output = _execute(
        "#tab=2-results&state.batch=B&state.sample=s2",
        """
var input = inputFor("batch");
input.focus();
input.value = "A";
input.listeners.change();
""",
    )
    assert output["writes"] == ["#tab=2-results&state.batch=A&state.sample=s2"]
    assert output["widgets"][0]["value"] == "A"
    assert output["hidden"][-1] == [False]
    assert output["focused"] == "coda-selection-batch"


def test_unavailable_categorical_selection_is_not_displayed_as_first_value() -> None:
    output = _execute("#state.batch=missing")
    widget = output["widgets"][0]
    assert widget["value"] == ""
    assert widget["options"][0] == {
        "value": "",
        "text": "No selection — all states shown",
        "disabled": True,
    }
    assert output["hidden"][0] == [False, False]


def test_ordered_slider_exposes_raw_value_and_commits_index_as_raw_selection() -> None:
    output = _execute(
        "#state.sample=s1",
        """
var input = inputFor("sample");
input.focus();
input.value = "1";
input.listeners.input();
input.listeners.change();
""",
        setup='wrappers[1].setAttribute("data-kind", "ordered");',
    )
    assert output["writes"] == ["#tab=1-results&state.sample=s2"]
    widget = output["widgets"][1]
    assert widget["tag"] == "input"
    assert widget["type"] == "range"
    assert (widget["min"], widget["max"], widget["step"]) == ("0", "1", "1")
    assert widget["value"] == "1"
    assert widget["valueText"] == "s2"
    assert widget["output"] == "s2"
    assert widget["describedBy"] == widget["outputId"]
    assert widget["labelFor"] == widget["id"]
    assert output["focused"] == "coda-selection-sample"


def test_unselected_ordered_slider_has_an_explicit_non_axis_position() -> None:
    output = _execute(
        "#state.sample=missing",
        setup='wrappers[1].setAttribute("data-kind", "ordered");',
    )
    widget = output["widgets"][1]
    assert widget["min"] == "-1"
    assert widget["value"] == "-1"
    assert widget["valueText"] == "No selection — all states shown"
    assert widget["output"] == widget["valueText"]
    assert output["hidden"][1] == [False, False]
    assert output["writes"] == []


def test_disappearing_focused_control_moves_focus_to_active_tab() -> None:
    output = _execute(
        "",
        """
inputFor("sample").focus();
window.location.hash = "#state.batch=B";
windowListeners.hashchange();
""",
    )
    assert [widget["dimension"] for widget in output["widgets"]] == ["batch"]
    assert output["focused"] == "1-results"


def test_disabled_shared_axis_has_no_control() -> None:
    output = _execute(
        "",
        setup='wrappers[2].setAttribute("data-kind", "ordered");',
    )
    assert [widget["dimension"] for widget in output["widgets"]] == ["sample"]


def test_raw_dropdown_labels_and_values_are_preserved() -> None:
    raw = ' Run <b>A</b> & "quoted" '
    output = _execute(
        "#state.batch=" + "%20Run%20%3Cb%3EA%3C%2Fb%3E%20%26%20%22quoted%22%20",
        setup=(
            "batch.children[0].setAttribute('data-state-value', "
            + json.dumps(raw)
            + ");"
        ),
    )
    widget = output["widgets"][0]
    assert widget["value"] == raw
    assert widget["options"][0]["text"] == raw
    assert widget["options"][0]["value"] == raw


@pytest.mark.parametrize("has_states", [False, True])
def test_renderer_inlines_planner_once_before_controller(has_states: bool) -> None:
    leaf = ComponentEntry(
        kind=EntryKind.RENDERED,
        component_id="example.quality",
        title="Quality",
        outcome=RenderedComponent.from_html("<p>Content.</p>"),
    )
    tabs: tuple[DocumentTab, ...]
    if has_states:
        tabs = (
            DocumentTab(
                title="Results",
                nodes=(
                    StatesEntry(
                        dimension="batch",
                        kind="categorical",
                        panels=(StatePanel(value="A", children=(leaf,)),),
                    ),
                ),
            ),
        )
    else:
        tabs = (
            DocumentTab(title="Results", nodes=(leaf,)),
            DocumentTab(title="Other", nodes=(leaf,)),
        )
    document = ReportDocument(
        title="Planner wiring",
        subtitle=None,
        author=None,
        version=None,
        theme=DEFAULT_THEME,
        logo=None,
        favicon=None,
        manifest=ReportManifest.model_validate(make_manifest_payload()),
        tabs=tabs,
        diagnostics=(),
    )
    page = render_report(document)
    assert page.count("<script>") == 1
    assert page.count("window.codaSelectionWidgets = Object.freeze") == 1
    assert (
        page.index("window.codaSelectionPolicy = Object.freeze")
        < page.index("window.codaSelectionWidgets = Object.freeze")
        < page.index("var planner = window.codaSelectionWidgets")
    )
    assert "controls: planner.plan(records, result, selectedTab)" in page
    assert ".innerHTML" not in page
    assert ".removeChild(" not in page
    # Controls are created by enhancement, not present in the raw HTML.
    assert '<div class="coda-selection-controls"' not in page
    assert re.search(
        r"\.coda-selection-feedback\s*,\s*\.coda-state-missing\s*,\s*"
        r"\.coda-selection-controls\s*\{\s*display:\s*none\s*;",
        page,
    )
    print_blocks = re.findall(
        r"@media print\s*\{((?:[^{}]|\{[^{}]*\})*)\}",
        page,
    )
    assert any(
        re.search(
            r"\.coda-js \.coda-selection-controls\s*\{\s*"
            r"display:\s*none\s*!important\s*;",
            block,
        )
        for block in print_blocks
    )
