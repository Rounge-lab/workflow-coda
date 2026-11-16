===========================================
Producing manifests from a workflow manager
===========================================

You run the pipeline.  Somewhere downstream, ``workflow-coda`` will turn the
pipeline's outputs into a report page (:doc:`report-authoring`).  The contract
between the pipeline and ``workflow-coda build`` is the *report manifest* — a
small JSON file declaring who produced the artifacts and where each file lives
with its claimed shape and status.  ``workflow-coda build`` reads that file and
nothing else. Producing it happens during the pipeline run and can be aided by
``workflow-coda verify``.

You can either write the manifest file by hand — the grammar is documented in
:doc:`../reference/framework/schemas`, or you can employ ``workflow-coda
verify``, which reads each artifact file, checks it under its declared format,
and writes the manifest carrying a SHA-256 checksum of exactly the bytes it
checked, and the record of exactly what the check was.

One artifact, one command
-------------------------

The fastest path is to use ``workflow-coda verify``'s *flags mode*: one file,
one command.  The four identity flags declare what the manifest will record
about the file; the producer flags name the pipeline, and are required because
the manifest does not exist yet::

   $ workflow-coda verify manifest.json outputs/sample_metrics.json \
       --id sample_metrics \
       --type org.example.sample_metrics \
       --format json \
       --schema-version 1.0 \
       --producer-name seq-pipeline \
       --producer-version 1.4.0

The run verifies the file and prints its summary on stdout::

   created manifest.json (producer seq-pipeline 1.4.0) — verified and appended artifact sample_metrics

and the manifest it wrote:

.. code-block:: json

   {
     "schema_version": "0.3.0",
     "producer": {
       "name": "seq-pipeline",
       "version": "1.4.0",
       "module_id": null,
       "run_id": null
     },
     "artifacts": [
       {
         "id": "sample_metrics",
         "type": "org.example.sample_metrics",
         "schema_version": "1.0",
         "path": "outputs/sample_metrics.json",
         "format": "json",
         "status": "complete",
         "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
         "verification": {
           "format": "json",
           "status": "ok"
         }
       }
     ]
   }

Two details worth noticing.  The checksum is of exactly the bytes the verifier
checked, computed by the command.  The writer emits every field: optional
and unset options become ``null`` (whereas a hand-written manifest may omit
them).  Passing ``--criteria keys=depth,rate`` would gain the record
``"keys_checked": ["depth", "rate"]``.

Many artifacts: the spec
------------------------

A pipeline typically produces many files, and ``workflow-coda verify`` can
verify them all with just one command.  *Spec mode* reads a small YAML file (the
spec) declaring the run's producer and one block per artifact.  Put it beside
the outputs: every ``file:`` path resolves against the spec's own directory.

.. code-block:: yaml

   # spec.yaml — the pipeline's declaration of its outputs
   producer:
     name: seq-pipeline
     version: "1.4.0"

   artifacts:
     - file: outputs/sample_metrics.json
       id: sample_metrics
       type: org.example.sample_metrics
       format: json
       schema_version: "1.0"
       criteria:
         keys:
           - depth
           - rate

     - file: outputs/reads_per_contig.tsv
       id: reads_per_contig
       type: org.example.reads_per_contig
       format: core.tabular
       schema_version: "1.0"
       criteria:
         sep: "\t"
         header: true
         columns:
           - contig
           - reads
         min_rows: 4

.. code-block:: console

   $ workflow-coda verify manifest.json --spec spec.yaml
   created manifest.json (producer seq-pipeline 1.4.0) — verified 2 artifacts — appended 2, updated 0

The spec is a hand-authored file and gets checked by ``workflow-coda`` when the
command is executed: duplicate keys are rejected naming the key and its line,
unknown keys are rejected, and a spec declaring no artifacts is considered an
authoring mistake.

What to check: criteria
-----------------------

Criteria are the pipeline's promises about content, and each format's verifier
owns its own vocabulary:

.. list-table::
   :header-rows: 1
   :widths: 14 86

   * - Format
     - Criteria
   * - ``json``
     - ``keys`` (the top-level keys that must be present).
   * - ``core.tabular``
     - ``sep`` (single character, tab by default), ``header``
       (boolean, true by default), ``columns`` (header names that
       must be present), ``min_rows`` (data rows, the header
       excluded).
   * - ``txt``, ``bytes``
     - None (the formats claim UTF-8 text and raw existence, and
       anything else is refused).

``json``, ``txt``, and ``bytes`` ship with the framework; ``core.tabular`` is
part of the core plugin; other installed plugins may claim more.  In the spec,
criteria are typed YAML — lists, booleans, integers.  From flags mode, each
``--criteria KEY=VALUE`` is one string, and the comma grammar belongs to the
verifier: ``--criteria keys=depth,rate`` means the single value
``depth,rate``.

