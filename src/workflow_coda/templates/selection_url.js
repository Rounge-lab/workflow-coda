/* workflow-coda selection URL grammar.
 *
 * Structured fragments:
 *   #tab=1-results&state.batch=run-a&state.sample=s1
 *
 * Keys and values are percent-encoded. Raw state values are preserved,
 * never trimmed, lowercased, or slugified. A fragment without "=" or
 * "&" is a legacy tab-panel anchor.
 *
 * This helper is inert: it changes no DOM, history, or selection.
 * The selection controller owns availability, defaults, feedback,
 * and degradation. Parsing reports invalid directives without
 * rewriting the reader's URL.
 *
 * Export: window.codaSelectionURL.parse(fragment) and
 * window.codaSelectionURL.format(tab, states).
 */
(function () {
  "use strict";

  var dimensionPattern = /^[a-z][a-z0-9_-]*$/;

  function dictionary() {
    return Object.create(null);
  }

  function issue(result, dimension, message) {
    result.issues.push({
      dimension: dimension,
      message: message
    });
    if (dimension === null) {
      result.invalidFragment = true;
    } else {
      result.invalidDimensions[dimension] = true;
      delete result.states[dimension];
    }
  }

  function decode(raw, result, dimension, description) {
    try {
      return decodeURIComponent(raw);
    } catch (error) {
      issue(
        result,
        dimension,
        "Cannot decode " + description + " " + JSON.stringify(raw) +
          "; use valid percent-encoded UTF-8 in the fragment, or remove " +
          "the directive."
      );
      return null;
    }
  }

  function readState(result, dimension, rawValue, seen) {
    var value;

    if (seen[dimension]) {
      issue(
        result,
        dimension,
        "State dimension " + JSON.stringify(dimension) +
          " is selected more than once; keep exactly one state directive " +
          "for this dimension."
      );
      return;
    }

    seen[dimension] = true;
    value = decode(
      rawValue,
      result,
      dimension,
      "the value for state dimension " + JSON.stringify(dimension)
    );
    if (value === null) {
      return;
    }

    if (value.length === 0) {
      issue(
        result,
        dimension,
        "State dimension " + JSON.stringify(dimension) +
          " has an empty selection; name a raw axis value, or remove " +
          "the directive to use the default."
      );
      return;
    }

    if (!result.invalidDimensions[dimension]) {
      result.states[dimension] = value;
    }
  }

  function readDirective(result, directive, seen) {
    var separator = directive.indexOf("=");
    var key;
    var rawValue;
    var dimension;
    var value;

    if (separator < 0) {
      issue(
        result,
        null,
        "Fragment directive " + JSON.stringify(directive) +
          " has no '='; use 'tab=<panel-id>' or " +
          "'state.<dimension>=<raw-value>', or remove the directive."
      );
      return;
    }

    key = decode(
      directive.slice(0, separator),
      result,
      null,
      "the directive key"
    );
    if (key === null) {
      return;
    }
    rawValue = directive.slice(separator + 1);

    if (key === "tab") {
      if (seen.tab) {
        result.tab = null;
        result.invalidTab = true;
        issue(
          result,
          null,
          "The fragment selects a tab more than once; keep exactly " +
            "one 'tab=<panel-id>' directive."
        );
        return;
      }

      seen.tab = true;
      value = decode(rawValue, result, null, "the tab selection");
      if (value === null || value.length === 0) {
        result.invalidTab = true;
        if (value === "") {
          issue(
            result,
            null,
            "The tab selection is empty; name a panel id, or remove " +
              "the tab directive to use the default."
          );
        }
        return;
      }
      result.tab = value;
      return;
    }

    if (key.indexOf("state.") === 0) {
      dimension = key.slice(6);
      if (!dimensionPattern.test(dimension)) {
        issue(
          result,
          null,
          "State dimension " + JSON.stringify(dimension) +
            " is not a dimension name; use a lowercase name such as " +
            "'batch' or 'sample_id', or remove the directive."
        );
        return;
      }
      readState(result, dimension, rawValue, seen.states);
      return;
    }

    issue(
      result,
      null,
      "Unknown fragment directive " + JSON.stringify(key) +
        "; use 'tab' or 'state.<dimension>', or remove the directive."
    );
  }

  function parse(fragment) {
    var body = fragment.charAt(0) === "#" ? fragment.slice(1) : fragment;
    var result = {
      tab: null,
      states: dictionary(),
      invalidTab: false,
      invalidDimensions: dictionary(),
      invalidFragment: false,
      issues: [],
      legacy: false
    };
    var seen = {
      tab: false,
      states: dictionary()
    };
    var directives;
    var index;

    if (body.length === 0) {
      return result;
    }

    if (body.indexOf("=") < 0 && body.indexOf("&") < 0) {
      result.legacy = true;
      result.tab = decode(body, result, null, "the legacy tab anchor");
      result.invalidTab = result.tab === null;
      return result;
    }

    directives = body.split("&");
    for (index = 0; index < directives.length; index += 1) {
      readDirective(result, directives[index], seen);
    }
    return result;
  }

  function format(tab, states) {
    var directives = [];
    var dimensions = Object.keys(states);
    var index;
    var dimension;
    var value;

    if (tab !== null && tab !== undefined) {
      if (typeof tab !== "string" || tab.length === 0) {
        throw new Error(
          "Cannot serialize tab " + JSON.stringify(tab) +
            "; supply a non-empty panel id, or null to omit it."
        );
      }
      directives.push("tab=" + encodeURIComponent(tab));
    }

    for (index = 0; index < dimensions.length; index += 1) {
      dimension = dimensions[index];
      value = states[dimension];
      if (!dimensionPattern.test(dimension)) {
        throw new Error(
          "Cannot serialize state dimension " + JSON.stringify(dimension) +
            "; supply a lowercase dimension name such as 'batch' " +
            "or 'sample_id'."
        );
      }
      if (typeof value !== "string" || value.length === 0) {
        throw new Error(
          "Cannot serialize selection " + JSON.stringify(value) +
            " for dimension " + JSON.stringify(dimension) +
            "; supply a non-empty raw axis value, or omit the dimension."
        );
      }
      directives.push(
        encodeURIComponent("state." + dimension) + "=" +
          encodeURIComponent(value)
      );
    }

    return directives.length ? "#" + directives.join("&") : "";
  }

  window.codaSelectionURL = Object.freeze({
    parse: parse,
    format: format
  });
})();
