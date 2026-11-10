=================
Authoring reports
=================

The :doc:`"hello world" report <../tutorials/hello-report>` taught the
two files and the build.  This guide covers the rest of what a report
author does: composing a multi-tab page, deciding what happens when a
component is missing or has no data, giving the report a look of its
own, and reading the build's messages.  Each section is a task you
can do on its own; every exact shape links into the
:doc:`reference documentation <../reference/index>`.

The two files and the command
------------------------------

A report is two authored files plus one the pipeline writes:

* ``manifest.json`` — the pipeline's claim list of what a run
  produced.  You do not write it, but you read it: every placement
  in your layout asks for an artifact *type* it declares.
* ``layout.yaml`` — yours: the report's identity and its content,
  tab by tab.
* ``theme.yaml`` — optional: the report's colors and fonts.

.. code-block:: console

   $ workflow-coda build manifest.json layout.yaml

Success is silent and writes ``report.html`` in the working
directory (``-o`` chooses another path).  A failure prints one
teaching message on stderr, naming the file, the problem, and the
fix; the exit codes are documented in
:doc:`../reference/framework/cli`.

Two path rules keep everything findable: artifact paths in the
manifest resolve against the manifest's directory, and theme, logo,
and favicon paths in the layout resolve against the layout's
directory.  Keeping a report's files together in one directory makes
both trivial — the tutorial's structure is the one to copy.

The full grammar of both files — every key, its shape, its meaning —
is the schemas page: :doc:`../reference/framework/schemas`.  This
guide tells you when to reach for a key; the schemas define it.

Placing components
------------------

A tab's ``components:`` list places content.  A placement is three
keys:

* ``id`` — the component, ``<plugin_id>.<component_name>``.  What
  ships with the framework is documented component by component in
  :doc:`../reference/core/index`.
* ``title`` — optional; a name for *this instance*, overriding the
  component's default card title.
* ``parameters`` — the component's own configuration, passed to its
  render call exactly as written.  Every component documents its own
  parameters; the framework interprets none of them.

The same component may be placed any number of times, each with its
own title and parameters.

Composing the page
------------------

Placements sit in composition nodes, and nodes nest: a row, grid, or
card takes a ``children:`` list that speaks the same grammar as a
tab's list.

* ``row`` — children side by side; ``split`` gives width ratios, one
  per child (``[2, 1]`` makes the first child twice the width of the
  second).  Omitted, equal widths.  Every ratio layout collapses to
  a single column on small screens.
* ``grid`` — children flow into columns given by the required
  ``split``; the last row may be short.
* ``card`` — a titled group of children; ``layout: stack | row |
  grid`` picks the inner arrangement.
* ``diagnostics`` — places the report's diagnostics panel at this
  spot in the page.

Two rules worth internalizing early:

* One tab, one panel: each tab becomes one page section, and the
  tab bar appears the moment a second tab exists.  A single-tab
  report renders no bar at all.
* Composition collapses honestly: when every child of a row, grid,
  or card resolves to nothing, the container disappears too — and a
  tab left with nothing drops from the report.  The diagnostics
  ledger still records why (below).

While composing, comment freely: YAML comments are the cheap way to
park a placement, and a tab that needs to disappear entirely is
commented out whole (a tab requires at least one node).

When a component cannot render
------------------------------

Two independent gates, each with its own policy:

* ``on_missing`` — the component id resolves to nothing: the plugin
  is not installed, or the id is a typo.  The default ``fail``
  refuses the build, because a dead id is probably an authoring
  mistake; ``notice`` renders the report without it and records the
  omission; ``skip`` drops it silently.
* ``on_unavailable`` — the component resolved, but its data is
  missing: the manifest declares the artifact ``partial`` or
  ``missing``, or does not declare it at all.  The default
  ``notice`` renders a card saying so; ``skip`` omits the card and
  records a note; ``fail`` refuses the build.

