======================
A "hello world" report
======================

You will build a working report from two small files, then give it a
look of its own.  Along the way you will meet every idea a
``workflow-coda`` report rests on: the manifest, the layout, honest
diagnostics, and the theme. At the end you hold one self-contained
HTML page you can send to anyone. An optional final step builds a
two-batch report with a selector.

Before you start
----------------

``workflow-coda`` is installed and on your ``PATH`` (see the
repository README). That is all: the tutorial creates every other
file it needs.  Make a directory for the report, keep all the files
in it, and run every command from inside it.

What the pipeline provides
--------------------------

Imagine you have run a pipeline to measure mean sequencing depth.
Per the ``workflow-coda`` design principles, the pipeline is responsible
for generating the artifacts that are used to fill the report; in this
case one ``JSON`` file with the measured depth.

.. literalinclude:: ../../../examples/hello-report/depth.json
   :language: json
   :caption: depth.json — the artifact, as the pipeline wrote it

The ``workflow-coda`` manifest file declares that artifact file to the report:

.. literalinclude:: ../../../examples/hello-report/manifest.json
   :language: json
   :caption: manifest.json

The manifest file is the single input that ``workflow-coda`` uses to find all
artifacts required for the report.  ``id`` names the artifact, ``type`` is its
namespaced kind (the ``org.example.`` prefix keeps third-party types
from colliding), and ``format`` tells consumers how to read the
file. This example uses ``json``, which is one of the built-in claims.
``status: complete`` says the pipeline successfully finished producing this
file.  ``workflow-coda`` validates the manifest's shape when the report
builds; artifact files are read only when a component actually asks for one.

.. note::

   The manifest's ``schema_version`` (``"0.3.0"``) is the contract
   between pipeline and report.  The artifact's own
   ``schema_version`` (``"1.0"``) is a different axis: the version
   of the artifact's *content*, defined by the pipeline author.
   The two are never compared.

The manifest in this tutorial is small enough to write by hand, and
writing it once is the fastest way to meet its shape.  When the
pipeline runs for real, the same file is usually produced by
``workflow-coda verify``: the command checks each artifact under
its declared format and records the checksum of exactly the bytes
it checked: :doc:`../how-to/producing-manifests`.

Declaring the report's shape and components: the layout
-------------------------------------------------------

The layout is provided by the report author; you! This file defines the report's
identity and its content, tab by tab. Start with one component on one tab:

.. code-block:: yaml
   :caption: layout.yaml - first version

   schema_version: "0.4.0"
   title: Run summary
   tabs:
     - title: Headlines
       components:
         - id: core.kpi
           title: Mean depth
           parameters:
             artifact: org.example.sample_metrics
             key: depth

Hopefully, most of this speaks for itself.  The one new idea is the
*placement*: ``id: core.kpi`` names a component that ships with
``workflow-coda``'s ``core`` plugin, and ``parameters`` is how you configure the
component. Here, ``parameters`` define which artifact type to read and which key
to pull out. Every component owns its own parameters.

Build it
--------

.. code-block:: console

   $ workflow-coda build manifest.json layout.yaml

The command prints nothing and writes ``report.html`` in the
working directory.  Open it in your browser, and you should see:

* "Run summary" on the colored header bar,
* one card: "Mean depth", showing ``42.7``,
* a footer crediting the pipeline by name and version.

There is no tab bar since a single tab is not yet navigation.  Adding more tabs
will add the tab bar to the report's header. We'll do this in the second
tutorial.

Ask the report what it left out
-------------------------------

A ``workflow-coda`` report does not hide its omissions. Instead, it collects
them for diagnostics.  To see the diagnostics in your report, add the diagnostics
marker to the ``Headlines`` tab, after the placement:

.. code-block:: yaml

   components:
     - id: core.kpi
       title: Mean depth
       parameters:
         artifact: org.example.sample_metrics
         key: depth
     - type: diagnostics

Rebuild the report, and the page gains a *Diagnostics* panel.  It lists three
notes, and each is honest: the report rendered with the default theme pair, without a
logo, and without a favicon. Each note also explains how to add what is missing.
None of them are errors; they are styling choices you have not made yet.  This
panel is worth placing while you are constructing your report: it is where the
framework talks to you about your own report. Once you are happy with your
report, you may choose to omit it, since the viewers of your report likely won't
need this information.

Give it a look
--------------

Take the panel's advice.  Declare a theme, a logo, and a header
color in the layout:

