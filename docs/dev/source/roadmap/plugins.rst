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

   [project.entry-points."workflow_coda.plugins"]
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

Plugin metadata also declares the manifest schema versions the plugin
supports (currently ``"0.1.0"``).  The report builder refuses to run a
plugin whose supported versions do not include the manifest's
``schema_version``, and the diagnostics section names both versions.

The plugin contract
-------------------

A report plugin is a value, not a class hierarchy.  There is no base
class to subclass and no protocol to implement: a plugin package
constructs one frozen ``ReportPlugin`` value — its identity
(``PluginMetadata``) plus the components it offers (a tuple of
``ReportComponent`` declarations) — and returns it from a small
``get_plugin`` function.  Constructing a value is the whole plugin
authoring surface.

Each ``ReportComponent`` declares its own ``render`` callable:

.. code-block:: python

   def render(context, parameters): ...

The report builder invokes it once per rendered report, passing the
report's ``RenderContext`` and the component's layout parameters, and
receives a ``RenderedComponent`` outcome.  The plugin declares *what*
its components are; the builder decides *when* they render.  There is
no dispatch method to implement, because each component knows its own
renderer.

Integrity is enforced where the plugin is assembled, so an authoring
mistake fails in the plugin author's own test run rather than as a
mystery at report time.  Construction raises ``ValueError`` for:

* a plugin id that is not lowercase snake_case;
* blank ``name``, ``version``, or ``description``;
* a component id that is not exactly
   ``<plugin_id>.<component_name>``, lowercase snake_case on both
   sides of exactly one dot;
* a component id that does not start with its own plugin's id, or a
   component id duplicated within a plugin;
* a plugin that declares no components.

The render outcome
------------------

Degradation is data, not error.  A render call returns a
``RenderedComponent`` with one of three statuses:

``ok``
   The component rendered content; its ``html`` is the component body.
   The framework wraps it in the shared card chrome and title.
``unavailable``
   The component's inputs are missing — an artifact declared ``failed``
   or ``missing``, or a condition such as too few samples — and its
   ``message`` explains what and why.  The framework renders the
   message as a notice.
``skipped``
   The plugin intentionally produced no component; nothing is rendered.

The three statuses are constructed through helpers:
``RenderedComponent.from_html`` for hand-written content,
``from_figure`` for a Plotly-shaped figure, ``unavailable`` with an
explanation, and ``skipped``.  ``from_figure`` centralizes the figure
embedding flags — a bare ``div`` without its own Plotly.js bundle,
because the report page loads Plotly.js exactly once — so a plugin
cannot get the embedding wrong.  Expected missing data is a status;
plugin *bugs* are exceptions, which the report builder collects into
the diagnostics section.

Give every figure a description — from_figure(figure, description="…").
Optional in the API, required for components shipped with workflow-coda
and its semi-official extensions: a one-line summary of chart type,
subject and key finding ('Line chart: per-sample depth, all above
10×'), not the component title repeated. The description is the
accessibility label announced to assistive technology — separate from,
and additional to, any visible caption the plot carries.

The render context
------------------

Plugins never touch the filesystem directly and never hard-code
colors.  Both are provided by the ``RenderContext``, constructed once
per report and passed to every render call:

* ``context.store``: the artifact store for the report's manifest.
  Plugins resolve and read artifacts exclusively through the store,
  inheriting its path-safety, status, and checksum guarantees.
* ``context.theme``: the report's design-token theme (see the Theming
  section of the rendering page).  Plugins style figures and other
  generated output from ``context.theme.series`` and the core color
  tokens.

Component-specific configuration travels separately, as the
per-component ``parameters`` argument of the render call: a plain
mapping of JSON-compatible values, exactly as the layout file wrote
them.  The framework interprets none of the keys; each plugin reads and
validates the keys it cares about.  The context is per-report; the
parameters are per-component; they are never merged.

Registering a plugin
--------------------

Plugins are discovered through entry points in the
``workflow_coda.plugins`` group:

.. code-block:: toml

   [project.entry-points."workflow_coda.plugins"]
   example_bio = "example_bio_reports.plugin:get_plugin"

The smallest possible plugin:

.. code-block:: python

   from workflow_coda.components import (
       ComponentParameters, PluginMetadata, ReportComponent,
       RenderedComponent,
   )
   from workflow_coda.context import RenderContext
   from workflow_coda.plugins import ReportPlugin


   def render_qc(
       context: RenderContext, parameters: ComponentParameters
   ) -> RenderedComponent:
       table = context.store.require("org.example.sample_metrics").read_tsv()
       return RenderedComponent.from_html(f"<p>{len(table)} samples</p>")


   def get_plugin() -> ReportPlugin:
       return ReportPlugin(
           metadata=PluginMetadata(
               id="example_bio",
               name="Example bio plugin",
               version="1.0.0",
               description="Quality components for the example pipeline.",
               supported_schema_versions=frozenset({"0.1.0"}),
           ),
           components=(
               ReportComponent(
                   id="example_bio.qc",
                   title="Sample quality",
                   render=render_qc,
               ),
           ),
       )

The registry
------------

The ``PluginRegistry`` loads every plugin in the group and assembles
the component namespace.  Cross-plugin conflicts — two plugins
claiming the same id — fail at load with ``PluginConflictError``.
Component ids cannot collide across plugins without their plugin ids
colliding first, so the registry's component-id re-check is a
defensive backstop for invariant drift.

Schema compatibility is a per-report question: plugins declare the
manifest schema versions they support, and the report builder selects
the plugins that support the manifest's ``schema_version``.  An
incompatible plugin is excluded from the report and named in its
diagnostics, together with the versions both sides support.

Lookup follows the store's pattern: ``find_component`` for inspection
(``None`` when absent), ``require_component`` for the strict form,
which raises ``ComponentUnavailableError`` naming the component ids
that *are* available — the registry counterpart of the store's
``require``, and likewise an expected-missing condition that report
building can handle as policy rather than as failure.

Authoring time and report time
------------------------------

The error type is decided by when the mistake can be corrected.
Contract violations in the types above raise plain ``ValueError`` at
plugin authoring time, in the author's own test run.  Failures while
building a report raise the typed ``PluginError`` family —
``PluginLoadError`` for entry points that fail to import or return the
wrong type, ``PluginConflictError`` for namespace conflicts, and
``ComponentUnavailableError`` for unresolved component ids — all
catchable where the CLI catches the framework's error root.

Testing a plugin
----------------

A plugin is data, so the first test is construction: building the
``ReportPlugin`` exercises every integrity rule above.  Render tests
build a ``RenderContext`` over a small artifact store, call each
component's ``render``, and assert on the *outcome* — status, message,
and html — rather than scraping rendered pages.
``RenderedComponent.from_figure``'s embedding flags are pinned with a
fake Plotly-shaped figure, so the suite needs no Plotly install.
``workflow_coda``'s own suite works this way; its fixture plugin module
doubles as the example above.
