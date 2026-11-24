==================
Developing plugins
==================

The first-plugin tutorial ended with one component and one figure.  This guide
covers the rest of the plugin author's craft: the full declaration surface,
reading artifacts properly, the complete outcome vocabulary, making content
native to any theme, page chrome, icons, and testing.  Every contract named here
is documented in full in the :doc:`reference documentation <../reference/index>`
. This page says when to reach for each piece, and why.

The full declaration surface
-----------------------------

A plugin is one value — metadata plus components, assembled
by ``get_plugin`` and registered by the entry point the tutorial
showed.  A component declaration can carry much more than that
tutorial needed:

.. code-block:: python

   from workflow_coda.components import (
       ComponentChrome,
       ReportComponent,
   )

   ReportComponent(
       id="mine.plate",
       title="Plate",
       description="A titled plate of key-value rows.",
       render=render_plate,
       chrome=ComponentChrome.TILE,
       css=PLATE_CSS,
       js=PLATE_JS,
   )

Everything is validated when the value is constructed: ids must be
``<plugin_id>.<name>`` in lowercase snake_case, titles must be
visible text, css and js must be non-blank and free of the
block-breaking sequences (below).  Two plugins claiming the same
id fail at discovery, with both named — long before a report is
built.  The full field list lives in
:doc:`../reference/framework/api/components`; the plugin value and
its integrity rules in :doc:`../reference/framework/api/plugins`.

Reading artifacts: the store is the only door
---------------------------------------------

Plugins never touch the filesystem.  ``context.store.require()``
resolves a declared artifact by type and returns a handle with
three readers: ``read_json()``, ``read_text()``, and
``read_bytes()`` — the last two for formats your plugin parses
itself (a table with your own parser, an image).

What you get without asking: paths are contained within the
manifest's directory, a declared checksum is verified over the
exact bytes you read, text is strict UTF-8, and only artifacts
with ``status: complete`` resolve at all.  What you own: the
*content*.  JSON syntax is checked; meaning is not — validate the
document against what your component documents and raise a
teaching error when it breaks (the style is below).

And the tutorial's split holds everywhere: ``require`` raising
:exc:`~workflow_coda.errors.ArtifactUnavailableError` is a missing
*artifact* — catch it, return ``unavailable``, let the store's
message ride (it already lists what the manifest declares).  The
reading API: :doc:`../reference/framework/api/artifact_store`.

The complete outcome vocabulary
-------------------------------

Three statuses, one extra channel.  ``ok`` carries html;
``unavailable`` carries a message and renders as a notice;
``skipped`` renders nothing.  And an ``ok`` outcome may carry
*notes* — facts you noticed about the data while rendering, for
the reader rather than the author:

.. code-block:: python

   from workflow_coda.components import ComponentStatus, RenderedComponent

   return RenderedComponent(
       status=ComponentStatus.OK,
       html=plate_html,
       notes=(
           "The palette wrapped at 12 groups: the last two groups "
           "reuse the first two series colors",
       ),
   )

Notes ride the report's diagnostics ledger as informational
entries — the same panel the author places with the diagnostics
marker.  Use them for what you would say out loud about the data:
a suspicious range, a wraparound, a near-miss threshold.

Raising is the fourth channel, and the builder draws the line for
you: any ``Exception`` from your render call is caught, recorded
as a plugin bug, and rendered as a failure card quoting your error
verbatim — your bug never crashes someone's report.  Control-flow
exceptions (``KeyboardInterrupt``) pass through untouched, as they
should.

Figures go through ``from_figure``
----------------------------------

Never hand-roll figure html.  ``RenderedComponent.from_figure()``
is the channel: it embeds the plot as a bare div (the card owns
the chrome), marks it with the framework's figure class — the
marker the renderer keys on to inline Plotly.js *exactly once per
report* — configures it responsive, and keeps the page one
self-contained file.  Hand-rolled html skips all four, and the
first three silently: the marker is what makes the plot work at
all.

The ``description`` argument is the figure's accessibility label —
what a screen reader announces instead of the plot's graphics.
It does not appear in the page.  Write one for every figure you
ship; for components shipped with ``workflow-coda`` itself it is
required, and it costs one line.

