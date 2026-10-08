======================
Layer Responsibilities
======================

Workflow or analysis system
---------------------------

The artifact producing system executes analyses and produces primary outputs. It
may be implemented with workflow managers like ``Snakemake`` or ``Nextflow``,
through a Python application, or another execution environment.

The artifact producing system must not need to know HTML, Jinja, CSS, or report
layout.

Report artifact production
--------------------------

Artifact production converts workflow-specific, tool-specific, or application-
specific outputs into report-ready artifacts.

The artifact producer is responsible for:

* Parsing native tool outputs where necessary.
* Reconciling identifiers.
* Selecting report-relevant fields.
* Defining domain-specific artifact schemas.
* Writing portable artifacts.
* Producing the report manifest.

The report framework consumes declared artifacts but does not prescribe how they
are created.

Report manifest
---------------

The manifest is the stable interface between an artifact producer and the
report framework. It declares available artifacts, their types, locations,
schemas, status, and provenance.

The report framework discovers data exclusively through the manifest rather than
through hard-coded paths or workflow-engine APIs.

Framework plugin layer
----------------------

Plugins consume artifacts and produce named report components. Plugins may be
provided by the framework, a domain-specific extension package, or an individual
workflow project. Plugins consume report manifests to generate report
components.

Plugins should not decide top-level layout like component placement, tab
structure, or page ordering.

Layout configuration
--------------------

The layout configures report composition. It determines where registered
components, state controls, groups, and notices appear. Layouts may be supplied
by the framework, a plugin package, a workflow integration, or an end user.
Report components are composed through a composable ``YAML`` declaration. This
allows report developers to rapidly change report layout without modifying
underlying component generation or the rendering engine.

Additional configuration for theming may be provided such as css, color
palettes, icons, logos, favicons, etc.

Generic renderer
----------------

The generic renderer uses the layout configuration to generate the final HTML
report through recursive rendering. It provides javascript for client-side
report navigation (e.g. tabs) and state management (e.g. filters/buttons).
