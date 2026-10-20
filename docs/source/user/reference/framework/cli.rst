========================
Command line interface
========================

The ``workflow-coda`` command line interface is a thin edge over
the library: it validates its own invocation, then hands everything
to code that already knows how to fail with teaching messages.
One command ships today — ``build`` — which runs the whole pipeline
and writes one self-contained HTML page.  The stages behind it are
the framework's own: :doc:`api/manifest` loads and verifies the
manifest, :doc:`api/layout_loader` loads the layout,
:doc:`api/builder` composes the report document with the installed
plugins, and :doc:`api/render` renders the page.

Usage
-----

.. code-block:: text

   workflow-coda build MANIFEST LAYOUT [-o OUTPUT]
   workflow-coda --version

``build`` — build a report from a manifest and a layout: load the
manifest's artifact store, build the report document from the
layout with the installed plugins, render it, and write one
self-contained HTML page.

Arguments
---------

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

Exit codes
----------

.. list-table::
   :header-rows: 1
   :widths: 8 92

   * - Code
     - Meaning
   * - ``0``
     - Success: the page is written, and nothing is printed.
   * - ``1``
     - The framework — or the write destination — diagnosed a
       failure: a teaching message on stderr.  The correction
       clock is the input files or the environment, never the
       CLI.  Every framework diagnosis derives from
       :py:class:`~workflow_coda.errors.WorkflowCodaError`.
   * - ``2``
     - Usage error, per the POSIX/GNU convention: a wrong flag, a
       missing argument, an input path that does not exist or
       cannot be read.  The usage line prints on stderr, before
       the pipeline starts.

Anything else — an uncaught exception — is a CLI bug, and fails
loudly with a traceback.

One boundary inside the failure family is worth knowing: an input
problem argparse catches is a usage error (``2``), but a
*destination* that refuses the page is a write failure (``1``) —
the report itself succeeded; only the write could not happen.

Streams
-------

Diagnostics print on stderr — the usage line, the teaching
messages, the write-refusal message — and the success path prints
nothing: the written page and exit code ``0`` are the whole report
of success.

The destination pre-flight
--------------------------

The output path is checked before the pipeline runs, so an
unwritable destination costs a usage error's worth of nothing
instead of a full pipeline's work: the same exit-1 failure,
discovered early.  Both the pre-flight's early warning and the
write's own refusal print one shape::

   could not write the report to 'report.html': <the reason>

Version
-------

``workflow-coda --version`` prints the framework's version, read
from installation metadata (``workflow-coda v<version>``) — or
``workflow-coda (version unknown: not installed)`` when running
from an uninstalled source tree.
