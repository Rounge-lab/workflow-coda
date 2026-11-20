=====================
core.tabular verifier
=====================

``core.tabular`` verifies a tabular artifact using the parsing, header,
and row-alignment rules shared with :doc:`core.table <table>`. Its
default reading uses a tab delimiter and a header row.

The verifier checks artifact shape and optional pipeline promises.
Presentation choices, such as column order and selection for display,
belong to the component rather than the verifier.

The core plugin declares this verifier. It is available when the
plugin is loaded and supports the manifest schema version being
written. This differs from the unconditional
:doc:`framework verifiers <../framework/api/verifiers>`.

Criteria
--------

.. list-table::
   :header-rows: 1

   * - Criterion
     - Shape and default
     - Meaning
   * - ``sep``
     - Single-character string; default: tab
     - Delimiter used to parse the artifact.
   * - ``header``
     - Boolean; default: ``true``
     - Whether the first parsed row is a header. String spellings
       ``true`` and ``false`` are also accepted, ignoring case and
       surrounding whitespace.
   * - ``columns``
     - Non-empty list of unique strings, or a comma-separated string;
       omitted by default
     - Requires the named columns to be present in the header.
       Requires ``header: true``.
   * - ``min_rows``
     - Non-negative integer or integer string; omitted by default
     - Requires at least this many data rows. A header row is not
       counted. Booleans are rejected.

For a comma-separated ``columns`` string, whitespace around each name
is stripped. Empty or duplicate names are rejected. Unknown criteria
are rejected.

Checks
------

The verifier:

* Decodes the artifact as strict UTF-8.
* Parses it using the declared delimiter.
* With ``header: true``, checks the header using the same rules as
  ``core.table``.
* With ``header: false``, requires at least one row so the column
  count can be established.
* Checks that data rows align with the established column count.
* Checks the optional ``columns`` and ``min_rows`` promises.

When the header declares an index column, ``columns`` checks the named
columns rather than the index column. A missing named column or too
few data rows is a verification failure.

Example
-------

.. code-block:: yaml

   artifacts:
     - file: outputs/samples.csv
       id: samples
       type: org.example.samples
       format: core.tabular
       schema_version: "1.0"
       criteria:
         sep: ","
         header: true
         columns: [sample_id, depth]
         min_rows: 1

See :doc:`../schemas/verification-spec` for the complete spec
declaration.

Records
-------

A successful record contains:

* ``format: "core.tabular"``
* ``status: "ok"``
* ``sep`` and ``header``: the reading used.
* ``rows``: the number of data rows.
* ``columns_checked``: the normalized names, when ``columns`` was
  supplied.
* ``min_rows``: the required minimum, when supplied.

When the command records a failure, the record instead contains the
format, ``status: "failed"``, and a ``message``. The command's failure
policy determines whether to record the failure or abort the run.
