(function () {
  "use strict";

  var UNAVAILABLE = "copy unavailable in this browser";
  var FEEDBACK_MS = 1500;

  function enhance(root) {
    var code = root.querySelector("pre > code");
    var button = root.querySelector(".coda-prose__copy");
    var feedback = root.querySelector(".coda-prose__copy-feedback");
    var status = root.querySelector(".coda-prose__copy-status");
    var feedbackTimer = null;

    if (!code || !button || !feedback || !status) {
      return;
    }

    function showFeedback(message, copied) {
      if (feedbackTimer !== null) {
        window.clearTimeout(feedbackTimer);
      }

      button.classList.toggle("coda-prose__copy--copied", copied);
      feedback.textContent = copied ? "" : message;
      status.textContent = copied ? message : "";

      feedbackTimer = window.setTimeout(function () {
        button.classList.remove("coda-prose__copy--copied");
        feedback.textContent = "";
        status.textContent = "";
        feedbackTimer = null;
      }, FEEDBACK_MS);
    }

    button.addEventListener("click", function () {
      if (
        !navigator.clipboard ||
        typeof navigator.clipboard.writeText !== "function"
      ) {
        showFeedback(UNAVAILABLE, false);
        return;
      }

      // Preserve whitespace, including the fence's trailing newline.
      button.disabled = true;
      try {
        navigator.clipboard.writeText(code.textContent).then(
          function () {
            button.disabled = false;
            showFeedback("Copied code", true);
          },
          function () {
            button.disabled = false;
            showFeedback(UNAVAILABLE, false);
          }
        );
      } catch (error) {
        button.disabled = false;
        showFeedback(UNAVAILABLE, false);
      }
    });

    // Show controls only after their handler has been installed.
    root.classList.add("coda-prose__code-block--enhanced");
  }

  var blocks = document.querySelectorAll(".coda-prose__code-block");
  for (var i = 0; i < blocks.length; i += 1) {
    enhance(blocks[i]);
  }
}());
