============================
workflow-coda documentation
============================

``workflow-coda`` is a framework for building portable, configurable static
HTML reports from workflow outputs.

It is designed primarily for scientific and bioinformatics workflow developers,
but it is not tied to a specific workflow engine, pipeline, analysis domain, or
artifact format.

A workflow integration supplies a report manifest and report-ready artifacts.
The framework discovers plugins, validates the layout, composes registered
components, and renders a portable static HTML report.

New here?  Start with the :doc:`tutorials </user/tutorials/index>`:

1. A minimal report from scratch: the
   :doc:`"hello world" report </user/tutorials/hello-report>`.
2. Extending it with a custom component through a minimal
   plugin: :doc:`your first plugin </user/tutorials/first-plugin>`.


.. toctree::
   :maxdepth: 2
   :caption: Tutorials

   user/tutorials/index

.. toctree::
   :maxdepth: 2
   :caption: How-to guides

   user/how-to/index

.. toctree::
   :maxdepth: 1
   :caption: Explanation

   user/explanation/index

.. toctree::
   :maxdepth: 3
   :caption: Reference

   user/reference/index
