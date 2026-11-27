========================
Command line interface
========================

The ``workflow-coda`` command line interface is a thin edge over
the library: it validates its own invocation, then hands everything
to code that already knows how to fail with teaching messages.
One command ships today — ``build`` — which runs the whole pipeline
and writes one self-contained HTML page.  The stages behind it are
the framework's own: :doc:`framework/api/manifest` loads and verifies the
manifest, :doc:`framework/api/layout_loader` loads the layout,
:doc:`framework/api/builder` composes the report document with the installed
plugins, and :doc:`framework/api/render` renders the page.

The fastest way to meet the command is the :doc:`"hello world" report
<../tutorials/hello-report>`.

Usage
-----

.. code-block:: text

   workflow-coda build MANIFEST LAYOUT [-o OUTPUT]
   workflow-coda verify MANIFEST (FILE | --spec SPEC) [options]
   workflow-coda --version

``build`` — build a report from a manifest and a layout: load the
manifest's artifact store, build the report document from the
layout with the installed plugins, render it, and write one
self-contained HTML page.

``verify`` — verify pipeline outputs into a report manifest: read
each artifact file, check it under its declared format, and write
the manifest — created, or updated in place — carrying each
artifact's verification record and SHA-256 checksum.  The manifest
is the stable interface ``build`` reads; :doc:`schemas/index` documents
it as written.

``build`` arguments
-------------------

.. list-table::
   :header-rows: 1
   :widths: 18 14 68

   * - Argument
     - Default
     - Meaning
   * - ``MANIFEST``
     - required
     - Path to the report manifest the pipeline wrote.  Must exist
       and be readable; the file name must end in ``.json``.
   * - ``LAYOUT``
     - required
     - Path to the report layout declaring the report.  Must exist
       and be readable; ``.yaml`` or ``.yml``.
   * - ``-o``, ``--output``
     - ``report.html``
     - Path of the HTML page to write; the file name must end in
       ``.html``.

The argument checks run during parsing, so a path that does not
exist, cannot be read, or carries the wrong extension is a *usage
error*: exit code ``2``, before the pipeline starts.

``verify`` arguments
--------------------

``verify`` turns real pipeline output files into a report
manifest — created, or updated in place.  One invocation runs one
mode: *flags mode* verifies the single FILE, its identity declared
by flags; *spec mode* verifies every artifact a YAML spec declares,
each artifact path resolving against the spec's own directory.
Passing both FILE and --spec — or neither — is a teaching, not a
usage error: exit ``1``, the modes named.

.. list-table::
   :header-rows: 1
   :widths: 18 14 68

   * - Argument
     - Default
     - Meaning
   * - ``MANIFEST``
     - required
     - Path of the manifest to create or update.  The file name
       must end in ``.json``; an existing manifest is updated in
       place, a missing one is created — and creating requires a complete
       producer identity resolved from CLI and/or spec declarations.
   * - ``FILE``
     - optional
     - Flags mode: the artifact file to verify.  Must exist and be
       readable; any extension — the format claim lives in
       ``--format``, not the file name.
   * - ``--spec SPEC``
     - optional
     - Spec mode: a YAML file declaring artifacts and optional producer claims.
       ``.yaml`` or ``.yml``; must exist and be readable.
   * - ``--id``
     - —
     - The artifact's id within the manifest (flags mode).
   * - ``--type``
     - —
     - The artifact's namespaced type, e.g. ``org.example.samples``
       (flags mode).
   * - ``--format``
     - —
     - The artifact's format: ``json``, ``txt``, ``bytes``, or a
       namespaced name like ``core.tabular`` (flags mode).
   * - ``--schema-version``
     - —
     - The artifact's content schema version, e.g. ``"1.0"``
       (flags mode).
   * - ``--producer-name``, ``--producer-version``
     - —
     - Optional producer claims. In spec mode these merge field by
       field with the spec; matching duplication is accepted and
       conflicts are rejected. Creating requires a resolved name
       and version. Updating may omit either field; supplied claims
       must match the recorded producer.
   * - ``--run-id``
     - —
     - The producing run's identifier, recorded on creation; on
       update, a mismatch with the recorded run is a teaching — one
       manifest describes one run.
   * - ``--criteria KEY=VALUE``
     - —
     - One verification criterion, repeatable.  The value rides
       to the format's verifier as one string — the pair
       ``keys=depth,rate`` means the single value ``depth,rate``;
       the format's verifier owns the comma grammar.  A pair
       without ``=``, an empty key, or one key passed twice is a
       teaching.
   * - ``--on-failure``
     - ``fail``
     - What a failed verification does.  ``fail`` aborts the run
       with the teaching and writes nothing — in spec mode every
       artifact is still attempted, and the failures are raised
       together, one line each.  ``write`` records the failed
       artifact on the manifest — status ``failed``, the teaching
       in its verification record, no checksum — prints one
       warning line per failed artifact on stderr, and exits
       ``0``: the recording is the command's success.

