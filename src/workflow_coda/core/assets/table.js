(function () {
  "use strict";

  var HIDDEN = "coda-table--filtered";
  var COPY_LABEL = "Copy as TSV";
  var UNAVAILABLE = "copy unavailable in this browser";
  var FEEDBACK_MS = 1500;

  function field(text) {
    if (/[\t\n\r"]/.test(text)) {
      return '"' + text.replace(/"/g, '""') + '"';
    }
    return text;
  }

  function enhance(root) {
    var table = root.querySelector("table");
    if (!table || !table.tHead || !table.tBodies.length) {
      return;
    }
    var tbody = table.tBodies[0];
    var filterInput = root.querySelector(".coda-table__filter");
    var copyButton = root.querySelector(".coda-table__copy");
    var headers = table.tHead.rows[0].cells;
    var original = [];
    var feedbackTimer = null;
    var i;
    for (i = 0; i < tbody.rows.length; i += 1) {
      original.push(tbody.rows[i]);
    }

    function cellText(row, index) {
      return row.cells[index].textContent.trim();
    }

    function rowText(row) {
      var parts = [];
      var j;
      for (j = 0; j < row.cells.length; j += 1) {
        parts.push(row.cells[j].textContent);
      }
      return parts.join("\n").toLowerCase();
    }

    function applySort(index, direction) {
      var rows = original.slice(0);
      var numeric;
      var th;
      var j;
      for (j = 0; j < headers.length; j += 1) {
        headers[j].removeAttribute("aria-sort");
      }
      if (index < 0) {
        for (j = 0; j < rows.length; j += 1) {
          tbody.appendChild(rows[j]);
        }
        return;
      }
      th = headers[index];
      th.setAttribute("aria-sort", direction > 0 ? "ascending" : "descending");
      numeric = th.getAttribute("data-type") === "numeric";
      rows.sort(function (a, b) {
        var av = cellText(a, index);
        var bv = cellText(b, index);
        var diff;
        if (av === "" || bv === "") {
          if (av === "" && bv === "") {
            return 0;
          }
          return av === "" ? 1 : -1;
        }
        if (numeric) {
          diff = Number(av) - Number(bv);
        } else {
          diff = av.localeCompare(bv);
        }
        return direction * diff;
      });
      for (j = 0; j < rows.length; j += 1) {
        tbody.appendChild(rows[j]);
      }
    }

    var sortIndex = -1;
    var sortDirection = 0;

    function onHeaderClick(index) {
      if (sortIndex !== index) {
        sortIndex = index;
        sortDirection = 1;
      } else if (sortDirection > 0) {
        sortDirection = -1;
      } else {
        sortIndex = -1;
        sortDirection = 0;
      }
      applySort(sortIndex, sortDirection);
    }

    for (i = 0; i < headers.length; i += 1) {
      (function (th, index) {
        var button = document.createElement("button");
        button.type = "button";
        if (th.textContent.trim() === "") {
          button.setAttribute("aria-label", "Sort");
        }
        while (th.firstChild) {
          button.appendChild(th.firstChild);
        }
        th.appendChild(button);
        button.addEventListener("click", function () {
          onHeaderClick(index);
        });
      }(headers[i], i));
    }

    if (filterInput) {
      filterInput.addEventListener("input", function () {
        var query = filterInput.value.trim().toLowerCase();
        var j;
        for (j = 0; j < original.length; j += 1) {
          var matches = query === "" || rowText(original[j]).indexOf(query) !== -1;
          original[j].classList.toggle(HIDDEN, !matches);
        }
      });
    }

    if (copyButton) {
      var feedback = function (message) {
        copyButton.textContent = message;
        if (feedbackTimer !== null) {
          window.clearTimeout(feedbackTimer);
        }
        feedbackTimer = window.setTimeout(function () {
          copyButton.textContent = COPY_LABEL;
          feedbackTimer = null;
        }, FEEDBACK_MS);
      };
      copyButton.addEventListener("click", function () {
        var lines = [];
        var cells = [];
        var count = 0;
        var j;
        var k;
        var row;
        for (j = 0; j < headers.length; j += 1) {
          cells.push(field(headers[j].textContent));
        }
        lines.push(cells.join("\t"));
        for (j = 0; j < tbody.rows.length; j += 1) {
          row = tbody.rows[j];
          if (row.classList.contains(HIDDEN)) {
            continue;
          }
          cells = [];
          for (k = 0; k < row.cells.length; k += 1) {
            cells.push(field(row.cells[k].textContent));
          }
          lines.push(cells.join("\t"));
          count += 1;
        }
        var text = lines.join("\n");
        if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
          navigator.clipboard.writeText(text).then(
            function () {
              feedback("Copied " + count + " rows");
            },
            function () {
              feedback(UNAVAILABLE);
            }
          );
        } else {
          feedback(UNAVAILABLE);
        }
      });
    }
  }

  var tables = document.querySelectorAll(".coda-table");
  for (var i = 0; i < tables.length; i += 1) {
    enhance(tables[i]);
  }
}());
