(function () {
  "use strict";

  var HIDDEN = "coda-table--filtered";
  var SCROLLING = "coda-table__viewport--scrolling";
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
    var viewport = root.querySelector(".coda-table__viewport");
    if (!table || !viewport || !table.tHead || !table.tBodies.length) {
      return;
    }
    var tbody = table.tBodies[0];
    var filterInput = root.querySelector(".coda-table__filter");
    var copyButton = root.querySelector(".coda-table__copy");
    var headers = table.tHead.rows[0].cells;
    var limit = Number(root.getAttribute("data-max-visible-rows")) || 0;
    var copyVisible = root.getAttribute("data-copy-rows") === "visible";
    var original = [];
    var feedbackTimer = null;
    var refreshPending = false;
    var sortIndex = -1;
    var sortDirection = 0;
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

    function refreshViewport() {
      var count = 0;
      var height;
      var row;
      var rect;
      var j;
      if (!limit) {
        return;
      }
      rect = table.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) {
        viewport.classList.remove(SCROLLING);
        viewport.style.removeProperty("max-height");
        viewport.removeAttribute("tabindex");
        viewport.removeAttribute("role");
        viewport.removeAttribute("aria-label");
        return;
      }
      height = table.tHead.getBoundingClientRect().height;
      for (j = 0; j < tbody.rows.length; j += 1) {
        row = tbody.rows[j];
        if (row.classList.contains(HIDDEN)) {
          continue;
        }
        if (count < limit) {
          height += row.getBoundingClientRect().height;
        }
        count += 1;
      }
      if (count <= limit) {
        viewport.classList.remove(SCROLLING);
        viewport.style.removeProperty("max-height");
        viewport.removeAttribute("tabindex");
        viewport.removeAttribute("role");
        viewport.removeAttribute("aria-label");
        return;
      }
      viewport.style.maxHeight = Math.ceil(height) + "px";
      viewport.classList.add(SCROLLING);
      viewport.setAttribute("tabindex", "0");
      viewport.setAttribute("role", "region");
      viewport.setAttribute("aria-label", "Scrollable table rows");
    }

    function scheduleRefresh() {
      if (!limit || refreshPending) {
        return;
      }
      refreshPending = true;
      window.requestAnimationFrame(function () {
        refreshPending = false;
        refreshViewport();
      });
    }

    function resetViewport() {
      viewport.scrollTop = 0;
      refreshViewport();
    }

    function applySort(index, direction) {
      var rows = original.slice(0);
      var numeric;
      var j;
      for (j = 0; j < headers.length; j += 1) {
        headers[j].removeAttribute("aria-sort");
      }
      if (index >= 0) {
        headers[index].setAttribute(
          "aria-sort", direction > 0 ? "ascending" : "descending"
        );
        numeric = headers[index].getAttribute("data-type") === "numeric";
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
          diff = numeric ? Number(av) - Number(bv) : av.localeCompare(bv);
          return direction * diff;
        });
      }
      for (j = 0; j < rows.length; j += 1) {
        tbody.appendChild(rows[j]);
      }
      resetViewport();
    }

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

    function withinViewport(row) {
      var bounds;
      var rowBounds;
      var top;
      if (!copyVisible || !viewport.classList.contains(SCROLLING)) {
        return true;
      }
      bounds = viewport.getBoundingClientRect();
      rowBounds = row.getBoundingClientRect();
      top = Math.max(
        bounds.top,
        table.tHead.getBoundingClientRect().bottom
      );
      return rowBounds.bottom > top &&
        rowBounds.top < bounds.top + viewport.clientHeight;
    }

    for (i = 0; i < headers.length; i += 1) {
      (function (th, index) {
        var button = document.createElement("button");
        button.type = "button";
        if (th.getAttribute("data-key") === "") {
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
          original[j].classList.toggle(
            HIDDEN,
            query !== "" && rowText(original[j]).indexOf(query) === -1
          );
        }
        resetViewport();
      });
    }

    if (copyButton) {
      var copyFeedback = copyButton.querySelector(".coda-table__copy-feedback");
      var copyCount = copyButton.querySelector(".coda-table__copy-count");
      var copyLabel = copyVisible ?
        "Copy visible rows as TSV" : "Copy all matching rows as TSV";
      copyButton.setAttribute("aria-label", copyLabel);
      copyButton.setAttribute("title", copyLabel);

      var showFeedback = function (message, copied) {
        copyButton.classList.remove("coda-table__copy--copied");
        if (copyCount) {
          copyCount.textContent = "";
        }
        if (copyFeedback) {
          copyFeedback.textContent = "";
        }
        if (copied) {
          copyButton.classList.add("coda-table__copy--copied");
          if (copyCount) {
            copyCount.textContent = message;
          }
        } else if (copyFeedback) {
          copyFeedback.textContent = message;
        }
        if (feedbackTimer !== null) {
          window.clearTimeout(feedbackTimer);
        }
        feedbackTimer = window.setTimeout(function () {
          copyButton.classList.remove("coda-table__copy--copied");
          if (copyCount) {
            copyCount.textContent = "";
          }
          if (copyFeedback) {
            copyFeedback.textContent = "";
          }
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
          cells.push(field(headers[j].getAttribute("data-key")));
        }
        lines.push(cells.join("\t"));
        for (j = 0; j < tbody.rows.length; j += 1) {
          row = tbody.rows[j];
          if (row.classList.contains(HIDDEN) || !withinViewport(row)) {
            continue;
          }
          cells = [];
          for (k = 0; k < row.cells.length; k += 1) {
            cells.push(field(row.cells[k].textContent));
          }
          lines.push(cells.join("\t"));
          count += 1;
        }
        if (navigator.clipboard &&
            typeof navigator.clipboard.writeText === "function") {
          try {
            navigator.clipboard.writeText(lines.join("\n")).then(
              function () {
                showFeedback("Copied " + count + " rows", true);
              },
              function () {
                showFeedback(UNAVAILABLE, false);
              }
            );
          } catch (error) {
            showFeedback(UNAVAILABLE, false);
          }
        } else {
          showFeedback(UNAVAILABLE, false);
        }
      });
    }

    if (limit) {
      refreshViewport();
      window.addEventListener("resize", scheduleRefresh);
      if (typeof window.ResizeObserver === "function") {
        var observer = new window.ResizeObserver(scheduleRefresh);
        observer.observe(root);
        observer.observe(table);
      } else if (typeof window.MutationObserver === "function") {
        var visibilityObserver = new window.MutationObserver(scheduleRefresh);
        var ancestor = root;
        while (ancestor) {
          visibilityObserver.observe(ancestor, {
            attributes: true,
            attributeFilter: ["class", "style", "hidden"]
          });
          ancestor = ancestor.parentElement;
        }
      }
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(scheduleRefresh);
      }
    }
  }

  var tables = document.querySelectorAll(".coda-table");
  for (var i = 0; i < tables.length; i += 1) {
    enhance(tables[i]);
  }
}());
