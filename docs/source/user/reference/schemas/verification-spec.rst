=================
Verification spec
=================

A verification spec is a UTF-8 YAML file declaring artifacts and optional
producer claims that ``workflow-coda verify`` uses when creating or
updating a manifest.

For command syntax and options, see the :doc:`CLI reference <../cli>`.
For the Python interface, see the
:doc:`verification API <../framework/api/verification>`.

Document structure
------------------

.. list-table::
   :header-rows: 1

   * - Key
     - Required
     - Shape and meaning
   * - ``producer``
     - no
     - Mapping containing optional ``name`` and ``version`` claims.
       Supplied non-null values must be non-empty strings.
   * - ``artifacts``
     - yes
     - Non-empty list of artifact mappings, in declaration order.

Unknown document, producer, and artifact model keys are rejected.
The spec has no ``run_id`` field; use ``--run-id`` for the invocation's
run claim.

Producer claims reconcile field by field with ``--producer-name`` and
``--producer-version``. Matching duplication is accepted; conflicting
CLI and spec values are rejected, never overridden. Creating a manifest
requires both resolved fields, supplied by the spec, CLI, or a
combination. Updating may omit either field and retain the recorded
producer; every supplied claim must match it.

An omitted producer block or ``producer: {}`` carries no claims.
``producer: null`` is invalid: a supplied block must be a mapping.
Within that mapping, omitted or ``null`` fields carry no claim.
Empty strings, numbers, and booleans are invalid claims.
Producer and run refusals occur before artifact verification,
independently of ``--on-failure``.

Artifact blocks
---------------

.. list-table::
   :header-rows: 1

   * - Key
     - Required
     - Shape and meaning
   * - ``file``
     - usually
     - Non-empty string identifying the file to verify. Resolved
       against the spec directory. Required for plain blocks and
       ``values`` or ``samplesheet`` families; forbidden for a
       ``glob`` family, whose pattern supplies the path.
   * - ``id``
     - yes
     - Artifact identifier matching ``[a-z][a-z0-9_-]*``.
   * - ``type``
     - yes
     - Namespaced artifact type: at least two dot-separated
       ``[a-z][a-z0-9_-]*`` segments.
   * - ``format``
     - yes
     - ``json``, ``txt``, ``bytes``, or a namespaced format such as
       ``core.tabular``. An available verifier must claim the format.
   * - ``schema_version``
     - yes
     - Non-empty string identifying the artifact's content schema.
   * - ``criteria``
     - no
     - Mapping of verifier-owned criteria to JSON-compatible values.
       Omitted or ``null`` means no criteria for a plain block.
   * - ``for_each``
     - no
     - Mapping declaring one dimension and exactly one value source.
       Expands the block into a family of artifacts.
   * - ``sanitize``
     - no
     - Boolean for a ``for_each`` block; defaults to ``false``. When
       true, uses an address-safe slug in expanded ids and types.

``criteria`` is transported to the verifier, which owns its vocabulary
and validates its values. See the :doc:`framework verifiers
<../framework/api/verifiers>` reference for ``json``, ``txt``, and
``bytes``, and the :doc:`core.tabular verifier
<../core/tabular-verifier>` reference for its reading and shape
criteria. Namespaced plugin formats define their own criteria.

A ``for_each`` block that explicitly supplies ``criteria`` must supply
a mapping, not ``null``.

Families with ``for_each``
--------------------------

A ``for_each`` mapping accepts only ``dimension`` and one of
``values``, ``samplesheet``, or ``glob``. Exactly one source is
required; an empty source is an error.

``dimension`` is a non-empty string. Placeholders use the form
``{dimension}``, where the name matches ``[a-z][a-z0-9_-]*``.
To use a dimension in placeholders, its declared spelling must fit
that grammar.

The block expands once per discovered value, in source order. A
``{dimension}`` placeholder substitutes:

* The raw value in ``file`` and other string fields.
* The raw value throughout ``criteria``, including nested mapping
  keys and string values.
* The raw value in ``id`` and ``type``, or its slug when
  ``sanitize: true``.

Within each criteria mapping, distinct keys must remain distinct after
substitution. If two source keys expand to the same key, expansion is
rejected even when their values are equal. This applies recursively to
nested mappings, including mappings inside lists; substitution never
silently overwrites criteria.

Expanded ids and types must satisfy their ordinary artifact grammars.
Within-family collisions are rejected during expansion, with the source
values named. After expansion and field validation, ids and types must
each be unique across the entire concrete spec, including collisions
between plain blocks and families or between different families.

