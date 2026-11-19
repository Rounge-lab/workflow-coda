/* workflow-coda selector planning.
 *
 * Records use the selection-policy shape plus tabId, the containing
 * tab panel's id. Policy results supply global, context-dependent
 * axes and selections.
 *
 * A selector is locally relevant when an active states node on a
 * displayed tab uses its dimension. Its choices remain global:
 * a locally singleton node still needs access to a shared axis
 * when another selection can hide or restore its content.
 *
 * Disabled, empty, and genuinely singleton axes have no widget.
 * A null tab means tabs are stacked; all displayed tabs contribute.
 * A null selection stays null: planning never invents a chosen value.
 *
 * This helper is inert. The controller owns DOM controls, focus,
 * URL writes, and updates after tab or outer-state changes.
 *
 * Export: window.codaSelectionWidgets.plan(records, result, tabId).
 */
(function () {
  "use strict";

  function relevant(records, result, dimension, tabId) {
    return records.some(function (record, index) {
      return record.dimension === dimension &&
        result.active[index] &&
        record.values.length > 0 &&
        (tabId === null || record.tabId === tabId);
    });
  }

  function plan(records, result, tabId) {
    var controls = [];

    result.dimensions.forEach(function (dimension) {
      var values = result.axes[dimension];

      if (result.disabled[dimension] || values.length < 2 ||
          !relevant(records, result, dimension, tabId)) {
        return;
      }

      controls.push({
        dimension: dimension,
        kind: result.kinds[dimension],
        values: values.slice(),
        selected: result.selections[dimension]
      });
    });

    return controls;
  }

  window.codaSelectionWidgets = Object.freeze({
    plan: plan
  });
})();
