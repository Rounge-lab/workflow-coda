/* workflow-coda report chrome: coordinated tab and state selection.
 *
 * URL parsing, selection policy, and selector planning are inlined
 * before this controller. Every content panel is already present.
 * Enhancement hides by class or ARIA only; print restores all content.
 *
 * Initial load and hashchange read the URL without rewriting it.
 * Tab and widget interactions preserve other valid directives.
 * Report-wide selections drive controls relevant to the displayed
 * tabs and selected outer context. Only the controls area is rebuilt;
 * content panels are never removed.
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
  var controlsArea = null;
  var controlInputs = Object.create(null);
  var current;
  var unselectedText = "No selection — all states shown";

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

  if (wrappers.length) {
    controlsArea = document.createElement("div");
    controlsArea.className = "coda-selection-controls";
    controlsArea.setAttribute("role", "group");
    controlsArea.setAttribute("aria-label", "Report state selection");
    panels[0].parentElement.insertBefore(controlsArea, panels[0]);
  }

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

  function writeSelection(tabId, states) {
    var fragment = codec.format(tabId, states);
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, "", fragment);
    } else {
      window.location.hash = fragment;
    }
    apply();
  }

  function selectValue(dimension, raw) {
    var states = Object.create(null);
    Object.keys(current.directive.states).forEach(function (name) {
      states[name] = current.directive.states[name];
    });
    states[dimension] = raw;
    writeSelection(
      current.tab === null ? current.directive.tab : current.tab,
      states
    );
  }

  function categoricalControl(plan, container, label) {
    var dropdown = document.createElement("div");
    var button = document.createElement("button");
    var value = document.createElement("span");
    var list = document.createElement("div");
    var iconTemplate = document.getElementById("coda-dropdown-icon");
    var options = [];
    var selected = plan.values.indexOf(plan.selected);
    var active = selected >= 0 ? selected : 0;
    var search = "";
    var searchTimer = null;
    var id = "coda-selection-" + plan.dimension;
    var labelId = id + "-label";
    var valueId = id + "-value";
    var listId = id + "-list";

    dropdown.className = "coda-dropdown";
    button.type = "button";
    button.className = "coda-dropdown-button";
    button.setAttribute("role", "combobox");
    button.setAttribute("aria-labelledby", labelId + " " + valueId);
    button.setAttribute("aria-haspopup", "listbox");
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-controls", listId);

    label.id = labelId;
    value.id = valueId;
    value.textContent = selected < 0 ? unselectedText : plan.values[selected];
    button.appendChild(value);

    if (iconTemplate) {
      button.appendChild(iconTemplate.content.cloneNode(true));
    }

    list.className = "coda-dropdown-list";
    list.id = listId;
    list.setAttribute("role", "listbox");
    list.setAttribute("aria-labelledby", labelId);
    list.hidden = true;

    function setActive(index) {
      active = Math.max(0, Math.min(index, options.length - 1));
      options.forEach(function (option, optionIndex) {
        option.classList.toggle("is-active", optionIndex === active);
      });
      button.setAttribute("aria-activedescendant", options[active].id);
      options[active].scrollIntoView({ block: "nearest" });
    }

    function open() {
      list.hidden = false;
      button.setAttribute("aria-expanded", "true");
      setActive(selected >= 0 ? selected : 0);
    }

    function close() {
      list.hidden = true;
      button.setAttribute("aria-expanded", "false");
      button.removeAttribute("aria-activedescendant");
      options.forEach(function (option) {
        option.classList.remove("is-active");
      });
      search = "";
      clearTimeout(searchTimer);
    }

    function choose(index) {
      // selectValue rebuilds the controls and restores focus by dimension.
      close();
      selectValue(plan.dimension, plan.values[index]);
    }

    plan.values.forEach(function (raw, index) {
      var option = document.createElement("div");
      option.className = "coda-dropdown-option";
      option.id = id + "-option-" + index;
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", index === selected ? "true" : "false");
      option.textContent = raw;
      option.addEventListener("pointermove", function () {
        setActive(index);
      });
      option.addEventListener("pointerdown", function (event) {
        if (event.pointerType === "mouse") {
          event.preventDefault();
        }
      });
      option.addEventListener("click", function () {
        // Keep focus on the combobox before controls are rebuilt.
        button.focus();
        choose(index);
      });
      options.push(option);
      list.appendChild(option);
    });

    button.addEventListener("click", function () {
      if (list.hidden) {
        open();
      } else {
        close();
      }
    });

    button.addEventListener("keydown", function (event) {
      var match;
      if (event.key === "Escape" && !list.hidden) {
        event.preventDefault();
        close();
        return;
      }
      if (event.key === "Tab") {
        close();
        return;
      }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (list.hidden) {
          open();
        } else {
          setActive(active + (event.key === "ArrowDown" ? 1 : -1));
        }
        return;
      }
      if (!list.hidden && (event.key === "Home" || event.key === "End")) {
        event.preventDefault();
        setActive(event.key === "Home" ? 0 : options.length - 1);
        return;
      }
      if (!list.hidden && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        choose(active);
        return;
      }
      if (event.key.length === 1 && event.key !== " " &&
          !event.ctrlKey && !event.metaKey && !event.altKey) {
        event.preventDefault();
        if (list.hidden) {
          open();
        }
        search += event.key.toLocaleLowerCase();
        clearTimeout(searchTimer);
        searchTimer = setTimeout(function () {
          search = "";
        }, 700);
        match = plan.values.findIndex(function (raw) {
          return raw.toLocaleLowerCase().indexOf(search) === 0;
        });
        if (match >= 0) {
          setActive(match);
        }
      }
    });

    // Closing on focus loss also handles clicks outside without registering
    // a document listener for every rebuild of the controls.
    dropdown.addEventListener("focusout", function (event) {
      if (!dropdown.contains(event.relatedTarget)) {
        close();
      }
    });

    dropdown.appendChild(button);
    dropdown.appendChild(list);
    container.appendChild(dropdown);
    return button;
  }

  function orderedControl(plan, container) {
    var input = document.createElement("input");
    var output = document.createElement("span");
    var range = document.createElement("div");
    var ticks = document.createElement("div");
    var position = plan.values.indexOf(plan.selected);

    input.type = "range";
    input.min = position < 0 ? "-1" : "0";
    input.max = String(plan.values.length - 1);
    input.step = "1";
    input.value = String(position);
    output.className = "coda-selection-value";
    output.id = "coda-selection-value-" + plan.dimension;
    input.setAttribute("aria-describedby", output.id);

    range.className = "coda-range";
    ticks.className = "coda-range-ticks";
    ticks.setAttribute("aria-hidden", "true");

    // Reserve the temporary -1 position without showing a state tick.
    if (position < 0) {
      var placeholder = document.createElement("span");
      placeholder.className = "coda-range-tick coda-range-tick--placeholder";
      ticks.appendChild(placeholder);
    }

    plan.values.forEach(function () {
      var tick = document.createElement("span");
      tick.className = "coda-range-tick";
      ticks.appendChild(tick);
    });

    function describe() {
      var index = Number(input.value);
      var text = index < 0 ? unselectedText : plan.values[index];
      output.textContent = text;
      input.setAttribute("aria-valuetext", text);
    }

    // Preview the slider position honestly; commit selection on change.
    input.addEventListener("input", describe);
    input.addEventListener("change", function () {
      var index = Number(input.value);
      if (index >= 0 && index < plan.values.length &&
          Math.floor(index) === index) {
        selectValue(plan.dimension, plan.values[index]);
      }
    });

    range.appendChild(input);
    range.appendChild(ticks);
    container.appendChild(range);
    container.appendChild(output);
    describe();
    return input;
  }

  function fallbackFocus() {
    var target = tabs.filter(function (tab) {
      return tab.getAttribute("data-target") === current.tab;
    })[0];
    var panel;
    if (target || tabs.length) {
      (target || tabs[0]).focus();
      return;
    }
    panel = panels[0];
    panel.setAttribute("tabindex", "-1");
    panel.focus();
  }

  function updateControls() {
    var focusedDimension = null;
    var nextInputs = Object.create(null);

    if (controlsArea === null) {
      return;
    }
    Object.keys(controlInputs).forEach(function (dimension) {
      if (controlInputs[dimension] === document.activeElement) {
        focusedDimension = dimension;
      }
    });

    // This area contains enhancement chrome only, never report content.
    controlsArea.replaceChildren();
    current.controls.forEach(function (plan) {
      var container = document.createElement("div");
      var label = document.createElement("label");
      var input;
      var id = "coda-selection-" + plan.dimension;

      container.className = "coda-selection-control";
      label.textContent = plan.dimension;
      label.setAttribute("for", id);
      container.appendChild(label);
      if (plan.kind === "ordered") {
        input = orderedControl(plan, container);
      } else {
        input = categoricalControl(plan, container, label);
      }
      input.id = id;
      input.setAttribute("data-selection-dimension", plan.dimension);
      controlsArea.appendChild(container);
      nextInputs[plan.dimension] = input;
    });
    controlsArea.classList.toggle(
      "coda-selection-controls--visible", current.controls.length > 0
    );
    controlInputs = nextInputs;
    if (focusedDimension !== null) {
      if (controlInputs[focusedDimension]) {
        controlInputs[focusedDimension].focus();
      } else {
        fallbackFocus();
      }
    }
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
    updateControls();

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
    if (!target) {
      return;
    }
    writeSelection(id, current.directive.states);
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