Whole-spec collisions are collected together and reported with one-based
expanded block positions, in declaration order. These positions are not
YAML line numbers or original template-block positions. Repeating a
declaration within one spec is an error, not an update instruction.
Module attribution does not partition the id or type namespace.

Only an opening ``{`` starts a placeholder; a lone ``}`` is literal.
In a family, an opening brace must start the block's own placeholder.
In a plain block, placeholders in artifact string fields or criteria
keys and string values are rejected, including nested criteria.
There is no markdown-variable exception in a verification spec.

With ``sanitize: true``, a value is lowercased; runs outside
``[a-z0-9_-]`` become a hyphen; edge hyphens are removed; and a result
not starting with a lowercase letter receives the prefix ``s-``. A
value that produces an empty slug is rejected. Sanitization changes
ids and types, not file paths or criteria.

Explicit values
~~~~~~~~~~~~~~~

``values`` is a non-empty list of non-blank strings, used in written
order. Quote numbers and booleans intended as names. Duplicate values
produce identity collisions and are rejected.

.. code-block:: yaml

   producer:
     name: pipeline
     version: "1.0"
   artifacts:
     - for_each:
         dimension: sample
         values: ["Sample A", "Sample B"]
       sanitize: true
       file: "outputs/{sample}.json"
       id: "sample_{sample}"
       type: "org.example.{sample}"
       format: json
       schema_version: "1.0"
       criteria:
         keys: [depth]

Samplesheet
~~~~~~~~~~~

``samplesheet`` is a mapping with:

* ``file``: required non-empty path string, resolved against the spec
  directory.
* ``column``: required non-empty header name.
* ``sep``: optional single-character delimiter; defaults to a tab.

Unknown keys are rejected. The sheet must be UTF-8 and satisfy the
tabular parser's header and row-alignment rules. The named column must
exist; blank and duplicate values are rejected. Values are used in
first-appearance order. A sheet with no data rows is an error.

.. code-block:: yaml

   for_each:
     dimension: sample
     samplesheet:
       file: samples.tsv
       column: sample_id
   file: "outputs/{sample}.json"

Glob
~~~~

``glob`` is a non-empty relative pattern containing exactly one
placeholder, the block's own ``{dimension}``. The placeholder captures
the varying part of the path; other wildcards (``*``, ``?``, or
``[``) are forbidden. The pattern resolves against the spec directory
and supplies the artifact file path, so the block must not also carry
``file``.

Only matches that are files are discovered; directories and other
non-files are ignored. Symlinks resolving to regular files are included.
A file whose captured value is empty or whitespace-only is an error,
even when other files have valid captures.

Matches are used in natural order: digit runs compare numerically.
Equal natural keys, such as ``s1`` and ``s01``, are ordered by their
original case-sensitive spelling, so ordering does not depend on the
filesystem. Hidden files follow the underlying glob behavior and are
not discovered by an ordinary pattern. Discovering no files is an error.

.. code-block:: yaml

   for_each:
     dimension: sample
     glob: "outputs/{sample}.json"

Verification and manifest placement
-----------------------------------

Artifact files resolve against the spec directory, but their recorded
paths are relative to the manifest directory. An artifact outside the
manifest directory cannot be recorded.

The command checks every expanded artifact's path geometry before
verifying any artifact. A later out-of-tree path therefore refuses the
whole invocation before earlier artifact files are read, under either
failure policy. This check uses lexical path arithmetic; it does not
require the artifact to exist or resolve symlinks. A missing output
inside the manifest directory can still be recorded as failed under
``--on-failure write``.

Flags-mode ids, types, formats, and content schema versions validate
against the same field grammars as spec artifacts before artifact
verification. Invalid declarations are invocation errors, not failed
artifact records.

Successful verification records the verifier's result and the SHA-256
of the same bytes that were verified. An artifact already recorded in
the destination manifest with the same id and type is updated in place;
a new artifact is appended. This rerun behavior does not permit duplicate
declarations within the current spec.

Under ``--on-failure fail``, artifact verification failures are
collected and nothing is written. Under ``--on-failure write``, each
failed artifact is recorded with a failure message and no checksum.
Unavailable verifiers, invalid specs, path geometry errors, and
manifest conflicts abort independently of that setting. The manifest
is written once, atomically, after placement succeeds.

Loading rules
-------------

The loader reads UTF-8 YAML, rejects duplicate keys, expands families,
then validates the resulting blocks and their whole-spec identity
uniqueness. Unknown keys and invalid field shapes are errors. Whole-spec
identity collisions are refused before verifier dispatch or artifact
verification, independently of ``--on-failure``. YAML values must have
the expected types: for example, quote ``"1.0"`` to keep a version as a
string. Discovery errors occur during spec loading, before artifact
verification.
