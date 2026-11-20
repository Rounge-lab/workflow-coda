===============
Report manifest
===============

The manifest is a JSON file declaring the producer and the artifacts
of a pipeline run. Artifact paths are relative to the manifest file.

Loading validates the manifest envelope; it does not read artifact
files. Components read artifacts through the
:doc:`artifact store <../framework/api/artifact_store>`.

Envelope
--------

.. list-table::
   :header-rows: 1

   * - Key
     - Required
     - Shape and meaning
   * - ``schema_version``
     - yes
     - The literal ``"0.3.0"``: the manifest envelope version.
       Earlier versions are not read; regenerate them with
       ``workflow-coda verify``.
   * - ``producer``
     - yes
     - Object identifying the producing workflow or application.
   * - ``artifacts``
     - yes
     - List of artifact declarations, in declaration order. May be
       empty. Artifact ids and types must each be unique.

Unknown model keys are rejected. The manifest version also gates
plugins: a plugin is available only for manifest versions it declares
support for.

Producer
--------

.. list-table::
   :header-rows: 1

   * - Key
     - Required
     - Shape and meaning
   * - ``name``
     - yes
     - Non-empty string identifying the producer.
   * - ``version``
     - yes
     - Non-empty string identifying the producer's version.
   * - ``module_id``
     - no
     - Non-empty string identifying a workflow module.
   * - ``run_id``
     - no
     - Non-empty string identifying a run.

Artifacts
---------

.. list-table::
   :header-rows: 1

   * - Key
     - Required
     - Shape and meaning
   * - ``id``
     - yes
     - Unique identifier matching ``[a-z][a-z0-9_-]*``.
   * - ``type``
     - yes
     - Unique namespaced type: at least two dot-separated
       ``[a-z][a-z0-9_-]*`` segments. Components address artifacts
       by type.
   * - ``schema_version``
     - yes
     - Non-empty string identifying the artifact's content schema
       version. This is distinct from the manifest envelope version.
   * - ``path``
     - yes
     - Path relative to the manifest file, using forward slashes.
       Absolute paths and ``..`` segments are not permitted.
   * - ``format``
     - yes
     - ``json``, ``txt``, ``bytes``, or a namespaced format such as
       ``core.tabular``. A namespaced format's grammar belongs to its
       plugin.
   * - ``status``
     - yes
     - ``complete``, ``partial``, ``failed``, or ``missing``.
   * - ``sha256``
     - no
     - SHA-256 checksum as 64 lowercase hexadecimal characters. The
       store checks it when present.
   * - ``verification``
     - no
     - Object carrying the verifier's account of what was checked, or
       why verification failed. The framework transports it without
       interpreting its format-specific fields.

Only ``complete`` artifacts are eligible for reading. A ``complete``
status alone does not guarantee that the file exists or that its
content is valid. Other statuses describe outputs a run declared but
did not fully produce; a component's unavailable outcome is handled
by the layout's ``on_unavailable`` policy.

Verification records
--------------------

``workflow-coda verify`` records the format and status of its
verification. Successful records carry ``status: "ok"`` and may add
format-specific information, such as ``keys_checked`` for ``json`` or
``sep``, ``header``, and ``rows`` for ``core.tabular``. Failed records
carry ``status: "failed"`` and a ``message``.

The record is opaque to the framework. A hand-written declaration may
omit it. See :doc:`verification-spec` for the input to spec-mode
verification.

Loading
-------

The manifest loader reads strict UTF-8, rejects a byte-order mark,
parses JSON, and validates the envelope. An unsupported schema version
fails before envelope validation. Errors identify the manifest path;
JSON parse errors include a line and column. See the
:doc:`manifest API <../framework/api/manifest>`.

Example
-------

.. code-block:: json

   {
     "schema_version": "0.3.0",
     "producer": {
       "name": "seq-pipeline",
       "version": "1.4.0",
       "run_id": "run-42"
     },
     "artifacts": [
       {
         "id": "sample_metrics",
         "type": "org.example.sample_metrics",
         "schema_version": "1.0",
         "path": "outputs/sample_metrics.json",
         "format": "json",
         "status": "complete",
         "verification": {
           "format": "json",
           "status": "ok",
           "keys_checked": ["depth"]
         }
       }
     ]
   }
