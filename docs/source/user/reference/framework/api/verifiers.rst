===================
Framework verifiers
===================

The framework provides three artifact verifiers: ``json``, ``txt``,
and ``bytes``. They are available unconditionally in every registry.
The core plugin also provides :doc:`core.tabular
<../../core/tabular-verifier>`, which is subject to plugin availability
and manifest-version gating.

A verifier receives the artifact's bytes and a criteria mapping. On
success it returns a verification record. The verification engine
computes the SHA-256 digest over the same bytes that the verifier
checked. See :doc:`../../schemas/verification-spec` for spec-mode
declarations and :doc:`../../cli` for command-line invocation.

Criteria belong to the verifier. Spec files can provide typed values;
command-line criteria are passed as strings.

json
----

The ``json`` verifier decodes the artifact as strict UTF-8 and parses
it as JSON. Without criteria, any successfully parsed top-level JSON
value passes.

.. list-table::
   :header-rows: 1

   * - Criterion
     - Shape
     - Meaning
   * - ``keys``
     - Non-empty list of unique strings, or a comma-separated string
     - Requires a top-level object containing each named key. Other
       keys are permitted.

For a comma-separated string, whitespace around each name is stripped.
Empty or duplicate names are rejected. Unknown criteria are rejected.

A successful record contains:

* ``format: "json"``
* ``status: "ok"``
* ``keys_checked``: the normalized list of names, when ``keys`` was
  supplied.

Example spec criterion:

.. code-block:: yaml

   criteria:
     keys: [depth, rate]

txt
---

The ``txt`` verifier checks that the bytes decode as strict UTF-8. It
does not check the text's content and accepts no criteria.

A successful record contains ``format: "txt"`` and ``status: "ok"``.

bytes
-----

The ``bytes`` verifier makes no content claim and accepts no criteria.
File existence and readability are checked by the verification engine
before the verifier is called.

A successful record contains ``format: "bytes"`` and ``status: "ok"``.

Failures
--------

Invalid UTF-8, invalid JSON, unmet criteria, and unsupported criteria
are verification failures. The command's failure policy determines
whether a failure aborts the run or is recorded in the manifest. A
recorded failure contains the format, ``status: "failed"``, and a
``message`` explaining the failure.
