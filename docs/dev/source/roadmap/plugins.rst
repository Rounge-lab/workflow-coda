===================
Plugin Architecture
===================

Plugins translate declared report artifacts into named report components.

A plugin may be built into the framework, supplied by an installed extension
package, or provided explicitly by Python code using the framework API.

Plugin Discovery
----------------

Third-party plugins should be discoverable through Python package entry points.

Recommended entry-point group:

.. code-block:: toml

   [project.entry-points."workflow_reports.plugins"]
   example_bio = "example_bio_reports.plugin:get_plugin"

A plugin distribution may also provide layouts, templates, static assets, and
artifact-schema documentation.

The CLI should support:

* Automatic discovery of installed plugins.
* Explicit plugin enablement or disablement.
* A strict mode that fails when requested plugins are unavailable.
* Reporting of discovered, enabled, disabled, and failed plugins.

Plugin Metadata
---------------

Plugins should declare metadata before component construction.

.. code-block:: python

   from dataclasses import dataclass
   from typing import Sequence


   @dataclass(frozen=True)
   class PluginMetadata:
       id: str
       version: str
       requires_framework: str
       artifact_dependencies: Sequence["ArtifactDependency"]
       component_ids: Sequence[str]

This supports early diagnostics such as:

* A required plugin is not installed.
* An artifact type is absent.
* A plugin does not support the manifest schema version.
* Two plugins claim the same component ID.

Plugin Interface

.. code-block:: python

   from typing import Protocol

   class ReportPlugin(Protocol): metadata: PluginMetadata

      def build(
          self,
          artifacts: "ArtifactStore",
          context: "ReportContext",
      ) -> list["ReportComponent"]:
          ...


The framework should isolate plugin failures. By default, a failure in one
non-required plugin should generate a diagnostic and allow unrelated components
to render. Strict mode may promote plugin failures to report-build errors.

Component IDs
-------------

Component IDs are part of a plugin's public API. They should be stable,
namespaced, and documented.

Recommended form:

.. code-block:: text

   <plugin_id>.<component_name>

Examples:

.. code-block:: text

   bio_overview.kpis
   bio_quality.summary
   bio_taxonomy.relative_abundance
   generic.provenance
   generic.diagnostics

The framework must reject duplicate component IDs unless an explicit component
override mechanism is later introduced.
