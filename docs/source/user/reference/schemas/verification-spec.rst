=================
Verification spec
=================

A verification spec is a UTF-8 YAML file declaring a producer and the
artifacts that ``workflow-coda verify`` should verify. The command
expands artifact families, verifies the resulting files, and writes
their declarations to a :doc:`manifest <manifest>`.

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
     - yes
     - Mapping containing the producer's ``name`` and ``version``,
       both non-empty strings.
   * - ``artifacts``
     - yes
     - Non-empty list of artifact mappings, in declaration order.

Unknown document, producer, and artifact model keys are rejected.
The spec has no ``run_id`` field. When creating a manifest, its
producer is initialized from the spec; when updating one, the name and
version must match its producer.

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

Expanded ids and types must satisfy their ordinary artifact grammars.
Colliding ids or types within a family are rejected at spec load.
Across blocks, manifest placement rules apply.

Only an opening ``{`` starts a placeholder; a lone ``}`` is literal.
In a family, an opening brace must start the block's own placeholder.
In a plain block, placeholders in artifact string fields or criteria
values are rejected. There is no markdown-variable exception in a
verification spec.

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

Matches are used in natural order. Hidden files follow the underlying
glob behavior and are not discovered by an ordinary pattern. No matches
is an error.

.. code-block:: yaml

   for_each:
     dimension: sample
     glob: "outputs/{sample}.json"

Verification and manifest placement
-----------------------------------

Artifact files resolve against the spec directory, but their recorded
paths are relative to the manifest directory. An artifact outside the
manifest directory cannot be recorded.

Successful verification records the verifier's result and the SHA-256
of the same bytes that were verified. An existing artifact with the
same id and type is updated in place; a new artifact is appended.
Reusing an id for a different type, or a type for a different id, is
an error.

Under ``--on-failure fail``, artifact verification failures are
collected and nothing is written. Under ``--on-failure write``, each
failed artifact is recorded with a failure message and no checksum.
Unavailable verifiers, invalid specs, path geometry errors, and
manifest conflicts abort independently of that setting. The manifest
is written once, atomically, after placement succeeds.

Loading rules
-------------

The loader reads UTF-8 YAML, rejects duplicate keys, expands families,
then validates the resulting blocks. Unknown keys and invalid field
shapes are errors. YAML values must have the expected types: for
example, quote ``"1.0"`` to keep a version as a string. Discovery
errors occur during spec loading, before artifact verification.
