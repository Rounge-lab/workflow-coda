==============
Bundled themes
==============

These theme declarations ship with workflow-coda. Each selection
identifier is the declaration's YAML filename stem; its display name
may differ.

A layout selects one declaration for each appearance mode:

.. code-block:: yaml

   theme:
     light: default
     dark: default-dark

The previews below use identical illustrative content and the
renderer's default solid-header derivations. They show palette,
typography, semantic colors, and every categorical series entry.
They are not exact rendered reports: installed fonts, layout choices,
and component presentation may differ.

Swatches list declared tokens and series values in their original
order. Preview ink and header properties also include the renderer's
derivations and any declared overrides.

See the :doc:`theme schema <schemas/theme>` for custom declarations,
selection rules, and pair compatibility.

.. bundled-themes::
