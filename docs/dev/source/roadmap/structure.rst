===========================
Suggested Package Structure
===========================

.. code-block:: text
   :caption: Core framework structure

   workflow-coda/
   ├── __init__.py
   ├── cli.py
   ├── builder.py
   ├── manifest.py
   ├── artifacts.py
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

   [project.entry-points."workflow_reports.plugins"]
   example_bio = "example_bio_reports.plugin:get_plugin"


Testing Strategy
----------------

Recommended tests include:

* Manifest parsing and validation.
* Relative artifact path resolution.
* Required-column validation for each artifact type.
* Plugin behavior with complete, absent, empty, and malformed artifacts.
* Component registry duplicate-ID detection.
* Layout schema validation.
* Unknown component reference behavior.
* ``on_missing`` policy behavior.
* Cohort and sample report scope behavior.
* Successful HTML generation for partial runs.
* Plotly included once in a generated report.
* Accessibility checks for tab controls where practical.
