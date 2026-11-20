========================
Visual inspection report
========================

Build the report from the repository root::

   pixi run demo

Open the file URL printed by the command. The build directory contains
the generated artifacts, verification spec, manifest, layout, and
self-contained HTML report. Rebuilding replaces that directory.

Remove the generated files with::

   pixi run demo-clean

The verification warning for ``missing.json`` is intentional. The
report's Outcomes tab also contains intentional missing-component and
unavailable-artifact examples.

Inspection checklist
--------------------

* Check header, logo, favicon, theme, footer, and tab navigation.
* Inspect KPI variants, threshold colors, icons, units, and captions.
* Sort, filter, and copy tables; inspect their captions and column order.
* Interact with each chart and resize the browser.
* Change both state selectors and reload the selected URL.
* Inspect markdown formatting and literal substituted data.
* Open and close notices with pointer and keyboard.
* Check responsive layout, print preview, and behavior without JavaScript.
* Inspect the diagnostics ledger for unexpected failures.
* Inspect ``build/manifest.json`` for complete and failed verification
  records, family expansion, and checksums.