.. code-block:: yaml

   schema_version: "0.4.0"
   title: Run summary
   theme:
     light: default
     dark: theme.yaml
   logo: core-arrow-up
   header_color: accent
   tabs:
     - title: Headlines
       components:
         - id: core.kpi
           title: Mean depth
           parameters:
             artifact: org.example.sample_metrics
             key: depth
         - type: diagnostics

And write the dark-mode theme file next to the layout. Light mode uses
the bundled ``default`` declaration; the custom file defines the
dark-mode palette:

.. literalinclude:: ../../../examples/hello-report/theme.yaml
   :language: yaml
   :caption: theme.yaml

Three things to notice:

* The colors are quoted.  In ``YAML`` a bare ``#`` starts a comment —
  ``background: #10141a`` would silently lose its value.
* ``logo: core-arrow-up`` is a bundled icon's name,
  one of the icons the ``workflow-coda`` itself ships. You can define any
  shipped icon, or alternatively, a path to your own image.
  Using an ``SVG`` logo with ``"currentColor"`` will let the icon follow the
  header's text color.
* ``header_color: accent`` names a token the theme declares, never
  a color literal. ``workflow-coda`` uses color tokens to maintain a cohesive
  look. Themes may define a light and dark text color, and ``workflow-coda``
  will automatically use the color that produces the best contrast for
  readability.

Rebuild your report. The page follows your system's light or dark
preference. Use the sun/moon button on the right of the header to
inspect both modes: dark mode uses your custom palette, while light
mode uses the bundled default. An arrow sits beside the title, and
the header bar wears the active theme's accent color.

The component did not change by one character. Colors belong to the
theme declarations; content belongs to the components. Reloading
returns to system preference.

The diagnostics panel noticed too: two notes are gone, and the one
that remains offers the favicon, which follows the same rule as the
logo.

The finished files
------------------

.. literalinclude:: ../../../examples/hello-report/layout.yaml
   :language: yaml
   :caption: layout.yaml — complete

Four small files build this report: one artifact, one manifest, one
theme, one layout.  The page they produce is a single self-contained
HTML file; it loads nothing from the internet and needs no servers.

Optional: select between two batches
------------------------------------

Real pipelines often produce the same files for each ``batch``, ``sample``,
``patient``, or other. ``workflow-coda`` handles this through ``states``. Below
we will build an example report generated from two batches. The report file will
include a dropdown selector to choose which batch to show. Keep your finished
report unchanged: make a new directory and run the following build from
inside it.

Write these two artifact files:

.. literalinclude:: ../../../examples/states-report/depth-a.json
   :language: json
   :caption: depth-a.json — batch a

.. literalinclude:: ../../../examples/states-report/depth-b.json
   :language: json
   :caption: depth-b.json — batch b

Declare both in the new directory's manifest:

.. literalinclude:: ../../../examples/states-report/manifest.json
   :language: json
   :caption: manifest.json — two batches

Write this layout alongside them:

.. literalinclude:: ../../../examples/states-report/layout.yaml
   :language: yaml
   :caption: layout.yaml — one template, two states

``type: states`` builds the child placement once for each value in
``[a, b]``. At build time, ``{batch}`` becomes ``a`` or ``b`` in the
title and artifact type. The component id stays ``core.kpi``.

.. code-block:: console

   $ workflow-coda build manifest.json layout.yaml

Open the new ``report.html`` with JavaScript enabled. You should see
"Batch summary", a dropdown labeled ``batch``, and batch ``a``'s mean
depth, ``42.7``. Choose ``b``: the card now shows ``18.3``. Reload the
page; the URL keeps your batch selection.

This example uses the default theme pair and needs no additional files.
Both batches are already embedded in the HTML: selection fetches nothing.
Without JavaScript, and when printing, both batches appear stacked.
More states mean more embedded content, even when only one is visible.

When making reports for real pipelines, families of artifacts may be discovered
through different mechanisms. The ``workflow-coda verify`` command can be used
to dynamically generate the ``manifest.json`` based on the actual pipeline
output. Take a look at the :ref:`Producing manifests how-to guide <families-for-each>`.
For more details on how to build and customize your own reports, continue with
:doc:`../how-to/report-authoring`; the exact keys available are documented in
:doc:`../reference/schemas/index`.

Where next
----------

* :doc:`first-plugin` grows the original single-batch report with a component
  you get to write yourself: a Plotly figure ``workflow-coda`` does not ship.
* Every layout and theme key, with its exact shape:
  :doc:`../reference/schemas/index`.
* The command and its exit codes: :doc:`../reference/cli`.
