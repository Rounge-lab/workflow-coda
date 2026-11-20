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
:doc:`../reference/schemas/index`, or you can employ ``workflow-coda
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

.. _families-for-each:

Families of artifacts: ``for_each``
-----------------------------------

A pipeline rarely produces single-file outputs. QC files may be produced in
batches, one results table may be produced per sample, and so on.
``workflow-coda`` enables users to handle these axes through the spec's
``for_each`` block. The axis family, the *dimension*, is declared once (e.g.
``batch`` or ``sample_id``) and the *source* discovers its values.
``workflow-coda verify``
expands the block into its concrete members before anything is
verified: the spec loads as if every block had been written out by
hand, and the manifest never knows the family existed. ``for_each`` can exist in
one of three shapes:

.. code-block:: yaml

   # Pre-determined values
   - for_each: {dimension: batch, values: [b1, b2, b3]}
     file: "qc/{batch}.json"
     id: "qc-{batch}"
     type: "org.example.qc-{batch}"
     format: json
     schema_version: "1.0"

   # Values derived from a sample sheet
   - for_each:
       dimension: sample_id
       samplesheet: {file: samples.csv, column: sample, sep: ","}
     file: "tables/{sample_id}.tsv"
     id: "table-{sample_id}"
     type: "org.example.table-{sample_id}"
     format: core.tabular
     schema_version: "1.0"

   # Values derived through file glob
   - for_each: {dimension: sample_id, glob: "tables/{sample_id}.tsv"}
     id: "table-{sample_id}"
     type: "org.example.table-{sample_id}"
     format: core.tabular
     schema_version: "1.0"

The house shape follows the sources.  ``file:`` is required with
``values`` and ``samplesheet``, and forbidden with ``glob`` (the
glob is its own path provider).  The glob carries exactly one
placeholder, the block's own ``{dimension}``; the rest of the
pattern is the file's literal shape.  The samplesheet is a small
mapping (``file``, ``column``, and an optional ``sep``).

Each source carries its own order, and the order is the
declaration order in the manifest. ``values`` remain sorted as written.
When a samplesheet is provided, samples remain in the same order as declared in
the samplesheet.  The glob orders values in *natural* order (i.e. ``s2`` before
``s10``).

A family that discovers no values (an empty list, an empty
column, a glob matching nothing) aborts at spec load with the
source named, whatever ``--on-failure`` says: an empty family
declares no artifacts, and there is nothing yet to record.  A
family *member* whose file is missing is different: that is the
artifact's own fact, recordable under ``write`` exactly like any
other missing output.  And on rerun a family behaves like any
block: each member updates in place, its position in the manifest
remain preserved.

Names and addresses: ``sanitize``
---------------------------------

Sample names may be end-user provided data. In some cases, this could cause
issues for ``workflow-coda``. ``id:`` and ``type:`` are *addresses* and must fit
their ``workflow-coda`` grammar.  Add the samplesheet family to the spec:

.. code-block:: yaml

   - for_each:
       dimension: sample_id
       samplesheet: {file: samples.csv, column: sample, sep: ","}
     file: "tables/{sample_id}.tsv"
     id: "table-{sample_id}"
     type: "org.example.table-{sample_id}"
     format: core.tabular
     schema_version: "1.0"

with a sheet carrying capitalized names:

.. code-block:: text

   sample
   S-1
   S-2

The run refuses at spec load (before any artifact is verified) with the teaching
on stderr and exit 1:

.. code-block:: text

   spec.yaml: the value 'S-1' for dimension 'sample_id' does not fit the artifact id grammar — ids and types are addresses, never display names; pass 'sanitize: true' to use its slug ('s-1'), or fix the value in its source

You can let ``workflow-coda`` automatically reformat these values to match the
required grammar.  Add ``sanitize: true`` to the block and rerun:

.. code-block:: console

   $ workflow-coda verify manifest.json --spec spec.yaml
   verified 4 artifacts — appended 2, updated 2 in manifest.json

The two family members were appended; the spec's earlier artifacts
updated in place.  The manifest carries each member with the raw
name on the disk side and the re-formatted slug on the address side:

.. code-block:: json

   {
     "id": "table-s-1",
     "type": "org.example.table-s-1",
     "schema_version": "1.0",
     "path": "tables/S-1.tsv",
     "format": "core.tabular",
     "status": "complete",
     "sha256": "3c990b8f5f4e2a7d6b1c8e4f9a2b5d7c1e6f3a8b4d9c2e7f1a6b5d8c3e9f2a4b7",
     "verification": {
       "format": "core.tabular",
       "status": "ok",
       "sep": "\t",
       "header": true,
       "rows": 12
     }
   }

``sanitize: true`` substitutes the *slug* into ``id:`` and
``type:`` only.  The slug is lowercase; every run of characters
outside ``[a-z0-9_-]`` becomes one ``-``; edge hyphens strip; a
result not starting with a lowercase letter gains an ``s-``
prefix (``S-42`` slugs to ``s-42``, ``42`` to ``s-42``); a value
that slugs to nothing teaches.  Ids are addresses,
never display names: the raw name
never disappears, it lives on in the artifact's ``path``.

Two values that expand to the same address refuse the spec load
together, e.g. ``S-1`` and ``s-1`` under ``sanitize: true``, or a
value listed twice.  The report side addresses
each member by its own type: a layout placement names
``org.example.table-s-1`` directly.

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
(:doc:`../reference/cli`).  The end-to-end story is the :doc:`hello
report tutorial <../tutorials/hello-report>`. The exact grammar of every file is
documented at :doc:`../reference/schemas/index`.
