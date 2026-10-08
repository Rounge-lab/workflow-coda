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
