===============================
Stable Report Artifact Contract
===============================

Report artifacts are the stable API between an artifact producer and the report
framework.

The framework defines the manifest envelope and artifact lifecycle semantics.
Artifact producers define the meaning and schema of domain-specific artifact
types.

Artifacts should be:

* Portable independently of workflow-internal directory structure.
* Addressable relative to the manifest where possible.
* Explicitly typed and versioned.
* Small enough to distribute and test where practical.
* Validated before use by a plugin.
* Focused on report needs rather than preserving every native tool field.
* Accompanied by auditing, provenance or integrity metadata when required.

Recommended output layout:

.. code-block:: text

   results/
   ├── report_manifest.json
   ├── report_data/
   │   ├── summary.json
   │   ├── sample_metrics.tsv
   │   └── ...
   └── report/
       └── report.html

Artifact Type Names
-------------------

Artifact types should use a namespaced identifier to avoid collisions between
independent plugin and workflow packages.

Recommended form:

.. code-block:: text

   <namespace>.<artifact_name>

Examples:

.. code-block:: text

   org.example.sample_metrics
   org.example.qc_summary
   io.github.projectx.variant_summary
   bio.example.checkv_quality

The framework reserves only its own namespace, for example:

.. code-block:: text

   workflow_reports.provenance
   workflow_reports.diagnostics

A plugin should document every artifact type it consumes, including compatible
schema versions and required fields.

Example Manifest
----------------

.. code-block:: json

   {
     "schema_version": "1.0",
     "producer": {
       "name": "Example workflow",
       "version": "2.4.0",
       "run_id": "2026-10-01T103012Z"
     },
     "artifacts": [
       {
         "id": "sample_metrics",
         "type": "org.example.sample_metrics",
         "schema_version": "1.0",
         "path": "report_data/sample_metrics.tsv",
         "format": "tsv",
         "status": "complete"
       },
       {
         "id": "qc_summary",
         "type": "org.example.qc_summary",
         "schema_version": "1.0",
         "path": "report_data/qc_summary.json",
         "format": "json",
         "status": "complete"
       }
     ]
   }

The core report framework validates the manifest envelope, path safety, status
values, checksums, and artifact metadata. Plugins are responsible for validating
the content and schema versions of artifacts they consume through an entry-point
registry. The framework should permit any declared artifact that a plugin knows
how to consume through a safe API:

.. code-block:: python

   artifact = artifacts.require("org.example.sample_metrics")
   table = artifact.read_tsv()

   payload = artifacts.require("org.example.summary").read_json()
