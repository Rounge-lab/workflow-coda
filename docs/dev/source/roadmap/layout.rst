Declarative Layout Configuration
================================

The report layout should be represented in ``YAML``. The layout controls
composition while plugins control component content.

Interactive report behavior is controlled through report state. Report state is
a collection of named variables that can be changed by the user in the static
HTML report. Components may optionally bind one or more parameters to those
variables.

For example:

* A ``sample_id`` state variable can drive sample-specific quality and taxonomy plots.
* A ``votu_id`` state variable can drive vOTU-specific annotation views.
* A ``taxonomy_rank`` state variable can drive a taxonomic aggregation plot.

Components without state bindings are global components. For example, cohort
KPIs and a cohort ordination may remain unchanged when a user selects a sample.

State is intentionally generic. The reporting system should not reserve special
semantics for ``sample_id`` or ``votu_id`` beyond their use as conventional,
well-documented state variable names.

Example layout:

.. code-block:: yaml

   version: 1

   report:
     title: Viral Identification Pipeline Report

    state:
    variables:
      - id: sample_id
        label: Sample
        type: select
        source:
          type: manifest_samples
        default: first

      - id: votu_id
        label: vOTU
        type: select
        source:
          type: artifact_column
          artifact: virmake.votu_catalog
          column: votu_id
        default: first

    tabs:
      - id: overview
      title: Cohort Overview
      layout:
        type: row
        class: layout-flex overview
        children:
          - type: component
            ref: overview.kpis

          - type: component
            ref: ordination.bray_curtis
            on_missing: hide

    - id: samples
      title: Samples
      layout:
        type: grid
        columns: 2
        gap: medium
        type: stack
        children:
          - type: state_control
            ref: sample_id
          - type: grid
            columns: 2
            gap: medium
            children:
              - type: component
                ref: checkv.summary
                bind:
                  sample_id: sample_id
                on_missing: placeholder
              - type: component
                ref: taxonomy.relative_abundance
                bind:
                  sample_id: sample_id
                on_missing: hide
    - id: votu
      title: vOTUs
      layout:
        type: stack
        children:
          - type: state_control
            ref: votu_id
          - type: component
            ref: checkv.summary
            on_missing: placeholder
          - type: component
            ref: taxonomy.relative_abundance
            ref: annotation.genome_summary
            bind:
              votu_id: votu_id
            on_missing: hide

Layout configuration enables report rearrangement without modifying a central
template. State controls can likewise be moved, repeated, or grouped through
configuration.

For example, moving CheckV to the overview page is a configuration-only change.

.. code-block:: yaml

   - id: overview
     title: Cohort Overview
     layout:
       type: grid
       columns: 2
       children:
         - type: component
           ref: overview.kpis

         - type: component
           ref: ordination.bray_curtis

         - type: component
           ref: checkv.summary
           bind:
             sample_id: sample_id


State Variables
---------------

A state variable has:

``id``
    A stable machine-readable identifier. Examples include ``sample_id``,
    ``votu_id``, ``taxonomy_rank``, and ``checkv_quality_category``.

``label``
    Human-readable text displayed beside the control.

``type``
    The control and value type. The initial implementation should support
    ``select`` and ``multi_select``.

``source``
    The source from which valid selectable values are obtained.

``default``
    The initial selected value or selection policy.

The initial supported state-value sources should be:

``manifest_samples``
    Populate values from the manifest sample collection.

``artifact_column``
    Populate unique values from a declared column in a normalized report
    artifact.

``static``
    Use values explicitly provided in the layout configuration.


Example ``static`` state variable:

.. code-block:: yaml

   id: taxonomy_rank
   label: Taxonomic rank
   type: select
   source:
     type: static
     values:
       - realm
       - kingdom
       - phylum
       - class
       - order
       - family
       - genus
   default: family


State controls update report state in the browser. The report JavaScript emits
a ``report:state-change`` event whenever a state variable changes. Components
bound to that variable subscribe to the event and update their displayed data.

The URL may optionally be synchronized with state using query parameters or a
URL fragment. This allows a selected state to be bookmarked or shared:

.. code-block:: text

    virmake_report.html?sample_id=ERR2867948&votu_id=vOTU_001

Component State Bindings
------------------------

A component node may bind component parameters to report-state variables.

.. code-block:: yaml

   type: component
   ref: checkv.summary
   bind:
     sample_id: sample_id
   on_missing: placeholder

The key in bind is a parameter exposed by the component. The value is the
ID of a report-state variable.

A component can bind multiple parameters:

.. code-block:: yaml

   type: component
   ref: abundance.sample_votu_profile
   bind:
     sample_id: sample_id
     votu_id: votu_id
   on_missing: hide

Bindings are declared in layout because they describe page composition and user
interaction. Plugin metadata declares which parameters a component supports.

For example:

.. code-block:: python

   ReportComponent(
      id="checkv.summary",
      title="CheckV genome quality summary",
      kind="plot",
      html=initial_html,
      parameters={
          "sample_id": ComponentParameter(
              type="select",
              required=False,
          ),
      },
   )


A layout validator must reject a binding when:

* The referenced state variable does not exist.
* The component does not expose the bound parameter.
* The state-variable value type is incompatible with the component parameter.

