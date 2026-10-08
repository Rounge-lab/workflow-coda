Architecture Overview
=====================

The system is divided into four conceptual layers. The first layer belongs
to the workflow or analysis integration and defines the stable interface between
the workflow manager and the reporting framework. The remaining layers are
provided by the standalone report framework and its installed plugins and are
responsible for report component generation, defining the composable layout, and
rendering the static HTML report.

.. code-block:: text

   Workflow manager
                 |
                 v
   Report Interface
   +----------------------------+
   | Report manifest            |
   | Artifact declarations      |
   | Provenance metadata        |
   +-------------+--------------+
                 |
                 v
   Framework Layers
   +----------------------------+
   | Artifact store             |
   | Plugin discovery           |
   | Components and diagnostics |
   +-------------+--------------+
                 |
                 v
   +----------------------------+
   | Layout configuration       |
   | Tabs, grids, state, rules  |
   +-------------+--------------+
                 |
                 v
   +----------------------------+
   | Generic HTML renderer      |
   | Static HTML or report bundle|
   +----------------------------+

The framework receives only the manifest, declared artifacts, configuration,
and installed plugins. It does not need to know which workflow engine produced
the data.
