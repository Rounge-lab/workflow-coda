======================================
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

The artifact contract represents these conditions through artifact status.
A producer whose run did not fully produce an artifact should still declare
it, with the appropriate status:

``complete``
    The artifact is fully written and loadable.

``partial``
    The run wrote the artifact but did not complete it.

``failed``
    The analysis producing the artifact failed.

``missing``
    The analysis was not run, or its output is absent.

Only artifacts declared ``complete`` are guaranteed loadable. The artifact
store reports every other status as an expected, typed unavailability
rather than an error. Declaring an unavailable artifact is preferred over
silently omitting it: the report can then distinguish "the analysis was
not run" from "the manifest is unaware of this artifact".

Plugins receiving an unavailable artifact should produce either:

* No component.
* An unavailable component with a clear message.
* A component containing an explanatory result.

For example:

.. code-block:: text

   Bray-Curtis ordination is unavailable because fewer than two samples were
   included in this run.

A failed plugin should not necessarily fail the entire report. The report
builder should collect recoverable plugin errors and render a diagnostics
section.

Report Provenance
-----------------

The manifest envelope carries producer identity only: a ``name``, a
``version``, and an optional ``run_id``. The envelope is a closed, versioned
contract, so richer run metadata does not belong in it.

Run provenance is instead represented as a framework-reserved artifact type
(the ``workflow_coda`` namespace is reserved for framework types):

.. code-block:: text

   workflow_coda.provenance

Modeling provenance as an artifact gives it the same guarantees as every
other report input: explicit declaration in the manifest, a versioned
content schema, path safety, checksum verification, and portability with
the rest of the report bundle. The built-in ``generic`` plugin renders the
provenance artifact through its ``generic.provenance`` component as a
visible or collapsible run-information section.

The content schema of the provenance artifact is defined by the framework
alongside the generic plugin that consumes it. The intended shape covers
pipeline identity and version-control state, the workflow engine and its
version, run timestamps and configuration location, and the tool versions
used:

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
       {"name": "checkv", "version": "1.0.3"},
       {"name": "dramv", "version": "1.5.0"}
     ]
   }

Because the provenance artifact is declared like any other artifact, a
report from a partial run degrades gracefully: the producer omits it, or
declares it with a non-complete status, and the run-information section
shows an explanation instead.

Optional integrity metadata is declared on the artifact itself, as for any
other artifact:

.. code-block:: json

   {
     "type": "virmake.relative_abundance",
     "path": "report_data/relative_abundance.tsv",
     "sha256": "..."
   }
