=============
Report layout
=============

.. automodule:: workflow_coda.layout

Version and text types
----------------------

.. autodata:: workflow_coda.layout.LayoutSchemaVersion
   :no-value:

.. autodata:: workflow_coda.layout.VisibleText
   :no-value:

Placement policies
------------------

The layout grammar's two gates.  ``on_missing`` governs component
*resolution* — whether the environment offers the component at all —
and defaults to ``fail`` because a dead id is probably an authoring
mistake.  ``on_unavailable`` governs the *outcome* — the component
resolved and rendered, but the run produced no data for it — and
defaults to ``notice`` because missing data may be expected pipeline
behavior.  Each policy exists as a layout-level default with a
per-placement override.

.. autoclass:: workflow_coda.layout.MissingPolicy
   :members:
   :undoc-members:

.. autoclass:: workflow_coda.layout.UnavailablePolicy
   :members:
   :undoc-members:

Composition nodes
-----------------

.. autodata:: workflow_coda.layout.LayoutNode
   :no-value:

.. autoclass:: workflow_coda.layout.RowNode
   :members:
   :exclude-members: model_config

.. autoclass:: workflow_coda.layout.GridLayout
   :members:
   :exclude-members: model_config

.. autoclass:: workflow_coda.layout.CardNode
   :members:
   :exclude-members: model_config

.. autoclass:: workflow_coda.layout.DiagnosticsNode
   :members:
   :exclude-members: model_config

The placement
--------------

.. autoclass:: workflow_coda.layout.ComponentPlacement
   :members:
   :exclude-members: model_config

The layout
----------

.. autoclass:: workflow_coda.layout.ReportLayout
   :members:
   :exclude-members: model_config
