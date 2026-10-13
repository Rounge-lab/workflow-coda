=======================================
workflow-coda development documentation
=======================================

``workflow-coda`` is a framework for building portable, configurable static
HTML reports from workflow outputs.

It is designed primarily for scientific and bioinformatics workflow developers,
but it is not tied to a specific workflow engine, pipeline, analysis domain, or
artifact format.

A workflow integration supplies a report manifest and report-ready artifacts.
The framework discovers plugins, validates the layout, composes registered
components, and renders a portable static HTML report.

.. toctree::
   :maxdepth: 2
   :caption: Design Goals

   roadmap/background
   roadmap/architecture
   roadmap/layers
   roadmap/artifact_contract
   roadmap/plugins
   roadmap/layout
   roadmap/state
   roadmap/rendering
   roadmap/data_and_provenance
   roadmap/assets
   roadmap/security
   roadmap/structure

.. toctree::
   :maxdepth: 2
   :caption: Reference documentation

   api/errors
   api/manifest
   api/artifact_store
   api/theme
   api/context
   api/components
   api/plugins
   api/registry
   api/layout
   api/layout_loader
   api/builder
   api/report
   api/assets