Supplied producer names, versions, and run IDs must be non-empty
strings. Invalid claims abort before artifact verification, under
either failure policy. Omitting ``--run-id`` on update retains the
recorded run; supplying it must match, including when the recorded
run ID is absent.

Flags mode requires the four identity flags together; the library
teaches when one is missing (exit ``1``), naming the set, rather
than letting the parser report a usage error for the first one it
happens to notice.  A format no loaded verifier offers is a
teaching too, with the available formats named.

An artifact that verifies lands on the manifest with status
``complete``, its SHA-256 checksum, and the verifier's record;
rerunning with the same ``--id`` updates the declaration in place,
the type repeating.  Reusing an id with a different type, or
introducing a new id for a type another artifact already carries,
is a teaching — the report framework resolves artifacts by type.
The manifest is written once, atomically, after every artifact has
been placed; a crash never leaves a torn manifest.

The pipeline-side workflow — a spec beside the outputs, verify as
the workflow's last rule, reruns and recorded failures — is walked
in :doc:`../how-to/producing-manifests`.

Exit codes
----------

.. list-table::
   :header-rows: 1
   :widths: 8 92

   * - Code
     - Meaning
   * - ``0``
     - Success.  ``build``: the page is written and nothing is
       printed.  ``verify``: one summary line prints on stdout —
       and under ``--on-failure write`` a recorded failure still
       exits ``0``: the manifest records it, one warning per
       failure prints on stderr, and the recording is the
       command's success.
   * - ``1``
     - The framework — or the write destination — diagnosed a
       failure: a teaching message on stderr.  The correction
       clock is the input files or the environment, never the
       CLI.  Every framework diagnosis derives from
       :py:class:`~workflow_coda.errors.WorkflowCodaError`.
       ``verify`` reaches it for its own teachings: a spec that
       does not parse, a mode contradiction, a missing identity
       flag, a criterion without ``KEY=VALUE`` shape, a producer
       or run mismatch, a manifest conflict, a format no verifier
       offers, a verification failure under ``--on-failure fail``.
   * - ``2``
     - Usage error, per the POSIX/GNU convention: a wrong flag, a
       missing argument, an input path that does not exist or
       cannot be read, a ``verify`` MANIFEST whose name does not
       end in ``.json``, an ``--on-failure`` value outside the
       two.  The usage line prints on stderr, before the pipeline
       starts.

Anything else — an uncaught exception — is a CLI bug, and fails
loudly with a traceback.

One boundary inside the failure family is worth knowing: an input
problem argparse catches is a usage error (``2``), but a
*destination* that refuses the write — the page, the manifest — is
a write failure (``1``): the work itself succeeded; only the write
could not happen.

Streams
-------

Diagnostics print on stderr — the usage line, the teaching
messages, the write-refusal message.  ``build``'s success path
prints nothing: the written page and exit code ``0`` are the whole
report of success.  ``verify``'s success prints one summary line
on stdout, naming what happened::

   created manifest.json (producer seq-pipeline 1.4.0) — verified and appended artifact sample_metrics
   verified outputs/depth.json — updated artifact depth in manifest.json
   verified 2 artifacts — appended 1, updated 1 in manifest.json

Under ``--on-failure write``, each recorded failure adds one
warning line on stderr, carrying the teaching that failed it.

The destination pre-flight
--------------------------

Each command's destination — ``build``'s page, ``verify``'s
manifest — is checked before the pipeline runs, so an unwritable
destination costs a usage error's worth of nothing instead of a
full pipeline's work: the same exit-1 failure, discovered early.
Both the pre-flight's early warning and the write's own refusal
print one shape::

   could not write the report to 'report.html': <the reason>

``verify``'s variant names the manifest's path in the same words.

Version
-------

``workflow-coda --version`` prints the framework's version, read
from installation metadata (``workflow-coda v<version>``) — or
``workflow-coda (version unknown: not installed)`` when running
from an uninstalled source tree.
