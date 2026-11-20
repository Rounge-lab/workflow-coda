/* workflow-coda selection policy.
 *
 * Input nodes carry dimension, kind, values, and ancestor selections.
 * Output carries report-wide selections, available axes, active nodes,
 * and teaching messages. This module touches no DOM or URL.
 */
(function () {
  "use strict";

  function dictionary() {
    return Object.create(null);
  }

  function unique(values) {
    var seen = dictionary();
    return values.filter(function (value) {
      if (seen[value]) {
        return false;
      }
      seen[value] = true;
      return true;
    });
  }

  function orderedValues(nodes, values) {
    var edges = dictionary();
    var degrees = dictionary();
    var output = [];
    var remaining = values.slice();
    var index;
    var next;

    values.forEach(function (value) {
      edges[value] = [];
      degrees[value] = 0;
    });
    nodes.forEach(function (node) {
      var position;
      var before;
      var after;
      for (position = 1; position < node.values.length; position += 1) {
        before = node.values[position - 1];
        after = node.values[position];
        if (edges[before].indexOf(after) < 0) {
          edges[before].push(after);
          degrees[after] += 1;
        }
      }
    });

    while (remaining.length) {
      index = -1;
      remaining.some(function (value, position) {
        if (degrees[value] === 0) {
          index = position;
          return true;
        }
        return false;
      });
      if (index < 0) {
        return null;
      }
      next = remaining.splice(index, 1)[0];
      output.push(next);
      edges[next].forEach(function (value) {
        degrees[value] -= 1;
      });
    }
    return output;
  }

  function evaluate(nodes, directive) {
    var dimensions = unique(nodes.map(function (node) {
      return node.dimension;
    }));
    var groups = dictionary();
    var dependencies = dictionary();
    var disabled = dictionary();
    var resolved = dictionary();
    var selections = dictionary();
    var axes = dictionary();
    var kinds = dictionary();
    var issues = directive.issues.map(function (problem) {
      return problem.message;
    });
    var remaining;
    var progress;

    function refuse(dimension, explanation) {
      disabled[dimension] = true;
      issues.push(
        "Cannot select dimension " + JSON.stringify(dimension) + ": " +
          explanation + "; correct the shared states declarations. " +
          "This dimension remains stacked."
      );
    }

    function active(node) {
      return node.ancestors.every(function (ancestor) {
        var selected = selections[ancestor.dimension];
        return selected === null || selected === undefined ||
          selected === ancestor.value;
      });
    }

    dimensions.forEach(function (dimension) {
      var group = nodes.filter(function (node) {
        return node.dimension === dimension;
      });
      var values = unique([].concat.apply([], group.map(function (node) {
        return node.values;
      })));
      groups[dimension] = group;
      kinds[dimension] = group[0].kind;
      dependencies[dimension] = unique([].concat.apply(
        [],
        group.map(function (node) {
          return node.ancestors.map(function (ancestor) {
            return ancestor.dimension;
          }).filter(function (name) {
            return name !== dimension;
          });
        })
      ));
      if (group.some(function (node) {
        return node.kind !== kinds[dimension];
      })) {
        refuse(dimension, "shared nodes declare different axis kinds");
      } else if (kinds[dimension] === "ordered" &&
                 orderedValues(group, values) === null) {
        refuse(dimension, "shared ordered axes impose contradictory ordering");
      }
    });

    Object.keys(directive.states).forEach(function (dimension) {
      if (dimensions.indexOf(dimension) < 0) {
        issues.push(
          "Unknown state dimension " + JSON.stringify(dimension) +
            " with selection " + JSON.stringify(directive.states[dimension]) +
            "; remove its directive, or name a dimension present in the report."
        );
      }
    });

    function resolve(dimension) {
      var group = groups[dimension].filter(active);
      var values = unique([].concat.apply([], group.map(function (node) {
        return node.values;
      })));
      var explicit = Object.prototype.hasOwnProperty.call(
        directive.states, dimension
      );
      var selected = explicit ? directive.states[dimension] : values[0];

      if (kinds[dimension] === "ordered" && !disabled[dimension]) {
        values = orderedValues(group, values);
      }
      axes[dimension] = values;
      if (directive.invalidFragment || disabled[dimension] ||
          directive.invalidDimensions[dimension]) {
        selected = null;
      } else if (explicit && values.indexOf(selected) < 0) {
        issues.push(
          "Selection " + JSON.stringify(selected) + " for dimension " +
            JSON.stringify(dimension) +
            " is unavailable in the selected outer context; choose an " +
            "available value, or remove its directive to use the default. " +
            "This dimension remains stacked."
        );
        selected = null;
      }
      selections[dimension] = selected === undefined ? null : selected;
      resolved[dimension] = true;
    }

    remaining = dimensions.slice();
    while (remaining.length) {
      progress = false;
      remaining = remaining.filter(function (dimension) {
        if (dependencies[dimension].every(function (parent) {
          return resolved[parent];
        })) {
          resolve(dimension);
          progress = true;
          return false;
        }
        return true;
      });
      if (!progress) {
        remaining.forEach(function (dimension) {
          refuse(dimension, "nested dimensions have cyclic dependencies");
          selections[dimension] = null;
          resolved[dimension] = true;
        });
        remaining.forEach(resolve);
        remaining = [];
      }
    }

    return {
      dimensions: dimensions,
      selections: selections,
      axes: axes,
      kinds: kinds,
      disabled: disabled,
      active: nodes.map(active),
      issues: issues
    };
  }

  window.codaSelectionPolicy = Object.freeze({
    evaluate: evaluate
  });
})();
