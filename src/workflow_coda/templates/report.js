/* workflow-coda report chrome: tab navigation.
 *
 * Adds .coda-js to <html> first thing, so a reader without
 * JavaScript (and the DOM before this script runs) sees the full
 * stacked document: every panel, every heading.  With script, the
 * tab bar drives the panels per the ARIA tabs pattern — one visible
 * at a time, arrow-key navigation, hash synced so a link to
 * #panel-id opens that tab.  Printing shows every panel: the
 * stylesheet's print rules win over the interactive hiding. */
(function () {
  "use strict";
  document.documentElement.classList.add("coda-js");
  var tabs = Array.prototype.slice.call(document.querySelectorAll(".coda-tab"));
  var panels = Array.prototype.slice.call(
    document.querySelectorAll(".coda-tabpanel")
  );
  if (tabs.length < 2) {
    return;
  }
  function activate(id, focus) {
    tabs.forEach(function (tab) {
      var selected = tab.getAttribute("data-target") === id;
      tab.setAttribute("aria-selected", selected ? "true" : "false");
      tab.tabIndex = selected ? 0 : -1;
      if (selected && focus) {
        tab.focus();
      }
    });
    panels.forEach(function (panel) {
      panel.setAttribute("aria-hidden", panel.id === id ? "false" : "true");
    });
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, "", "#" + id);
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
  var initial = window.location.hash
    ? window.location.hash.slice(1)
    : panels[0].id;
  activate(initial, false);
})();
