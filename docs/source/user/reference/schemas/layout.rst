=============
Report layout
=============

The layout is a YAML file describing report identity and an ordered
list of tabs. Tabs contain component placements and composition nodes.
Its schema version is independent of the
:doc:`manifest <manifest>` version.

Identity
--------

.. list-table::
   :header-rows: 1

   * - Key
     - Required
     - Shape and meaning
   * - ``schema_version``
     - yes
     - The literal ``"0.3.0"``.
   * - ``title``
     - yes
     - Visible text displayed in the page header.
   * - ``subtitle``
     - no
     - Visible text displayed under the title.
   * - ``author``
     - no
     - Visible text displayed in the footer.
   * - ``version``
     - no
     - Visible report revision displayed in the header.
   * - ``theme``
     - no
     - Path to a :doc:`theme <theme>` file, relative to the layout.
       Omission uses the built-in theme and records a diagnostic.
   * - ``logo``
     - no
     - Relative image path or bundled icon name. Omission renders
       without a logo and records a diagnostic.
   * - ``favicon``
     - no
     - Relative image path. Omission renders without a favicon and
       records a diagnostic.
   * - ``header_variant``
     - no
     - ``fill`` (default) or ``gradient``. Selects a solid or
       two-color gradient header background.
   * - ``header_color``
     - no
     - For ``fill``, a theme color token or ``series-N`` entry;
       omission uses ``primary``. For ``gradient``, a required
       two-entry list of color references. Declared references must
       resolve against the report's theme.
   * - ``on_missing``
     - no
     - ``fail`` (default), ``notice``, or ``skip``: the layout-wide
       policy for an unresolved component.
   * - ``on_unavailable``
     - no
     - ``notice`` (default), ``skip``, or ``fail``: the layout-wide
       policy for an unavailable component outcome.
   * - ``tabs``
     - yes
     - A non-empty list of tabs, in display order.


Declared theme, logo, and favicon files must load. Assets are embedded
at build time; the written report is self-contained. Header text color
is selected for contrast against the header background.

Header styling
--------------

The header uses a token declared in the report's :doc:`theme <theme>`,
such as ``primary`` or ``accent``, or a categorical palette entry
such as ``series-1``. Series indices start at 1 and must be within the
theme's palette. Color literals are not accepted in the layout;
declare them in the theme and reference their tokens.

By default, the header has a solid ``primary`` background. To choose
another solid color:

.. code-block:: yaml

   header_color: accent

``header_variant: fill`` may be written explicitly, but is the
default. Omitted or ``null`` ``header_color`` uses ``primary`` and
does not produce an omission diagnostic.

A gradient requires ``header_variant: gradient`` and exactly two
color references, in written order:

.. code-block:: yaml

   header_variant: gradient
   header_color: [primary, accent]

Token and series references may be mixed:

.. code-block:: yaml

   header_variant: gradient
   header_color: [primary, series-2]

A single color or omitted color is invalid for
``gradient``; a color list is invalid for ``fill``.
Header ink is selected from the theme's ``text-light`` and
``text-dark`` colors. For a solid background, selection compares
contrast against that color. For a gradient, it compares contrast
against the mean relative luminance of both stops. This is a
heuristic, not a guarantee of sufficient contrast at every point
along the gradient.

A theme-declared ``header-background`` token overrides the requested
header background, including a gradient, with its solid color. Ink
is then selected against that effective background. A theme-declared
``header-text`` token overrides the selected ink independently.
Declared layout color references must still resolve, even when a
theme override takes precedence.

Tabs and placements
-------------------

A tab has a ``title`` and a non-empty ``components`` list. A report
with one tab renders no tab bar.

A node with ``id`` is a placement; a node with ``type`` is a
composition. A node with both or neither is invalid.

.. list-table::
   :header-rows: 1

   * - Placement key
     - Required
     - Shape and meaning
   * - ``id``
     - yes
     - Component id: ``<plugin_id>.<component_name>``.
   * - ``title``
     - no
     - Visible text overriding the component's default title.
   * - ``parameters``
     - no
     - Object, default ``{}``. Its keys and JSON-compatible values
       belong to the component.
   * - ``on_missing``
     - no
     - Per-placement override of the layout policy.
   * - ``on_unavailable``
     - no
     - Per-placement override of the layout policy.

Composition nodes
-----------------

Composition nodes may nest. Their children use the same placement and
composition grammar as a tab's ``components`` list.

