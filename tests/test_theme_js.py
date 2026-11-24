"""Executable screen-theme controller tests.

Node.js is test-time only. These fixtures test promise sequencing,
not real Plotly rendering, browser layout, or printing.
"""

import importlib.resources
import json
import shutil
import subprocess
from typing import Any

import pytest

_FIXTURE = r"""
var listeners = {};
var mediaListeners = {};
var attributes = {};
var wrappers = [];
var calls = [];
var pending = [];
var errors = [];

var root = {
  getAttribute: function (name) {
    return Object.prototype.hasOwnProperty.call(attributes, name)
      ? attributes[name] : null;
  },
  setAttribute: function (name, value) { attributes[name] = value; },
  removeAttribute: function (name) { delete attributes[name]; }
};

var media = {
  matches: false,
  addEventListener: function (name, callback) {
    mediaListeners[name] = callback;
  }
};

var document = {
  documentElement: root,
  querySelectorAll: function () { return wrappers; },
  addEventListener: function (name, callback) {
    listeners[name] = callback;
  }
};

var window = {
  matchMedia: function () { return media; },
  console: {
    error: function () { errors.push("error"); }
  },
  Plotly: {
    restyle: function (graph, fields, indices) {
      calls.push({kind: "trace", fields: fields, indices: indices});
      return new Promise(function (resolve, reject) {
        pending.push({resolve: resolve, reject: reject});
      });
    },
    relayout: function (graph, fields) {
      calls.push({kind: "layout", fields: fields});
      return new Promise(function (resolve, reject) {
        pending.push({resolve: resolve, reject: reject});
      });
    }
  }
};

function wrapper(isReady) {
  var attrs = {
    "data-coda-figure-theme": JSON.stringify({
      light: {
        layout: {"font.color": "#111111"},
        traces: [{"marker.color": "#222222"}]
      },
      dark: {
        layout: {"font.color": "#eeeeee"},
        traces: [{"marker.color": "#dddddd"}]
      }
    })
  };
  if (isReady) {
    attrs["data-coda-figure-ready"] = "true";
  }
  var result = {
    attrs: attrs,
    getAttribute: function (name) { return attrs[name] || null; },
    setAttribute: function (name, value) { attrs[name] = value; },
    removeAttribute: function (name) { delete attrs[name]; },
    querySelector: function () { return {}; }
  };
  wrappers.push(result);
  return result;
}

function flush() {
  return new Promise(function (resolve) { setImmediate(resolve); });
}

async function settle() {
  await flush();
  while (pending.length) {
    pending.shift().resolve();
    await flush();
  }
}

function output(value) {
  console.log(JSON.stringify(value));
}
"""


def _execute(setup: str, body: str) -> Any:
    node = shutil.which("node")
    if node is None:
        pytest.skip("install Node.js to execute theme JavaScript tests")
    source = (
        importlib.resources.files("workflow_coda") / "templates" / "theme.js"
    ).read_text(encoding="utf-8")
    script = (
        _FIXTURE
        + "\n"
        + setup
        + "\n"
        + source
        + "\n(async function () {\n"
        + body
        + "\n})().catch(function (error) {\n"
        + "console.error(error); process.exitCode = 1;\n"
        + "});"
    )
    completed = subprocess.run(
        [node, "-"],
        input=script,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_ready_before_controller_uses_browser_preference() -> None:
    result = _execute(
        "media.matches = true; wrapper(true);",
        "await settle(); output(calls);",
    )
    assert result == [
        {
            "kind": "trace",
            "fields": {"marker.color": ["#dddddd"]},
            "indices": [0],
        },
        {"kind": "layout", "fields": {"font.color": "#eeeeee"}},
    ]


def test_waits_for_initialization_and_uses_latest_mode() -> None:
    result = _execute(
        "var figure = wrapper(false);",
        """
window.codaTheme.set("dark");
await flush();
var before = calls.length;
listeners["coda:figure-ready"]({target: figure});
await settle();
output({before: before, calls: calls});
""",
    )
    assert result["before"] == 0
    assert result["calls"][0]["fields"] == {"marker.color": ["#dddddd"]}


def test_updates_serialize_and_coalesce_to_latest_mode() -> None:
    result = _execute(
        "wrapper(true);",
        """
await flush();
window.codaTheme.set("dark");
window.codaTheme.set("light");
window.codaTheme.set("dark");
var whileBusy = calls.length;
await settle();
output({whileBusy: whileBusy, calls: calls});
""",
    )
    assert result["whileBusy"] == 1
    assert [call["kind"] for call in result["calls"]] == [
        "trace",
        "layout",
        "trace",
        "layout",
    ]
    assert result["calls"][-1]["fields"] == {"font.color": "#eeeeee"}


def test_explicit_selection_overrides_preference_until_cleared() -> None:
    result = _execute(
        "",
        """
window.codaTheme.set("light");
media.matches = true;
mediaListeners.change();
var explicit = window.codaTheme.mode();
window.codaTheme.set(null);
output({
  explicit: explicit,
  restored: window.codaTheme.mode(),
  attribute: root.getAttribute("data-coda-theme")
});
""",
    )
    assert result == {"explicit": "light", "restored": "dark", "attribute": None}


def test_duplicate_readiness_does_not_repeat_completed_updates() -> None:
    result = _execute(
        "var figure = wrapper(true);",
        """
await settle();
listeners["coda:figure-ready"]({target: figure});
await settle();
output(calls.length);
""",
    )
    assert result == 2


def test_failed_update_surfaces_error_and_can_retry() -> None:
    result = _execute(
        "var figure = wrapper(true);",
        """
await flush();
pending.shift().reject(new Error("failed"));
await flush();
var marked = figure.getAttribute("data-coda-figure-theme-error");
var count = calls.length;
window.codaTheme.set("light");
await settle();
output({
  marked: marked,
  count: count,
  errors: errors.length,
  cleared: figure.getAttribute("data-coda-figure-theme-error")
});
""",
    )
    assert result == {
        "marked": "true",
        "count": 1,
        "errors": 1,
        "cleared": None,
    }


def test_invalid_explicit_mode_is_rejected() -> None:
    result = _execute(
        "",
        """
var rejected = false;
try {
  window.codaTheme.set("sepia");
} catch (error) {
  rejected = true;
}
output(rejected);
""",
    )
    assert result is True
