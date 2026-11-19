"""Controller integration for tab/context-aware selector planning.

The shipped JavaScript executes against a minimal DOM fixture.
This verifies dependency wiring, ancestry discovery, and replanning
through real controller handlers. It does not simulate browser layout,
accessibility, focus, printing, or Plotly.
"""

import importlib.resources
import json
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

function element(classes, attributes, parent) {
  var names = classes ? classes.split(" ") : [];
  var attrs = attributes || {};
  var value = {
    id: attrs.id || "",
    children: [],
    parentElement: parent || null,
    listeners: {},
    textContent: "",
    className: classes || "",
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
    insertBefore: function (child, before) {
      child.parentElement = value;
      value.children.splice(value.children.indexOf(before), 0, child);
    },
    addEventListener: function (name, handler) {
      value.listeners[name] = handler;
    },
    focus: function () {},
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
  documentElement: element(""),
  querySelectorAll: function (selector) {
    if (selector === ".coda-tab") { return tabs; }
    if (selector === ".coda-tabpanel") { return panels; }
    if (selector === ".coda-states") { return wrappers; }
    throw new Error("Unexpected selector: " + selector);
  },
  createElement: function (tag) {
    created.push(tag);
    return element("");
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
"""


def _execute(initial_hash: str, actions: str = "") -> Any:
    node = shutil.which("node")
    if node is None:
        pytest.skip("install Node.js to execute controller-planner integration tests")

    root = importlib.resources.files("workflow_coda") / "templates"
    source = _DOM
    source += "\nwindow.location.hash = " + json.dumps(initial_hash) + ";\n"
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


def test_controller_plans_initial_context_without_writing_url_or_creating_widgets() -> None:
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
    assert call["records"][1]["ancestors"] == [
        {"dimension": "batch", "value": "A"}
    ]
    assert [control["dimension"] for control in call["controls"]] == [
        "batch",
        "sample",
    ]
    assert output["hidden"] == [[False, True], [False, True], [False]]
    assert set(output["created"]) <= {"p", "div"}


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
    assert output["writes"] == []
    assert output["hash"] == fragment


def test_tab_activation_replans_and_keeps_shared_selection_for_singleton_node() -> None:
    output = _execute(
        "#state.batch=B",
        'tabs[1].listeners.click();',
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
    # The singleton node is hidden by B, so its shared selector is
    # still relevant: choosing A will restore the node's content.
    assert output["hidden"][-1] == [True]


def test_tab_without_states_plans_no_controls() -> None:
    output = _execute("", "tabs[2].listeners.click();")
    assert output["calls"][-1]["tab"] == "3-methods"
    assert output["calls"][-1]["controls"] == []


def test_invalid_tab_plans_for_all_stacked_tabs_without_rewriting_url() -> None:
    output = _execute("#tab=missing")
    assert output["calls"][0]["tab"] is None
    assert [control["dimension"] for control in output["calls"][0]["controls"]] == [
        "batch",
        "sample",
    ]
    assert output["writes"] == []
    assert output["hash"] == "#tab=missing"


@pytest.mark.parametrize("has_states", [False, True])
def test_renderer_inlines_planner_once_before_controller(has_states: bool) -> None:
    leaf = ComponentEntry(
        kind=EntryKind.RENDERED,
        component_id="example.quality",
        title="Quality",
        outcome=RenderedComponent.from_html("<p>Content.</p>"),
    )
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
    # Three helpers plus the controller still share one script tag.
    assert page.count("<script>") == 1
    assert page.count("window.codaSelectionWidgets = Object.freeze") == 1
    assert (
        page.index("window.codaSelectionPolicy = Object.freeze")
        < page.index("window.codaSelectionWidgets = Object.freeze")
        < page.index("var planner = window.codaSelectionWidgets")
    )
    assert "controls: planner.plan(records, result, selectedTab)" in page