.. list-table::
   :header-rows: 1

   * - ``type``
     - Other keys
     - Meaning
   * - ``row``
     - ``children``; optional ``split``
     - Non-empty children displayed side by side.
   * - ``grid``
     - ``children``; required ``split``
     - Non-empty children flowing row-major into columns.
   * - ``card``
     - ``children``; optional ``title``, ``layout``, ``split``
     - A titled grouping. ``layout`` is ``stack`` (default), ``row``,
       or ``grid``. A stack rejects ``split``.
   * - ``diagnostics``
     - none
     - Places the report's complete diagnostics ledger.
   * - ``states``
     - ``dimension``, ``children``; optional ``kind``, ``values``
     - Expands its children for each value of an axis.

``split`` is a list of at least two positive numeric ratios. A row
takes one ratio per child; without ``split``, its children have equal
widths. A grid requires column ratios. Booleans and non-positive
values are rejected.

States
------

.. list-table::
   :header-rows: 1

   * - Key
     - Required
     - Shape and meaning
   * - ``type``
     - yes
     - The literal ``states``.
   * - ``dimension``
     - yes
     - Name matching ``[a-z][a-z0-9_-]*``. It is both the placeholder
       name and the report-wide selection key.
   * - ``kind``
     - no
     - ``categorical`` (default) or ``ordered``. Kind is declared,
       not inferred from labels.
   * - ``values``
     - no
     - Non-empty list of unique visible-text strings, in written
       order. Omitted or ``null`` derives values from distinct full
       manifest artifact types in declaration order.
   * - ``children``
     - yes
     - Non-empty list of nodes expanded for each value.

Unknown states keys are rejected. Derivation uses declarations, not
file discovery or availability, and includes non-``complete``
artifacts. A declared empty list fails validation; an empty derived
axis collapses at build time with an informational diagnostic.

Expansion
~~~~~~~~~

For each value, ``{dimension}`` substitutes the raw value verbatim in:

* Placement titles and strings within parameters, including mapping
  keys and nested values.
* Card titles.
* Nested states nodes' declared values and template children.

Numbers, booleans, and null remain unchanged. Placement ids, policies,
splits, dimension names, and kinds remain literal. If expanded
parameter keys collide, the later mapping assignment wins.

Nested outer placeholders substitute before inner expansion. If a
nested node reuses an outer dimension name, the outer expansion has
already replaced that placeholder throughout the subtree.

A malformed placeholder or an unbound name raises an expansion error.
Only an opening ``{`` starts a placeholder; a lone ``}`` is literal.
There is no escape for a literal opening brace in templated strings.
Valid ``{{ variable }}`` expressions in string-valued
``core.markdown.text`` are opaque to states expansion; the markdown
component resolves them instead.

Each expanded placement follows the ordinary resolution and
unavailable-data policies. Empty panels and states nodes collapse
upward through enclosing compositions and tabs. Diagnostics markers
repeat with the template but each displays the complete build ledger.

All surviving states are embedded in the report. Expansion therefore
increases build work and HTML size; nested axes can multiply the
number of instances. Read-time controls select visibility, not build
work. See :doc:`selection-fragments` for selection and degradation.

YAML authoring and loading
--------------------------

* Text fields require visible text; whitespace-only text is rejected.
* Duplicate mapping keys are rejected, with the key and line reported.
* YAML booleans are booleans: quote words such as ``"no"`` where a
  string is intended.
* Unknown model keys are rejected.
* An opening brace outside states is rejected in placement titles,
  parameters, and card titles, except for valid markdown variables in
  string-valued ``core.markdown.text``.
* Report identity strings and tab titles cannot be bound by states.
  Placement ids cannot contain placeholders.
* Theme, logo, and favicon paths are resolution strings, not states
  templates.

Layouts at versions ``0.1.0`` and ``0.2.0`` are not read. To migrate
``0.1.0``, rename ``sections`` to ``tabs`` and remove ``toc``.
Version ``0.2.0`` is otherwise current: set ``schema_version`` to
``"0.3.0"``. See the
:doc:`layout loader API <../framework/api/layout_loader>`.

Example
-------

.. code-block:: yaml

   schema_version: "0.3.0"
   title: Run summary
   header_variant: gradient
   header_color: [primary, accent]
   tabs:
     - title: Headlines
       components:
         - id: core.kpi
           title: Mean depth
           parameters:
             artifact: org.example.sample_metrics
             key: depth
             unit: x
         - type: diagnostics
