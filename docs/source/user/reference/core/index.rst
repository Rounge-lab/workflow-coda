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
  workflow-coda: headline metrics, tables, charts, prose, and
  notices.
* **Version:** the framework's own version, read from the installed
  package metadata, so ``pyproject.toml`` stays the single source of
  truth.
* **Loading:** the registry loads the plugin through its
  ``get_plugin()`` entry point.
* **Components:** ``core.kpi``, ``core.table``, ``core.chart``,
  ``core.markdown``, and ``core.notice`` today; the roster grows
  with the framework.
* **Icons:** ``core`` ships the built-in icon set — ``core-``
  prefixed SVGs under its own ``assets/icons/``, declared through
  the plugin's ``icons_package`` field and served through the
  report's icon library — so ``core.kpi``'s ``icon`` parameter
  addresses them by name (``core-arrow-up`` and friends).

Schema gating
-------------

The plugin declares the manifest schema versions it supports — today, 0.2.0, the
current manifest schema version, which carries namespaced plugin artifact
formats.  A manifest that declares a version outside the set gates the plugin
out entirely: its placements resolve to nothing under the layout's
``on_missing`` policy, and the report records a ``plugin_excluded`` diagnostic
that tells the story.

.. _core-placement-gates:

Placement gates
---------------

A placement in the layout's ``components`` list carries the
component id, an optional per-instance ``title``, and the
component's ``parameters``.  Two placement gates decide what
happens when things are absent — and both are placement keys,
siblings of ``id`` and ``title``, never parameters:

``on_missing``
    The resolution gate: does this environment offer the component at
    all?  An id that resolves to nothing (not installed, or the
    plugin gated out by the manifest's schema version) follows the
    policy — the default is ``fail``, because a dead id is probably
    an authoring mistake.  See
    :py:class:`~workflow_coda.layout.MissingPolicy`.

``on_unavailable``
    The outcome gate: the component resolved and rendered, but the
    run produced no data for it.  The default is ``notice``, because
    missing data may be expected pipeline behavior.  See
    :py:class:`~workflow_coda.layout.UnavailablePolicy`.

What counts as *no data* is each component's own story — every
component page's outcomes section tells it.  And a policy nested
inside ``parameters:`` is an unknown parameter key: every
component's closed parameter vocabulary teaches the move rather
than silently ignoring it.

Page chrome
-----------

Core components may declare page chrome through the component
channel — the same contract third-party plugins use, so the
framework's own roster proves it.  ``core.kpi`` self-hosts its
card stylesheet and declares no script: a KPI is static content.
``core.table`` self-hosts a stylesheet *and* an enhancement
script — the channel's first script consumer; the complete table
ships in the HTML, script or no script.  Each contribution inlines
once per report, exactly when at least one of the component's
placements renders ``ok``: contributions merge into one style
block after the framework stylesheet and one script block after
the framework's own scripts, each stamped with its component's
banner by the channel (``/* <id> */`` for css, ``// <id>`` for js)
— so a report without a component's healthy placements carries
none of its chrome at all.  The chrome itself ships as real files
under ``core/assets/`` and is read at import: a storage detail the
channel makes invisible to authors.  Being the framework's own
plugin, ``core`` owns the bare ``coda-*`` class names; third-party
plugins namespace theirs as ``coda-<plugin_id>-*``.
``core.chart`` declares neither: its body is a Plotly figure
through the framework's figure channel, and Plotly.js inlines
exactly when the document contains a figure — a report without
healthy chart placements carries none of it.
``core.markdown`` self-hosts a stylesheet and declares no script,
like the KPI — prose is static content — its rules scoped under
the ``coda-prose`` wrapper.
``core.notice`` self-hosts the prose stylesheet concatenated with
its own disclosure rules and declares no script either — the
collapse is native ``<details>``/``<summary>`` — scoped under the
``coda-notice`` classes.

The component pages
-------------------

Every component page follows the same shape, so the roster reads as
a set: the component's identity, how to place it, its parameter
grammar (a closed vocabulary), its semantics (variants, colors,
policies), and its outcomes and page chrome.  The two placement
gates every placement carries are shared by the whole roster —
described once, in `Placement gates`_ above.

.. toctree::
   :maxdepth: 1

   kpi
   table
   chart
   markdown
   notice
