Partial and Insufficient Data Handling
======================================

Expected missing data must not be treated as a fatal rendering error.

Examples include:

* CheckV was not run.
* DRAMv was not run.
* No viral genomes passed filtering.
* Only one sample is available for ordination.
* A sample has zero abundance for all retained vOTUs.
* An annotation artifact is empty.

Plugins should produce either:

* No component.
* An unavailable component with a clear message.
* A component containing an explanatory result.

For example:

.. code-block:: text

   Bray-Curtis ordination is unavailable because fewer than two samples were
   included in this run.

A failed plugin should not necessarily fail the entire report. The report builder
should collect recoverable plugin errors and render a diagnostics section.

Report Provenance
-----------------

The manifest should include sufficient metadata to interpret and reproduce a
report.

Recommended fields include:

.. code-block:: json

   {
     "pipeline": {
       "name": "VirMake",
       "version": "2.4.0",
       "git_commit": "a1b2c3d",
       "workflow_engine": "Snakemake",
       "workflow_engine_version": "9.1.0"
     },
     "run": {
       "started_at": "2026-10-01T10:30:12Z",
       "completed_at": "2026-10-01T14:02:51Z",
       "config_path": "config.yaml"
     },
     "tools": [
       {
         "name": "checkv",
         "version": "1.0.3"
       },
       {
         "name": "dramv",
         "version": "1.5.0"
       }
     ]
   }

Recommended optional artifact fields include:

.. code-block:: json

   {
     "type": "virmake.relative_abundance",
     "path": "report_data/relative_abundance.tsv",
     "sha256": "..."
   }

The final report should contain a visible or collapsible run-information section.
