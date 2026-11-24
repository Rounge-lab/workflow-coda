=================
Your first plugin
=================

The "hello world" report placed ``core.kpi``, a component the
framework ships.  In this tutorial you will write your own! We'll walk through
building a plugin with one component that draws a Plotly waterfall chart. This
is a type of figure that ``workflow-coda`` does not ship.  Then you'll grow the
same report with your new component, and watch it gain its tab bar.

A plugin is a value, not a class hierarchy
------------------------------------------

A ``workflow-coda`` plugin is a small amount of data: who it is (*metadata*) and
what it offers (*components*), assembled by a zero-argument ``get_plugin``
function and registered with one line in your packaging.  There is no base class
and nothing to subclass.  This is the whole plugin package:

.. literalinclude:: ../../../examples/waterfall-plugin/pyproject.toml
   :language: toml
   :caption: pyproject.toml: the entry point is the plugin registration


``[project.entry-points."workflow_coda.plugins"]`` is the registration: the
group name ``workflow_coda.plugins`` is fixed, the name ``waterfall`` is yours
(it's your plugin's own id), and the value
``"waterfall_reports.plugin:get_plugin"`` points at your ``get_plugin``
function, which ``workflow-coda`` will use to load your plugin and its
components.  Every installed plugin is discovered automatically by
``workflow-coda`` at build time.  One note on dependencies: ``workflow-coda`` is
not listed here, pending release to ``PyPI``. This tutorial assumes you
already have it installed.

.. literalinclude:: ../../../examples/waterfall-plugin/waterfall_reports/plugin.py
   :language: python
   :caption: waterfall_reports/plugin.py: the plugin defining one component

The rest of this page walks through what that module is doing, and why.

The render contract
-------------------

Every ``workflow-coda`` component (see ``render_waterfall``) is a callable with
a fixed shape: it receives the render *context*, the placement's *info*, and the
placement's *parameters*, from the layout configuration, and returns one
``RenderedComponent``, which is the typed *outcome* that declares the content of
your component.

The context carries the report's data: ``context.store`` is where
``workflow-coda`` lets you get the verified data contained in artifacts declared
in ``manifest.json``, and ``context.theme``, declared in ``layout.yaml``, is the
report's resolved light/dark ``ThemePair``.  Its individual members provide the
palettes and fonts used to construct styling for each mode. Use those declared
colors rather than literals so the component fits bundled and custom themes,
that way the whole report will have a cohesive look, and it will be easy to
adjust theming options later. The ``info`` parameter carries the placement's
resolved title ``info.title``. In this example, the title is "Where the bases
went".  The parameters are your component's configuration, exactly as written in
``layout.yaml``.  The framework interprets none of them, so the component has to
validate its own parameters.

The return value carries a ``status`` that says what happened, so
``workflow-coda`` can render it honestly.  Three outcomes exist:

``ok``
   The component rendered as expected, and the return value carries
   valid html content.

``unavailable``
   Carries a message about missing data and doesn't carry html content. The
   component will then render as a neutral notice displaying the message.

``skipped``
   Renders nothing.

It may also be possible that the plugin component raised an exception. In this
case, nothing gets returned.  The distinction matters, so the two families
deserve their own section.

Missing data is a fact; bugs are bugs
-------------------------------------

Suppose the pipeline never wrote the waterfall artifact ``steps.json``. This
could be expected pipeline behavior if partial runs are allowed.  In this case,
the component cannot render anything, and the report should *say so* without
drama. In ``workflow-coda`` a 'not there' error becomes the message of an
``unavailable`` outcome:

.. code-block:: python

   try:
       artifact = context.store.require(artifact_type)
       data = artifact.read_json()
   except ArtifactUnavailableError as e:
       return RenderedComponent.unavailable(str(e))

If the artifact is missing, ``render_waterfall`` returns an unavailable
component. ``workflow-coda`` then handles this gracefully, based on the
``on_unavailable`` policy defined in ``layout.yaml`` (by default, a notice card
will be rendered with an explanatory message).

If at any point ``render_waterfall`` raises an unexpected error, for example
because of a bug in the component's code, ``workflow-coda`` will catch the error
and report it honestly as a plugin bug in a failure card. This is why
``_parse_steps`` raises instead of returning "unavailable"; it allows
``workflow-coda`` to distinguish between unavailability of the artifact (which
may be expected) and unexpected bugs that should be fixed by the plugin
developer.

