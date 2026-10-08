Report State
============

A report is built once from all available report artifacts. It may expose
interactive state variables that allow the user to select a subset or view of
that data in the browser.

The report builder should not require a fixed cohort, sample, or vOTU scope.
Those concepts are represented naturally by components bound to state variables
such as ``sample_id`` and ``votu_id``.

A minimal server-side context remains useful for build metadata and plugin
configuration:

.. code-block:: python

    from dataclasses import dataclass
    @dataclass
    class ReportContext:
      pipeline_name: str
      pipeline_version: str
      manifest: ReportManifest
      layout: ReportLayout

The client-side report state may be represented as:

.. code-block:: javascript

   {
     sample_id: "ERR2867948",
     votu_id: "vOTU_001",
     taxonomy_rank: "family"
   }

The generated report JavaScript is responsible for:

* Initializing state values from layout defaults.
* Optionally overriding defaults from URL query parameters.
* Rendering state controls.
* Validating selected values against the control's available values.
* Broadcasting state-change events.
* Updating bound reactive components.
* Optionally synchronizing state back to the URL.

The command-line interface remains simple:

.. code-block:: bash

    virmake-report \
      --manifest results/report_manifest.json \
      --layout layouts/default.yaml \
      --output results/report/virmake_report.html

A few implementation recommendations follow from this change.

Do not have the layout generate per-sample plots. The layout only declares
bindings. The plugin decides whether to embed data for browser-side filtering or
multiple precomputed views.

Keep state controls as normal layout nodes. This allows a sample selector to
appear at the top of the Samples tab and a vOTU selector at the top of the vOTUs
tab, without hard-coding either in the base template.

Treat unavailable artifacts differently from empty selections. If CheckV was
never run, ``on_missing: placeholder`` applies. If CheckV exists but the
selected sample has no records, the CheckV component itself should display an
empty state.

Prefer state variables over generic “filters.” A “filter” implies exclusion
only. State can represent a selected item, an aggregation level, a display mode,
a threshold, or a category selection.

Start with single-value selects. Implement select for ``sample_id`` and
``votu_id`` first. Add multi-select, numeric range sliders, search/type-ahead,
and linked controls only when actual report requirements justify them.
