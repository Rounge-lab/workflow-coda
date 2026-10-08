==========
Background
==========

This document describes the proposed architecture for ``workflow-coda``, a
standalone Python package for generating configurable, static HTML reports from
workflow outputs.

The framework is intended for workflow and pipeline developers who need to
publish useful report artifacts without coupling report rendering to a specific
workflow engine, directory structure, scientific domain, or central HTML
template.

The goal is to make report generation:

* Modular and extensible through installable plugins.
* Independent of workflow-internal directory structures.
* Compatible with workflow managers like ``Snakemake`` and ``Nextflow``, as well
  as plain Python and other execution environments.
* Robust to partial workflow executions and optional analyses.
* Configurable without editing framework-owned templates.
* Reproducible and auditable through explicit manifests and provenance.
* Testable through small, portable artifact fixtures.
* Portable as a single self-contained HTML file.

The central architectural principle is:

.. code-block:: text

   Workflow or analysis system
       -> report-ready artifacts
       -> report manifest
       -> workflow-reports core
       -> installed report plugins
       -> declarative layout configuration
       -> generic HTML renderer
       -> static HTML report

The framework does not require a workflow to use any particular artifact type,
identifier scheme, or scientific vocabulary. For example, a viral-metagenomics
workflow may define artifacts keyed by ``sample_id`` and ``votu_id``, while
another workflow may use ``patient_id``, ``assembly_id``, or no biological
identifiers at all.

Framework and Integration Responsibilities
------------------------------------------

The standalone framework owns the generic reporting platform:

* Manifest loading and validation.
* Manifest-relative artifact resolution.
* Artifact status handling.
* Plugin discovery and registration.
* Component registration and collision detection.
* Layout parsing, validation, and resolution.
* Generic templates, assets, and HTML rendering.
* Report diagnostics and provenance display.
* Static client-side state management.
* Stable Python API and command-line interface.

A workflow integration owns domain-specific behavior:

* Producing report-ready artifacts.
* Defining artifact schemas.
* Reconciling tool-specific identifiers.
* Writing a manifest.
* Implementing domain-specific plugins.
* Providing default layouts, themes, and optional assets.
* Documenting the meaning of artifact types and components.

The core framework must not parse tool-native files, infer workflow output
paths, or contain assumptions about a particular pipeline.
