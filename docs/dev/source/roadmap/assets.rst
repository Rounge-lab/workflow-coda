Static Asset Strategy
=====================

The report requires shared assets such as:

* CSS.
* JavaScript.
* Logo SVG.
* Favicon SVG.
* Plotly JavaScript.

Plotly should be included exactly once per report.

Plugin Plotly fragments should use:

.. code-block:: python

   figure.to_html(
       full_html=False,
       include_plotlyjs=False,
       config={"responsive": True},
   )

The base report template should include Plotly once, either through:

* A pinned local asset for offline and portable reports.
* A pinned CDN URL for smaller report files.
* An inlined Plotly bundle for a fully self-contained file.

For reproducible offline reports, a local pinned version is preferred.

``report.css`` contains no color literals.  All colors come from the
CSS custom properties that the report template emits from the active
theme (``--wc-*`` variables; see the Theming section of the rendering
page). This is what makes a theme swap restyle the entire report,
including plugin output, without any CSS edits. The bundled
``plotly.min.js`` likewise carries no theme awareness: figures are
styled by plugins through the render context before they are embedded.
