Generic Jinja Rendering
=======================

The base Jinja template should only render general report concepts:

* HTML document structure.
* Header and footer.
* Tab navigation.
* Shared assets.
* A recursive layout tree.

It should not render analysis-specific variables directly.

Avoid:

.. code-block:: jinja

   {{ checkv_plot | safe }}
   {{ taxonomy_plot | safe }}
   {{ genome_annotation_plot | safe }}

Prefer:

.. code-block:: jinja

   {% for tab in tabs %}
   <section
       id="{{ tab.id }}-panel"
       class="tab-panel {% if loop.first %}active{% endif %}"
       role="tabpanel"
       aria-labelledby="{{ tab.id }}-tab"
       {% if not loop.first %}hidden{% endif %}
   >
       {{ layout.render_node(tab.layout) }}
   </section>
   {% endfor %}

Recursive Layout Macro
----------------------

A generic Jinja macro can render configured layout nodes.

.. code-block:: jinja

   {% macro render_node(node) %}

       {% if node.type == "component" %}
           <article
               class="report-component report-component--{{ node.component.kind }}
                      {{ node.class_name or '' }}"
           >
               {% if node.component.title %}
               <header class="report-component__header">
                   <h2>{{ node.component.title }}</h2>
               </header>
               {% endif %}

               <div class="report-component__content">
                   {{ node.component.html | safe }}
               </div>
           </article>

       {% elif node.type == "stack" %}
           <div class="layout-stack {{ node.class_name or '' }}">
               {% for child in node.children %}
                   {{ render_node(child) }}
               {% endfor %}
           </div>

       {% elif node.type == "row" %}
           <div class="layout-row {{ node.class_name or '' }}">
               {% for child in node.children %}
                   {{ render_node(child) }}
               {% endfor %}
           </div>

       {% elif node.type == "grid" %}
           <div
               class="layout-grid {{ node.class_name or '' }}"
               style="--grid-columns: {{ node.columns }};"
           >
               {% for child in node.children %}
                   {{ render_node(child) }}
               {% endfor %}
           </div>

       {% elif node.type == "group" %}
           <section class="report-group">
               <header class="report-group__header">
                   <h2>{{ node.title }}</h2>

                   {% if node.description %}
                   <p>{{ node.description }}</p>
                   {% endif %}
               </header>

               {% for child in node.children %}
                   {{ render_node(child) }}
               {% endfor %}
           </section>

       {% endif %}

   {% endmacro %}

Component Rendering
-------------------

There are two supported strategies for component content.

Pre-rendered HTML
^^^^^^^^^^^^^^^^^

A plugin returns trusted HTML:

.. code-block:: python

   ReportComponent(
       id="ordination.bray_curtis",
       title="Bray-Curtis sample ordination",
       kind="plot",
       html=figure.to_html(
           full_html=False,
           include_plotlyjs=False,
           config={"responsive": True},
       ),
   )

This is suitable for Plotly-generated fragments and internal trusted templates.

Template plus context
^^^^^^^^^^^^^^^^^^^^^

A plugin returns a component template path and a context dictionary.

.. code-block:: python

   @dataclass
   class ReportComponent:
       id: str
       title: str | None
       kind: str
       template: str
       context: dict[str, Any]
       available: bool = True

Example:

.. code-block:: python

   ReportComponent(
       id="overview.kpis",
       title=None,
       kind="kpi_grid",
       template="components/kpi_grid.html.jinja",
       context={"kpis": kpis},
   )

The report builder renders this component through a trusted Jinja environment
before inserting it into the generic layout.

The template-plus-context approach is preferred for reusable non-Plotly report
components such as KPI grids, tables, notices, and metadata blocks.


Theming
-------

Reports are themed through *design tokens*: a small, validated set of
semantic color values that is the single source of truth for every
visual element of a report — page CSS, plugin-generated figures, and
report JavaScript.  All colors are decided at report build time: the
generated HTML is deterministic, and theming is testable in Python
without a browser.

A theme consists of:

* ``name``: the theme's human-readable name.
* ``colors``: a mapping of semantic tokens to ``#rrggbb`` colors.  Every
  theme must provide the core tokens:

  ``background``, ``surface``, ``text``, ``muted``, ``border``,
  ``primary``, ``accent``, ``success``, ``warning``, ``danger``

  Themes may declare additional tokens beyond the core set.
* ``series``: an ordered categorical palette of at least two colors, for
  plots and other repeated-color contexts.

Tokens are lowercase kebab-case words.  The theme model is strict and
frozen, like the manifest models: unknown structure and malformed colors
fail validation, and a theme file that fails validation surfaces as a
typed framework error at build time rather than a silently degraded
report.  Typography, spacing, and layout are not theme tokens; they
remain the responsibility of ``report.css``.

Example theme file:

.. code-block:: yaml

   name: default
   colors:
     background: "#ffffff"
     surface: "#f5f7fa"
     text: "#212529"
     muted: "#6c757d"
     border: "#dee2e6"
     primary: "#0d6efd"
     accent: "#6610f2"
     success: "#198754"
     warning: "#ffc107"
     danger: "#dc3545"
   series:
     - "#0d6efd"
     - "#d63384"
     - "#fd7e14"
     - "#20c997"
     - "#6610f2"

The theme is injected at two places, both at build time:

1. **CSS.**  The report template emits the theme as CSS custom properties
   in a single ``:root`` block.  Token ``x`` becomes ``--wc-x``; the
   series palette becomes ``--wc-series-1``, ``--wc-series-2``, ... with
   as many variables as the palette has colors.  The ``--wc-`` prefix
   avoids collisions with properties contributed by plugins or the
   hosting page.

   .. code-block:: css

      :root {
        --wc-background: #ffffff;
        --wc-surface: #f5f7fa;
        /* ... */
        --wc-series-1: #0d6efd;
        --wc-series-2: #d63384;
      }

   ``report.css`` references these custom properties exclusively and
   contains no color literals.  Swapping a theme therefore restyles the
   entire report without any CSS modification.

2. **Plugins.**  The render context exposes the theme to every plugin, so
   generated figures share the report's appearance:

   .. code-block:: python

      def render(self, context, parameters):
          figure.update_layout(
              colorway=list(context.theme.series),
              font={"color": context.theme.colors["text"]},
              paper_bgcolor=context.theme.colors["surface"],
          )

Division of responsibility:

* *Theme authors extend* the token set.  ``report.css`` and plugins may
  use non-core tokens opportunistically when the active theme provides
  them.
* *Plugins consume* the core tokens and the series palette.  Plugins
  never declare tokens of their own, and never hard-code colors.

This keeps themes and plugins orthogonal: a plugin renders correctly
against any theme, and a theme restyles any plugin's output.

Theme selection happens at build time.  The framework ships a built-in
``default`` theme; selecting a custom theme file via the CLI is a planned
feature of the CLI milestone.

Dark mode is an explicit non-goal for the current milestones.  The token
architecture does not preclude it — a dark palette could later be added
as a second token set applied via a ``[data-theme]`` attribute or
``prefers-color-scheme``, without changes to the plugin contract.  The
non-goal is recorded here so that partial support is not added
piecemeal before that decision.