Colors: adopt both theme modes
------------------------------

``context.theme`` is a ``ThemePair``. Its ``light`` and ``dark``
members are individual ``Theme`` values.

For HTML-based components, use validated CSS references:

.. code-block:: python

   from workflow_coda.theme import color_css

   bar = color_css(context.theme, "mine.plate", "series-3")

The result is ``var(--coda-series-3)``. Both members are validated,
and the browser resolves the reference against the active palette.
Use the same approach for parameter-selected color tokens rather
than embedding a hexadecimal value from one member.

For fixed framework tokens, component CSS can refer directly to
properties such as ``var(--coda-surface)`` and
``var(--coda-text)``. For contrast-selected ink on colored plates,
use the mode-aware ink helpers documented in the
:doc:`theme API <../reference/framework/api/theme>`.

When constructing styling for one mode, use its individual theme:

.. code-block:: python

   theme = context.theme.light
   ink = theme.text_on(theme.colors["surface"])
   bar = theme.resolve_color("mine.plate", "series-3")

These values describe light-mode styling only. They do not
automatically update when the reader switches modes.

To make a Plotly figure follow theme mode changes through the framework's
figure channel, pass paired updates to ``from_figure``:

.. code-block:: python

   from workflow_coda.theme import FigureTheme

   binding = FigureTheme(
       light=figure_style(context.theme.light),
       dark=figure_style(context.theme.dark),
   )
   return RenderedComponent.from_figure(
       figure,
       description=description,
       theme=binding,
   )

Here, ``figure_style`` is your own helper returning a ``FigureStyle``
for one mode. Construct the initial figure once, then describe the
updates separately. The waterfall tutorial demonstrates this pattern
for a trace type that the core chart component does not provide.

The framework does not choose your Plotly fields or presentation
policy. Prefer appearance-only updates: avoid duplicating artifact
data or resetting the reader's zoom when changing modes. Omitting
the binding leaves the figure's initial presentation unchanged.

See the :doc:`theme API <../reference/framework/api/theme>` for the
update contracts and the
:doc:`components API <../reference/framework/api/components>` for
embedding and initialization requirements.

A pair may declare extra tokens beyond the required core set.
Declare the same extra tokens in both members and document those
your component expects. Validated resolution names your component
and the offending mode when a reference cannot resolve.

Page chrome: css and js
-----------------------

A component's optional ``css`` and ``js`` declarations are inlined
into the report — once per report, only when at least one of its
placements rendered ``ok``, in first-use order, each under your
component's id banner.  The css lands immediately after the
framework's stylesheet; the js lands after the framework's own
scripts, so the DOM exists when your code runs.

Three laws keep every report coherent:

* **Namespace.**  Your rules name ``coda-<plugin_id>-*`` — bare
  ``coda-*`` belongs to the framework.  A reader can tell your
  chrome from the framework's at a glance, and the two can never
  collide.
* **Script enhances, never gates.**  A reader with JavaScript off
  sees the complete document.  If your component must react to
  tab activation, subscribe to the ``coda:tab-shown`` event —
  dispatched on the shown panel, bubbling to document — rather
  than reaching into the panels.
* **Self-containment.**  The page's Content-Security-Policy
  blocks every network request at read time: your css loads
  nothing external, and your js makes no network calls.

Two sequences are rejected at declaration time — ``'</style'`` in
css, ``'</script'`` in js — because either would terminate the
inline block early and break the page.  If one appears inside a
string you genuinely need, the error teaches the escape
(``<\\/script`` and its sibling).

Icons
-----

Ship icons by declaring the package that carries them:

.. code-block:: python

   metadata=PluginMetadata(
       id="mine",
       # ...name, version, description, supported_schema_versions...
       icons_package="mine_reports",
   )

The build then reads ``assets/icons/`` inside that package, where
each icon is an SVG named ``<plugin_id>-<name>.svg``.  Every SVG —
shipped or user-authored — crosses the same deny-by-default
validator: only allowlisted elements survive, and an offender (a
``<text>`` element, say) fails the build by name.  Author icons
with ``fill="currentColor"`` and they follow the ink of whatever
they sit on.