Both can be set layout-wide or per placement; the placement wins.  A
working pattern: keep ``on_missing: fail`` while authoring, so
typos surface immediately, then decide placement by placement which
absences are expected pipeline behavior and mark those ``notice`` or
``skip``.

The two gates are orthogonal: a missing *component* never falls
under ``on_unavailable``, and missing *data* never falls under
``on_missing``.

The diagnostics ledger
-----------------------

The framework records everything noteworthy about a build:
informational notes (the default theme, an omitted logo or
favicon), problems (a missing component, a plugin excluded over
schema versions), and per-component facts (an unavailable outcome
under ``skip``).  The ledger always records; the panel renders only
where the layout places ``type: diagnostics``.

Place the marker while constructing the report — it is where the
framework talks to you about your own report — and drop it when the
report is final, if your readers do not need it.  A placed panel
always renders, and an empty ledger shows "No issues", so it never
leaves a blank.

Giving the report a look
------------------------

All presentation lives in the theme file; the layout only names it.
A theme is a small vocabulary — the required core color tokens, a
categorical ``series`` palette for figures, and two font stacks —
with its shapes documented in the schemas page.  Three authoring
facts matter here:

* Colors are quoted ``#rrggbb`` — in YAML a bare ``#`` starts a
  comment.
* Fonts are family names only: ``url(...)`` fetches are refused.
  The report loads nothing from the network, on any page, ever.
* Extra tokens are yours to declare: each becomes a CSS custom
  property on the page, and components can adopt them — a
  component's documentation says which tokens it understands.

Two layout keys finish the look:

* ``header_color`` — the header bar's background, named as a token
  the theme declares; never a color literal.  Omitted means the
  theme's ``primary``.  The bar's text color is picked automatically
  for contrast, on any theme.
* ``logo`` — two vocabularies.  A path addresses an image file next
  to the layout: raster formats embed as data, and an SVG file
  inlines as markup, so a logo authored with ``"currentColor"``
  follows the header's text color.  Anything else is a bundled
  icon's name; the shipped vocabulary is documented in
  :doc:`../reference/framework/api/icons`.

``favicon`` takes a path, under the same declared-then-strict rule
as ``logo``: omitted is a recorded note; declared, the file must
exist and be what its extension claims.

When the build fails
--------------------

A refusal means one message that names the file, the problem, and
the fix — the message is the documentation.  The families you will
meet:

* A manifest or layout that does not validate — an unknown key (a
  typo), a value of the wrong shape, a duplicated mapping key.  The
  message names the key and its line.
* A theme or asset that will not load — a missing file, an
  unsupported extension, an image that does not match its
  extension, or a color literal where a token belongs
  (``header_color: "#ff0000"`` is taught: colors live in the theme).
* A component id that resolves to nothing under the default
  ``on_missing: fail`` — the message lists what *is* available.

An exit code of ``2`` is different: the command itself was wrong —
a missing argument, an unknown flag, a nonexistent path
(:doc:`../reference/framework/cli`).

When the page renders, but...
-----------------------------

* **A quiet notice card** where a component should be: the
  component's data is missing.  Check that the manifest declares
  the artifact type with ``status: complete``, and that the file is
  where the manifest says it is.
* **A red failure card**: the component's code raised — a plugin
  bug, not a report-authoring problem.  The card quotes the error;
  report it to the plugin's author.
* **A placement missing, with the panel saying so**:
  ``on_missing: notice`` did its job — a typo'd id, or a plugin not
  installed.  A ``plugin_excluded`` note means a version mismatch:
  the plugin does not support the manifest's ``schema_version``,
  and the note names both versions.
* **A whole section vanished**: every child resolved away, so the
  composition collapsed.  The ledger's notes explain — place the
  panel to read them.

Where next
----------

* :doc:`plugin-development` — writing components of your own,
  beyond what ships.
* :doc:`../reference/core/index` — the components the framework
  ships, parameter by parameter.
* :doc:`../reference/framework/schemas` — every key of every file.