Drawing the figure
------------------

There are two recommendations that are worth adopting to ensure your custom
plugin components look nice and work well within the ``workflow-coda``
framework. These are not enforced though, you are allowed to design your plugin
exactly as you wish.

*Import your heavy dependencies inside the render call.*  The import of
``plotly`` sits inside ``_waterfall_figure``. This way, building a report with a
layout that doesn't include the ``waterfall.plot`` component doesn't have to
load ``plotly`` even when the report author has installed your plugin. On the
other hand, a missing ``plotly`` install becomes a clear instruction from
``workflow-coda`` ("install plotly and build the report again") rather than a
crash.

*Take colors from the theme, never from literals.*  The bars use
``theme.resolve_color("waterfall.plot", "series-1")`` and ``"series-2"`` (the
first two colors of the themes ``series`` list) and the text color is picked for
optimal contrast against the card surface by ``theme.text_on(...)``.
This way, your figure reads correctly on every theme, including custom themes
defined by report authors. ``resolve_color`` automatically handles errors and
lets ``workflow-coda`` show teaching messages to report authors in case a
required token is missing from ``theme.yaml``.

The return goes through ``RenderedComponent.from_figure``.  This way,
``workflow-coda`` guarantees the whole figure pipeline: the plot is embedded
correctly, Plotly.js loads exactly once per report, no matter how many figures
the page has, the plot resizes correctly with its card, and the page stays one
self-contained file.  The ``description`` argument is the figure's accessibility
label. This text does not show up visibly in the report.  It is what a screen
reader announces instead of the plot's graphics for people using accessibility
tools.  We recommend you write one for every figure you ship.

Install your new plugin and grow your report
--------------------------------------------

.. code-block:: console

   $ pip install -e path/to/waterfall-plugin

.. note::

   The ``-e`` flag makes the installation editable, meaning changes you make to
   the plugin will be applied without having to re-install the plugin package.

Now add your new component to your report from the first tutorial. It only takes
three small changes.

1. The pipeline's new artifact:

   .. literalinclude:: ../../../examples/waterfall-plugin/steps.json
      :language: json
      :caption: steps.json — the artifact

2. The manifest gains its declaration (``depth.json`` is unchanged):

   .. literalinclude:: ../../../examples/waterfall-plugin/manifest.json
      :language: json
      :caption: manifest.json — extended

   When the pipeline runs for real, produce the manifest through the
   ``verify`` command rather than hand-writing it::

      $ workflow-coda verify manifest.json steps.json \
          --id composition \
          --type org.example.waterfall \
          --format json \
          --schema-version 1.0

      verified steps.json — appended artifact composition to manifest.json

3. The layout gains a second tab (everything above ``tabs:`` is
   unchanged from the first tutorial):

   .. literalinclude:: ../../../examples/waterfall-plugin/layout.yaml
      :language: yaml
      :caption: layout.yaml — extended

Rebuild, and open the report in a browser:

* The tab bar has appeared with a second tab.
* The Composition tab holds your waterfall plot, dressed in the theme's colors:
  the up-steps wear the first series color, the down-steps the second.
* The page is still one self-contained HTML file.

Break it on purpose
-------------------

Two quick experiments teach the two failure families better than any
explanation:

* Rename the placement's ``artifact`` parameter to ``org.example.watterfall`` (a
  typo) and rebuild: instead of your component, the report now shows a notice
  card, quoting the manifest's declared types back at you as a help message.
* Open ``steps.json`` and change one of the step's ``value`` to a string. Then
  rebuild: a red failure card then appears on the report instead of your
  component, naming the step and the key with the invalid type, and displays an
  explanation message ("must be a number").

Undo each when you are done to restore the waterfall plot component.

Where next
----------

* :doc:`../how-to/plugin-development`: everything beyond a simple figure: custom
  css and js, icons, TILE mode, and testing against real bundles.
* The report contracts: :doc:`../reference/framework/api/components` (the render
  call, outcomes, the figure channel), :doc:`../reference/framework/api/plugins`
  (the plugin value and entry point),
  :doc:`../reference/framework/api/artifact_store` (the reading API your render
  call uses).
