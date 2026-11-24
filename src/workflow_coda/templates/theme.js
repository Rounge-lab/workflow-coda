/* workflow-coda screen theme controller.
 *
 * Figure bindings contain styling only, never duplicate figure data.
 * Initialization is signaled by the from_figure post_script hook.
 * Updates serialize per figure and coalesce to the latest requested mode.
 *
 * This module does not implement print capture.
 */
(function () {
  "use strict";

  var root = document.documentElement;
  var preference = window.matchMedia
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;
  var records = [];

  function mode() {
    var explicit = root.getAttribute("data-coda-theme");
    if (explicit === "light" || explicit === "dark") {
      return explicit;
    }
    return preference && preference.matches ? "dark" : "light";
  }

  function reportError(record, error) {
    record.wrapper.setAttribute("data-coda-figure-theme-error", "true");
    if (window.console && window.console.error) {
      window.console.error("workflow-coda figure theme update failed", error);
    }
  }

  function update(record, selected) {
    var style = record.binding[selected];
    var plotly = window.Plotly;
    var chain = Promise.resolve();

    // One trace at a time: each binding addresses exactly that trace.
    // Plotly restyle wraps scalar values in arrays for trace selection.
    style.traces.forEach(function (trace, index) {
      if (!Object.keys(trace).length) {
        return;
      }
      chain = chain.then(function () {
        var fields = {};
        Object.keys(trace).forEach(function (key) {
          fields[key] = [trace[key]];
        });
        return plotly.restyle(record.graph, fields, [index]);
      });
    });

    return chain.then(function () {
      if (Object.keys(style.layout).length) {
        return plotly.relayout(record.graph, style.layout);
      }
    });
  }

  function pump(record) {
    var selected;
    if (!record.ready || record.busy || record.applied === record.desired) {
      return;
    }
    if (!window.Plotly ||
        typeof window.Plotly.restyle !== "function" ||
        typeof window.Plotly.relayout !== "function") {
      reportError(record, new Error("Plotly styling APIs are unavailable"));
      return;
    }

    selected = record.desired;
    record.busy = true;
    update(record, selected).then(function () {
      record.applied = selected;
      record.busy = false;
      record.wrapper.removeAttribute("data-coda-figure-theme-error");
      pump(record);
    }, function (error) {
      record.busy = false;
      reportError(record, error);
      // Do not retry a failing mode indefinitely. A newer selection
      // may still succeed; another explicit request can retry this one.
      if (record.desired !== selected) {
        pump(record);
      }
    });
  }

  function request() {
    var selected = mode();
    records.forEach(function (record) {
      record.desired = selected;
      pump(record);
    });
  }

  function ready(record) {
    var graph = record.wrapper.querySelector(".plotly-graph-div");
    if (!graph) {
      reportError(record, new Error("Initialized figure has no graph element"));
      return;
    }
    record.graph = graph;
    record.ready = true;
    pump(record);
  }

  Array.prototype.forEach.call(
    document.querySelectorAll(".coda-figure[data-coda-figure-theme]"),
    function (wrapper) {
      var record;
      try {
        record = {
          wrapper: wrapper,
          binding: JSON.parse(wrapper.getAttribute("data-coda-figure-theme")),
          graph: null,
          ready: false,
          busy: false,
          applied: null,
          desired: mode()
        };
        records.push(record);
      } catch (error) {
        reportError({ wrapper: wrapper }, error);
      }
    }
  );

  // Register first, then inspect persistent readiness markers.
  document.addEventListener("coda:figure-ready", function (event) {
    records.forEach(function (record) {
      if (record.wrapper === event.target) {
        ready(record);
      }
    });
  });
  records.forEach(function (record) {
    if (record.wrapper.getAttribute("data-coda-figure-ready") === "true") {
      ready(record);
    }
  });

  if (preference) {
    if (preference.addEventListener) {
      preference.addEventListener("change", request);
    } else if (preference.addListener) {
      preference.addListener(request);
    }
  }

  window.codaTheme = Object.freeze({
    mode: mode,
    set: function (selected) {
      if (selected !== null && selected !== "light" && selected !== "dark") {
        throw new Error("Theme selection must be light, dark, or null");
      }
      if (selected === null) {
        root.removeAttribute("data-coda-theme");
      } else {
        root.setAttribute("data-coda-theme", selected);
      }
      request();
    }
  });
})();
