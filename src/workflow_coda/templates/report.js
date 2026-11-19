/* workflow-coda report chrome: coordinated tab and state selection.
 *
 * URL parsing, selection policy, and selector planning are inlined
 * before this controller. Every content panel is already present.
 * Enhancement hides by class or ARIA only; print restores all content.
 *
 * Initial load and hashchange read the URL without rewriting it.
 * Tab interactions preserve state directives. Selector plans are
 * recomputed for the displayed tabs and selected outer context.
 * DOM controls will consume these plans in a later step.
 */
(function () {
  "use strict";

  var codec = window.codaSelectionURL;
  var policy = window.codaSelectionPolicy;
  var planner = window.codaSelectionWidgets;
  var tabs = Array.prototype.slice.call(document.querySelectorAll(".coda-tab"));
  var panels = Array.prototype.slice.call(
    document.querySelectorAll(".coda-tabpanel")
  );
  var wrappers = Array.prototype.slice.call(
    document.querySelectorAll(".coda-states")
  );
  var records = [];
  var localPanels = [];
  var missing = [];
  var feedback;
  var current;

  if (!codec || !policy || !planner || !panels.length) {
    return;
  }

  function childPanels(wrapper) {
    return Array.prototype.filter.call(wrapper.children, function (child) {
      return child.classList.contains("coda-state");
    });
  }

  wrappers.forEach(function (wrapper) {
    var children = childPanels(wrapper);
    var ancestors = [];
    var tabId = null;
    var parent = wrapper.parentElement;
    var notice = document.createElement("p");

    while (parent) {
      if (parent.classList.contains("coda-state")) {
        ancestors.unshift({
          dimension: parent.getAttribute("data-state-dimension"),
          value: parent.getAttribute("data-state-value")
        });
      }
      if (parent.classList.contains("coda-tabpanel")) {
        tabId = parent.id;
      }
      parent = parent.parentElement;
    }
    records.push({
      dimension: wrapper.getAttribute("data-states-dimension"),
      kind: wrapper.getAttribute("data-kind"),
      values: children.map(function (panel) {
        return panel.getAttribute("data-state-value");
      }),
      ancestors: ancestors,
      tabId: tabId
    });
    localPanels.push(children);
    notice.className = "coda-state-missing";
    notice.setAttribute("role", "status");
    wrapper.appendChild(notice);
    missing.push(notice);
  });

  feedback = document.createElement("div");
  feedback.className = "coda-selection-feedback";
  feedback.setAttribute("role", "status");
  feedback.setAttribute("aria-live", "polite");
  panels[0].parentElement.insertBefore(feedback, panels[0]);

  function shown(panel, name) {
    if (window.CustomEvent) {
      panel.dispatchEvent(new window.CustomEvent(name, { bubbles: true }));
    }
  }

  function showFeedback(messages) {
    feedback.textContent = "";
    messages.forEach(function (message) {
      var paragraph = document.createElement("p");
      paragraph.textContent = message;
      feedback.appendChild(paragraph);
    });
    feedback.classList.toggle(
      "coda-selection-feedback--visible", messages.length > 0
    );
  }

  function applyTabs(directive, messages) {
    var selected = directive.tab || panels[0].id;
    var valid = panels.some(function (panel) {
      return panel.id === selected;
    });
    var stacked = directive.invalidFragment || directive.invalidTab || !valid;

    if (!valid) {
      messages.push(
        "Unknown tab " + JSON.stringify(selected) +
          "; choose a report tab, or remove the tab directive to use " +
          "the default. Tabs remain stacked."
      );
    }

    tabs.forEach(function (tab) {
      var active = !stacked && tab.getAttribute("data-target") === selected;
      tab.setAttribute("aria-selected", active ? "true" : "false");
      tab.tabIndex = active ? 0 : -1;
    });
    if (stacked && tabs.length) {
      tabs[0].tabIndex = 0;
    }
    panels.forEach(function (panel) {
      var visible = stacked || panel.id === selected;
      if (tabs.length > 1) {
        panel.setAttribute("aria-hidden", visible ? "false" : "true");
      }
    });
    return stacked ? null : selected;
  }

  function applyStates(result) {
    records.forEach(function (record, index) {
      var selected = result.selections[record.dimension];
      var absent = result.active[index] && selected !== null &&
        record.values.indexOf(selected) < 0;

      missing[index].textContent = absent
        ? "No content for dimension " + JSON.stringify(record.dimension) +
          " at selection " + JSON.stringify(selected) +
          "; choose another value to view this node."
        : "";
      missing[index].classList.toggle("coda-state-missing--visible", absent);

      localPanels[index].forEach(function (panel) {
        var hidden = selected !== null &&
          panel.getAttribute("data-state-value") !== selected;
        panel.classList.toggle("coda-state--hidden", hidden);
        panel.setAttribute("aria-hidden", hidden ? "true" : "false");
      });
    });
  }

  function visible(element) {
    var parent = element;
    while (parent) {
      if (parent.classList.contains("coda-state--hidden") ||
          (parent.classList.contains("coda-tabpanel") &&
           parent.getAttribute("aria-hidden") === "true")) {
        return false;
      }
      parent = parent.parentElement;
    }
    return true;
  }

  function apply() {
    var directive = codec.parse(window.location.hash);
    var result = policy.evaluate(records, directive);
    var messages = result.issues.slice();
    var selectedTab = applyTabs(directive, messages);

    applyStates(result);
    showFeedback(messages);
    current = {
      directive: directive,
      result: result,
      tab: selectedTab,
      controls: planner.plan(records, result, selectedTab)
    };

    document.documentElement.classList.add("coda-js");
    panels.forEach(function (panel) {
      if (visible(panel)) {
        shown(panel, "coda:tab-shown");
      }
    });
    localPanels.forEach(function (children) {
      children.forEach(function (panel) {
        if (visible(panel)) {
          shown(panel, "coda:state-shown");
        }
      });
    });
  }

  function activate(id, focus) {
    var target = tabs.filter(function (tab) {
      return tab.getAttribute("data-target") === id;
    })[0];
    var fragment;

    if (!target) {
      return;
    }
    fragment = codec.format(id, current.directive.states);
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, "", fragment);
      apply();
    } else {
      window.location.hash = fragment;
      apply();
    }
    if (focus) {
      target.focus();
    }
  }

  tabs.forEach(function (tab, index) {
    tab.addEventListener("click", function () {
      activate(tab.getAttribute("data-target"), false);
    });
    tab.addEventListener("keydown", function (event) {
      var target = null;
      if (event.key === "ArrowLeft") {
        target = (index - 1 + tabs.length) % tabs.length;
      } else if (event.key === "ArrowRight") {
        target = (index + 1) % tabs.length;
      } else if (event.key === "Home") {
        target = 0;
      } else if (event.key === "End") {
        target = tabs.length - 1;
      }
      if (target === null) {
        return;
      }
      event.preventDefault();
      activate(tabs[target].getAttribute("data-target"), true);
    });
  });

  // Register reveal listeners before initial activation.
  function resizeShown(e) {
    var panel = e.target;
    var figures = panel.querySelectorAll('.coda-figure .plotly-graph-div');
    if (!figures.length) { return; }

    function tryResize(attempt) {
      if (window.Plotly && Plotly.Plots && Plotly.Plots.resize) {
        figures.forEach(function (f) {
          requestAnimationFrame(function () {
            if (visible(f)) {
              Plotly.Plots.resize(f);
            }
          });
        });
      } else if (attempt < 3) {
        setTimeout(function () { tryResize(attempt + 1); }, 50);
      }
    }

    tryResize(0);
  }

  document.addEventListener('coda:tab-shown', resizeShown);
  document.addEventListener('coda:state-shown', resizeShown);
  window.addEventListener("hashchange", apply);
  apply();
})();
