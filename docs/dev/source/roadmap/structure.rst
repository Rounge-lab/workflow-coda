===========================
Suggested Package Structure
===========================

The core framework is implemented as the ``workflow_coda`` package. The
manifest and artifact-store foundation is implemented as described below;
the remaining modules land with their milestones.

.. code-block:: text
   :caption: Core framework structure

   workflow_coda/
   ├── __init__.py
   ├── __main__.py
   ├── cli.py
   ├── builder.py
   ├── errors.py
   ├── artifact_store.py
   ├── manifest/
   │   ├── __init__.py
   │   ├── types.py
   │   ├── artifact.py
   │   ├── envelope.py
   │   └── loader.py
   ├── theme.py
   ├── context.py
   ├── components.py
   ├── diagnostics.py
   ├── plugins.py
   ├── registry.py
   ├── layout.py
   ├── state.py
   ├── validation.py
   ├── rendering/
   │   ├── __init__.py
   │   ├── environment.py
   │   └── assets.py
   ├── templates/
   │   ├── report.html.jinja
   │   ├── macros/
   │   │   └── layout.html.jinja
   │   └── components/
   │       ├── component.html.jinja
   │       ├── notice.html.jinja
   │       ├── unavailable.html.jinja
   │       ├── provenance.html.jinja
   │       └── diagnostics.html.jinja
   ├── layouts/
   │   └── generic.yaml
   └── _static/
       ├── report.css
       ├── report.js
       └── plotly.min.js

The ``manifest`` package is the manifest data contract: constrained shared
types, artifact declarations, the manifest envelope, and manifest loading.
``artifact_store`` resolves and reads declared artifacts relative to the
manifest root. ``errors`` holds the exception hierarchy shared by the whole
framework. ``theme`` defines the design-token theme model shared by the report
CSS and plugin-generated figures; the render context exposes it to plugins.

.. code-block:: text
   :caption: Example extension package

   example_bio_reports/
   ├── __init__.py
   ├── plugin.py
   ├── artifacts.py
   ├── schemas.py
   ├── plugins/
   │   ├── overview.py
   │   ├── quality.py
   │   ├── taxonomy.py
   │   └── annotation.py
   ├── layouts/
   │   └── default.yaml
   └── templates/
       └── components/

.. code-block:: toml
   :caption: Example entry-point declaration

   [project.entry-points."workflow_coda.plugins"]
   example_bio = "example_bio_reports.plugin:get_plugin"

Testing Strategy
----------------

Implemented for the manifest and artifact-store foundation:

* Manifest loading and validation (envelope, producer metadata, artifact
  declarations).
* Manifest-relative artifact path resolution and containment, including
  symbolic links.
* Artifact status handling for complete, partial, failed, and missing
  declarations.
* Checksum verification over the exact bytes that are parsed.
* Artifact loading for TSV and JSON, including malformed input.
* Error wrapping: every failure surfaces as a typed ``WorkflowCodaError``.
* Plugin behavior with complete, absent, empty, and malformed artifacts.
* Artifact schema validation for each artifact type a plugin consumes.
* Component registry duplicate-ID detection.
* Layout schema validation.
* Unknown component reference behavior.
* ``on_missing`` policy behavior.
* Cohort and sample report scope behavior.
* Successful HTML generation for partial runs.
* Plotly included once in a generated report.
* Accessibility checks for tab controls where practical.
* Theme model validation (core tokens present, color syntax, series
  palette length).
* Component contract invariants: status/field pairing for every
  outcome, id shapes, blank-text gates, and the constructor helpers —
  including the figure embedding flags, pinned with a fake
  Plotly-shaped figure.
* Plugin assembly integrity: prefix enforcement, duplicate component
  ids, declaration-order preservation, and frozen/slots value
  semantics.
* Registry behavior: namespace assembly, ``find``/``require`` lookup,
  schema-version gating, and entry-point loading through real
  ``importlib.metadata`` entry points against a fixture plugin module.
* Layout model: every authoring rule as shape validation against
  payload dictionaries — visible-text gates, id shape, unknown keys,
  enum coercion, the missing policy's default and override, frozen
  semantics, empty-section rejection.
* Layout loader: real YAML files exercising every failure family, with
  the teaching messages pinned — including the boolean-trap
  explanation and duplicate-key rejection with line numbers.
* Report builder: placement resolution and the missing policy across
  all three resolution cases, plugin-bug capture (with control-flow
  exceptions passing through), and declared-then-strict theme and
  asset loading; plus document-model guards for the entry, asset, and
  diagnostic contracts.