A criterion the format does not know, or a value it refuses, is
a verification failure: by default (``--on-failure fail``)
``workflow-coda verify`` aborts the run, if ``--on-failure write`` is used, the
failure is recorded in the manifest file and the artifact's ``status`` is set to
``failed``.  A format no loaded plugin offers is different: the artifact was
never checked, so there is nothing to record. In this case the run aborts,
naming the available formats, regardless of the ``--on-failure`` option.

Reruns, updates, and one run
----------------------------

Pipelines rerun, and ``verify`` is built for it.  Run the same command again and
each artifact *updates in place*, position preserved, checksum and record
refreshed:

.. code-block:: console

   $ workflow-coda verify manifest.json --spec spec.yaml
   verified 2 artifacts — appended 0, updated 2 in manifest.json

A rerun that produces a new artifact appends it and the summary counts both
(``appended 1, updated 1``).  Two authoring mistakes are taught instead of
guessed: reusing an id with a different type, and introducing a new id for a
type another artifact already carries. The report framework resolves artifacts
by type, and either mistake leaves that resolution ambiguous.

One manifest describes a single run of a specific pipeline. It is not meant as a
running log of everything the pipeline ever produced. On update the producer
flags are optional: omit them and the manifest keeps what it records, pass them
and they must repeat exactly what it records. A mismatched ``--run-id`` is
refused with both runs named, since a new run should produce a new manifest. The
spec has no run id field, so a run id can only enter the manifest through flags
mode.  To record one, make the first verification a flags-mode run with
``--run-id``, then verify the remaining artifacts with the spec: spec mode
checks the pipeline's name and version against the manifest, but it cannot see
the run id, so it never quarrels with the recorded one.

When verification fails
-----------------------

A verification can fail for the artifact's own reasons: the file is missing or
the content does not keep its promise.  What happens then is the
``--on-failure`` toggle.

``fail`` (the default) aborts the run with the teaching error on stderr and
writes nothing.  In spec mode every artifact is still attempted, and the
failures are raised together, one line each.  If this happens: fix the pipeline,
rerun, and the manifest stays untouched until a clean pass writes it.

``write`` treats the failure as a fact of the run and records it: the
declaration lands with status ``failed``, the teaching in its ``verification``
record, and no checksum:

.. code-block:: json

   {
     "id": "reads_per_contig",
     "type": "org.example.reads_per_contig",
     "schema_version": "1.0",
     "path": "outputs/reads_per_contig.tsv",
     "format": "core.tabular",
     "status": "failed",
     "sha256": null,
     "verification": {
       "format": "core.tabular",
       "status": "failed",
       "message": "core.tabular verification: the criteria requires at least 4 data rows, but the artifact carries 2"
     }
   }

The command still exits ``0``, printing one warning line per failure on stderr::

   artifact reads_per_contig recorded as failed: core.tabular verification: the criteria requires at least 4 data rows, but the artifact carries 2

A missing output file is a recordable verification failure, which is what
``write`` is for.  To the report, a failed artifact is expected missing data:
the store reports it unavailable, and the report author's ``on_unavailable``
policy decides how it shows in the report (a notice card, by default).

Wiring it into the workflow
---------------------------

``verify`` is designed to be the pipeline's last rule, when every output is in
place. This way the run can produce a single manifest.  The manifest is atomic;
it is replaced whole or not at all, so a killed run either leaves the previous
manifest (or none), never a torn one (at worst a hidden ``.manifest.json.*.tmp``
leftover, safe to delete).

The exit codes are designed for the workflow manager's ``if``:

``0``
   The manifest is written; under ``--on-failure write``, even with failures
   recorded — that is the point: a partial run is a success that tells the
   truth.

``1``
   The inputs or the environment need fixing; the teaching is on stderr and
   nothing was written.

``2``
   The command line itself is wrong: fix the rule, not the pipeline.

An example Snakemake rule:

.. code-block:: python

   rule manifest:
       input:
           "outputs/sample_metrics.json",
           "outputs/reads_per_contig.tsv",
       output:
           "manifest.json",
       shell:
           "workflow-coda verify {output} --spec spec.yaml"

Handing over the manifest
-------------------------

The manifest records paths relative to itself. This way ``manifest.json`` and
the artifacts it declares become portable as one tree.  From there the page can
be constructed with the declared artifacts. The layout, the theme, the tabs
(:doc:`report-authoring`) meet your manifest at ``workflow-coda build``
(:doc:`../reference/framework/cli`).  The end-to-end story is the :doc:`hello
report tutorial <../tutorials/hello-report>`. The exact grammar of every file is
documented at :doc:`../reference/framework/schemas`.