Component Update Strategies
---------------------------

A component may be static or reactive.

``static``
    The component does not depend on report state. It is rendered once during
    report generation and has no client-side update behavior.

``reactive``
    The component depends on one or more state variables and updates when its
    bound state changes.

The first implementation should support two reactive strategies:

``client_filter``
    The report embeds a compact, normalized data payload. Browser JavaScript
    filters or aggregates that payload, then updates the component. This is
    appropriate for tables, KPIs, and moderate-sized Plotly datasets.

``precomputed_views``
    The report generator pre-renders a finite set of component views, indexed by
    state values. Browser JavaScript swaps the currently visible view. This is
    appropriate when the plotting logic is difficult to reproduce in JavaScript
    but the number of possible views is small.

For example, a CheckV component may include Plotly traces for all samples and
use Plotly.react to display the trace subset for the selected ``sample_id``.
A vOTU annotation component may instead include one pre-rendered panel per vOTU
when the number of vOTUs is small.

Large all-by-all combinations must not be pre-rendered. If a report has SS
samples and VV vOTUs, pre-rendering every sample-by-vOTU view has S×V
views and will quickly create impractically large HTML files.

Plugins should choose the smallest practical update strategy. The plugin
interface should hide this implementation detail from the layout system.


Layout Primitive Vocabulary
---------------------------

The first implementation should support a small, explicit layout vocabulary.

``component``
   Reference a component registered by a plugin.

``state_control``
   Render a selector or other input control for a declared report-state
   variable.

``stack``
   Render children vertically.

``row``
   Render children horizontally using flexbox or CSS grid.

``grid``
   Render children in a configurable CSS grid.

``group``
   Render a titled and optionally described group.

``tabs``
   Render a tabbed group. Top-level tabs may initially be handled separately.

``notice``
   Render a static informational, warning, or error message.

``markdown``
   Render trusted static markdown content.

``conditional``
   Render children only when a supported condition is true.

``divider``
   Render a visual separator.

Avoid using layout configuration as an arbitrary HTML abstraction. The layout DSL
should remain small, documented, validated, and styleable.

Missing Component Behavior
--------------------------

A component reference may be unresolved because:

* The corresponding analysis was not run.
* A required artifact was missing.
* A plugin was disabled.
* The plugin is not installed.
* The component was renamed.
* The component has no data for the currently selected state.


The layout should explicitly state the desired behavior.

.. code-block:: yaml

   - type: component
     ref: checkv.summary
     on_missing: placeholder

Supported policies should include:

``hide``
   Do not render the component or its empty container.

``placeholder``
   Render an informative unavailable-state card.

``warning``
   Hide the component but record a warning in a report-level diagnostics area.

``error``
   Fail report generation because this component is required for the selected
   layout.

``on_missing`` applies to report-build-time component availability. For example,
it applies when CheckV was not run and the checkv.summary component cannot
be built.

A component that is available at build time but has no data for a particular
current state must normally render its own empty-state message. For example:

.. code-block:: text

    No CheckV-quality records are available for sample ERR2867948.

This distinction prevents the layout tree from changing unexpectedly whenever a
user changes a selector.

Conditional Layout
------------------

Conditional layout support should be intentionally constrained.

Recommended supported conditions:

.. code-block:: yaml

   - type: conditional
     when:
       component_available: ordination.bray_curtis
     children:
       - type: component
         ref: ordination.bray_curtis

.. code-block:: yaml

   - type: conditional
     when:
       state_defined: sample_id
     children:
       - type: component
         ref: overview.kpis
       - type: state_control
         ref: sample_id

.. code-block:: yaml

   - type: conditional
     when:
       artifact_available: virmake.relative_abundance
     children:
       - type: component
         ref: taxonomy.relative_abundance

Do not allow arbitrary Python expressions in configuration.

Avoid configurations such as:

.. code-block:: yaml

   # Unsupported and unsafe.
   when: "len(samples) > 2 and config['enable_ordination']"

Layout Validation
-----------------

Layout validation should occur in two stages.

Static validation
^^^^^^^^^^^^^^^^^

Static validation verifies configuration syntax and structural validity.

Examples:

* All tabs have unique IDs.
* Supported node types are used.
* A grid has at least one column.
* A component node contains a ``ref``.
* A group has a title.
* An ``on_missing`` policy is valid.
* A state variable has a unique id.
* A ``state_control`` node references a declared state variable.
* A component bind mapping has valid key-value structure.

Runtime validation
^^^^^^^^^^^^^^^^^^

Runtime validation occurs after plugins have registered their components.

Examples:

* Detect references to unknown component IDs.
* Detect components unavailable due to absent artifacts.
* Detect duplicate component IDs.
* Detect references to state variables unavailable because their source artifact

Example diagnostic:

.. code-block:: text

   Warning: Layout references unknown component:
     functional.kegg_summary

   Available components:
     - annotation.genome_summary
     - checkv.summary
     - overview.kpis
     - ordination.bray_curtis
     - taxonomy.relative_abundance

The severity should be configurable.

.. code-block:: yaml

   settings:
     unknown_component: warning
     unavailable_component: hide

For stricter production or CI environments:

.. code-block:: yaml

   settings:
     unknown_component: error
     unavailable_component: error
