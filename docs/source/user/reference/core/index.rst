============
Core plugins
============

The ``core`` plugin is workflow-coda's own component roster: the
generally useful, field-agnostic components that ship with the
framework itself.  It is a plugin like any other — discovered through
the same entry-point group, gated by the same schema contract,
declared through the same
:py:class:`~workflow_coda.plugins.ReportPlugin` API — which makes it
the reference instance of the plugin pattern: what ``core`` does is
exactly what a third-party plugin may do.

Identity
--------

* **Plugin id:** ``core``
* **Name:** ``Core report components``
* **Description:** generally useful report components shipped with
  workflow-coda — headline metrics, and more as the core grows.
* **Version:** the framework's own version, read from the installed
  package metadata, so ``pyproject.toml`` stays the single source of
  truth.
* **Loading:** the registry loads the plugin through its
  ``get_plugin()`` entry point.
* **Components:** ``core.kpi`` today; the roster grows with the
  framework.

Schema gating
-------------

The plugin declares the manifest schema versions it supports — today, 0.2.0, the
current manifest schema version, which carries namespaced plugin artifact
formats.  A manifest that declares a version outside the set gates the plugin
out entirely: its placements resolve to nothing under the layout's
``on_missing`` policy, and the report records a ``plugin_excluded`` diagnostic
that tells the story.

Page chrome
-----------

Core components may declare page chrome through the component
channel — the same contract third-party plugins use, so the
framework's own roster proves it.  ``core.kpi`` self-hosts its card
styles: the stylesheet inlines exactly once per report, exactly when
a KPI placement renders, so a report without KPI placements carries
no KPI styles at all.  Being the framework's own plugin, ``core``
owns the bare ``coda-*`` class names; third-party plugins namespace
theirs as ``coda-<plugin_id>-*``.

The component pages
-------------------

Every component page follows the same shape, so the roster reads as
a set: the component's identity, how to place it (including the two
placement gates), its parameter grammar (a closed vocabulary), its
semantics (variants, colors, policies), and its outcomes and page
chrome.

.. toctree::
   :maxdepth: 1

   kpi
   table