Components can accept icon names as parameters — the shipped KPI
component's icon parameter is the pattern — and any shipped icon
can serve as a report's logo by name.  The vocabulary:
:doc:`../reference/framework/api/icons`.

TILE mode: painting your own card
---------------------------------

By default (``chrome=ComponentChrome.CARD``) you return body html
and the framework wraps it in the shared card and renders the
resolved title as its heading.  With ``chrome=TILE`` you painted
the whole card — title, plate, corners — and the framework
contributes only the ``data-component`` wrapper.

Degradation is mode-independent: an unavailable TILE outcome
renders the framework's notice card, with the resolved title you
never got to paint.  Choose TILE for dense visual tiles; choose
CARD for everything else.  Page chrome (above) is available in
both modes.

Schema gating
-------------

``supported_schema_versions`` is your plugin's compatibility gate:
a non-empty frozenset of manifest versions it understands —
currently ``{"0.3.0"}``.  At build time the framework checks it
against the manifest's own ``schema_version``: a plugin outside
the gate is excluded from the report and the diagnostics ledger
records why, naming both versions.  Keep the set deliberate —
when a new manifest version ships, that is the moment to decide
whether your plugin supports it.

Teaching errors: the house style
--------------------------------

The framework's error messages are its best documentation, and
your component's errors are part of its documentation too.  Four
habits, straight from the framework's own messages:

* **Name the requester.**  ``resolve_color``'s first argument
  exists so every teaching points at the component that asked.
* **List the vocabulary.**  The store names what the manifest
  does declare; the registry names the components that are
  available; ``resolve_color`` names the theme's tokens.
* **Suggest the fix.**  Unknown parameters get a closest-match
  hint — ``did you mean 'unit'?``.
* **Name the move.**  A placement key nested inside
  ``parameters:`` teaches where it belongs: out, next to ``id``.

``reject_unknown_parameters`` gives you the first three for free
— call it first thing in your render, with your component's
closed parameter vocabulary, and typos become one-line fixes
instead of silent misconfigurations.

Testing a plugin
----------------

The framework's own suites follow a pattern that ports directly
to plugin packages:

* **Construct real values.**  Build the real ``ReportPlugin`` in
  tests — construction itself runs every declaration check you
  want covered.
* **Call renders directly.**  A real
  :class:`~workflow_coda.context.RenderContext` over a real
  :class:`~workflow_coda.artifact_store.ArtifactStore` with
  artifact files on disk, a ``PlacementInfo``, and a parameters
  mapping.  Assert on the returned ``RenderedComponent`` — its
  status, its html, its notes — and on raised teachings with
  ``pytest.raises``.
* **Integrate through the builder.**
  ``build_report(layout, store, PluginRegistry((get_plugin(),)))``
  exercises resolution, policies, and collection end to end;
  assert on the built document or the rendered page.
* **Simulate missing dependencies faithfully.**  Halting an
  import in-process (a ``None`` entry in ``sys.modules``) is
  defeated by cached submodules — purge every cached
  ``plotly.*`` entry first, then halt the top-level name;
  ``monkeypatch`` restores them at teardown.
* **Test the bug boundary.**  A render that raises must become a
  failed entry and a ``plugin_bug`` diagnostic, never a crash;
  ``KeyboardInterrupt`` must pass through.  If you add your own
  guards, pin both.
* **Test both theme modes.**  Construct a real ``ThemePair``. Check CSS
  references or both figure styling bindings, not hexadecimal
  occurrences across the entire generated HTML: paired metadata
  legitimately contains colors for both modes.

Where next
----------

* The contracts in full:
  :doc:`../reference/framework/api/components` (the render call,
  outcomes, chrome modes, page chrome),
  :doc:`../reference/framework/api/plugins` and
  :doc:`../reference/framework/api/registry` (the value and its
  discovery),
  :doc:`../reference/framework/api/artifact_store` and
  :doc:`../reference/framework/api/context` (the reading API),
  :doc:`../reference/framework/api/theme` (the color grammar),
  :doc:`../reference/framework/api/icons` (the icon door).
* The components workflow-coda ships — study material, and your
  report authors' toolbox: :doc:`../reference/core/index`.
* The other side of the report:
  :doc:`report-authoring`.
