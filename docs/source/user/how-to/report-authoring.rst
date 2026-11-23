=================
Authoring reports
=================

The :doc:`"hello world" report <../tutorials/hello-report>` taught the
two files and the build. This guide covers composing a multi-tab page,
repeating content across states, deciding what happens when a component
is missing or has no data, giving the report a look of its own, and
reading the build's messages. Each section is a task you can do on its
own; every exact shape links into the
:doc:`reference documentation <../reference/index>`.

The two files and the command
------------------------------

A report is two authored files plus one the pipeline writes:

* ``manifest.json`` — the pipeline's claim list of what a run
  produced. You do not usually write it, but you read it: every
  data-backed placement in your layout asks for an artifact *type*
  it declares.
* ``layout.yaml`` — yours: the report's identity and its content,
  tab by tab.
* ``theme.yaml`` — optional: the report's colors and fonts.

.. code-block:: console

   $ workflow-coda build manifest.json layout.yaml

Success is silent and writes ``report.html`` in the working
directory (``-o`` chooses another path). A failure prints one
teaching message on stderr, naming the file, the problem, and the
fix; the exit codes are documented in
:doc:`../reference/cli`.

Two path rules keep everything findable: artifact paths in the
manifest resolve against the manifest's directory, and theme, logo,
and favicon paths in the layout resolve against the layout's
directory. Keeping a report's files together in one directory makes
both trivial — the tutorial's structure is the one to copy.

The full grammar of both files — every key, its shape, its meaning —
is the schemas page: :doc:`../reference/schemas/index`. This
guide tells you when to reach for a key; the schemas define it.

Placing components
------------------

A tab's ``components:`` list places content. A placement is three
keys:

* ``id`` — the component, ``<plugin_id>.<component_name>``. What
  ships with the framework is documented component by component in
  :doc:`../reference/core/index`.
* ``title`` — optional; a name for *this instance*, overriding the
  component's default card title.
* ``parameters`` — the component's own configuration. Outside states,
  these pass to its render call as written; inside states, the framework
  first expands states placeholders. Every component documents and
  validates its own parameter vocabulary.

The same component may be placed any number of times, each with its
own title and parameters.

Composing the page
------------------

Placements sit in composition nodes, and nodes nest: a row, grid,
card, or states node takes a ``children:`` list that speaks the same
grammar as a tab's list.

* ``row`` — children side by side; ``split`` gives width ratios, one
  per child (``[2, 1]`` makes the first child twice the width of the
  second). Omitted, equal widths. Every ratio layout collapses to
  a single column on small screens.
* ``grid`` — children flow into columns given by the required
  ``split``; the last row may be short.
* ``card`` — a titled group of children; ``layout: stack | row |
  grid`` picks the inner arrangement.
* ``diagnostics`` — places the report's diagnostics panel at this
  spot in the page.
* ``states`` — builds its children once per axis value, such as a
  batch or sample. Readers select which state's content is visible;
  every state's content is already embedded.

Two rules worth internalizing early:

* One tab, one panel: each tab becomes one page section, and the
  tab bar appears the moment a second tab exists. A single-tab
  report renders no bar at all.
* Composition collapses honestly: when every child of a row, grid,
  or card resolves to nothing, the container disappears too. A states
  panel whose children all resolve away disappears; if every panel
  disappears, its states node disappears too. A tab left with nothing
  drops from the report. The diagnostics ledger still records why.

While composing, comment freely: YAML comments are the cheap way to
park a placement, and a tab that needs to disappear entirely is
commented out whole (a tab requires at least one node).

Repeating content for batches or samples
----------------------------------------

Use ``states`` when the same report structure should read different
artifacts for each batch, sample, patient, or other dimension. Name
the dimension, declare its values, and move the repeated placements
under ``children``.

The tutorial's small layout is a complete example:

.. literalinclude:: ../../../examples/states-report/layout.yaml
   :language: yaml
   :caption: One KPI template expanded for batches a and b

It reads this manifest:

.. literalinclude:: ../../../examples/states-report/manifest.json
   :language: json
   :caption: The two artifact types addressed by the template

The corresponding files contain:

.. literalinclude:: ../../../examples/states-report/depth-a.json
   :language: json
   :caption: depth-a.json

.. literalinclude:: ../../../examples/states-report/depth-b.json
   :language: json
   :caption: depth-b.json

Adapt the artifact type template to the types your manifest actually
declares. ``{batch}`` substitutes at build time into placement titles,
parameter keys and string values, and card titles. Nested parameter
lists and mappings are included. The component id stays literal:
``core.kpi`` is the component for every batch, not a family of component
ids.

Values substitute verbatim. If a value is used in an artifact type, its
spelling must produce a valid artifact address; uppercase display labels
are not silently lowercased. States has no ``sanitize`` option.

If your pipeline discovers artifact families through
``workflow-coda verify``, inspect the generated manifest before choosing
the layout's values and address template. Verification families and
report states are separate mechanisms: the manifest carries concrete
artifact declarations, not the original ``for_each`` family. See
:ref:`families-for-each`.

Choosing an axis and its control
--------------------------------

Declare ``values`` when you want batch or sample labels in a particular
order. The order is preserved; numeric-looking strings remain labels
unless you explicitly declare ``kind: ordered``.

* Use ``kind: categorical`` (the default) for peers, such as batches.
  The reader gets a dropdown.
* Use ``kind: ordered`` for a sequence, such as processing stages.
  The reader gets a single-position slider. Positions follow axis
  order, not numeric distances between labels.

Controls appear automatically when the available shared axis has at
least two values and the dimension affects content on the displayed tab.
A genuinely singleton axis needs no control.

Omit ``values`` only when the **full artifact types** are the axis you
want. Derivation collects every manifest artifact type in declaration
order. It does not extract filename stems, sample names, or the suffix
of ``org.example.sample_metrics-a``; it uses that whole type string.
This can be useful when a parameter should directly receive the selected
artifact type.

A declared empty list is an authoring error. An omitted axis derived
from a manifest with no artifacts collapses at build time and records
an informational ``states_empty`` diagnostic.

Sharing a selection across tabs
--------------------------------

Reuse a dimension name when different parts of the report should react
to the same selection. For example, a ``batch`` states node on a Summary
tab and another on a Details tab share one report-wide batch selection.

Use different dimension names when selections should be independent.

One selector per dimension appears above the tab content. Its visibility
follows the displayed tab and selected outer context; its selection does
not. Moving to a Methods tab with no batch-dependent panels hides the
batch selector without resetting the batch or removing its URL directive.

Shared categorical choices are the union of surviving panel values,
in first-occurrence order across the document. If one node contains only
batch ``a`` and another also contains ``b``, selecting ``b`` does not
make the first node quietly display ``a``. It shows a message explaining
that this node has no content for ``b``. Its selector remains available
so the reader can choose ``a`` to restore that content.

Keep shared nodes consistent:

* Declare the same ``kind`` for the dimension everywhere.
* For ordered axes, use compatible sequences. Partial sequences can
  merge, but do not declare ``a`` before ``b`` in one node and ``b``
  before ``a`` in another.

Conflicting kinds or contradictory ordered sequences disable selection
for that dimension, show feedback, and leave its panels stacked.

Nesting selections
-------------------

Nest a states node when one dimension's content belongs inside another,
such as processing steps within each batch. Use distinct dimension names
for the two levels.

The builder expands the outer value first, then the inner value. Both
placeholders can occur in a child title or artifact address. Declared
inner values can also contain the outer placeholder: an inner value
``"{batch}-final"`` becomes ``"a-final"`` during batch ``a``'s expansion.

At read time, inner choices come from nodes in the selected outer
context. Changing the batch can therefore change the available step
choices. With no explicit step directive, the default is the first
available value in first-occurrence order. An explicit step value that
does not exist in the new context is retained in the URL; feedback
explains the mismatch and the affected dimension remains stacked.

Avoid nesting a dimension inside itself. Although build-time substitution
uses the outer round's value for a shadowed placeholder, read-time
selection still treats the dimension as one global key. It cannot provide
two independent selections for that name.

Also avoid making dimensions depend on one another in opposite nesting
orders in different parts of the report. Cyclic dependencies degrade to
stacked content with feedback instead of inventing a resolution order.

Combining states with markdown variables
----------------------------------------

States placeholders and ``core.markdown`` variables have different jobs:

* ``{batch}`` receives an axis value during report building.
* ``{{ depth }}`` receives a value from the markdown component's JSON
  artifact during component rendering.

In string-valued ``core.markdown.text``, valid double-brace variables
survive states expansion. You can combine the two languages in a sentence
such as ``Batch {batch}: **{{ depth }}**``, backed by the artifact type
``org.example.sample_metrics-{batch}`` from the two-batch example above.

This exception belongs only to that component's ``text`` string. Titles,
artifact addresses, parameter keys, other components' parameters, and
non-string ``text`` values do not gain a double-brace exemption.
Malformed opening braces still teach.

Linking to a selected report view
---------------------------------

Use the URL fragment to address a tab and state values together. For the
two-batch example, append this fragment to the report's URL:

.. code-block:: text

   #tab=1-headlines&state.batch=b

The tab id is the generated panel id. Tab navigation writes it for you;
you can also inspect the panel's ``id`` in the HTML. A fragment containing
only ``#state.batch=b`` selects the batch and uses the default tab.

Raw values are percent-encoded, not slugified. For example, ``Run A``
is addressed as ``Run%20A``; ``Run A`` and ``run-a`` remain distinct.
The simplest way to obtain a valid link is to select the desired view
with the controls and copy the resulting URL.

The page reads the fragment on initial load and whenever it changes.
Tab interactions preserve state directives, and state interactions
preserve the selected tab and other valid state directives. With the
History API available, interactions replace the current URL rather than
adding a browser-history entry for every selection.

Existing ``#panel-id`` tab links remain accepted.

If an explicit value is unavailable, remove its state directive to use
the default, or choose an available value with the control. Initial load
and fragment changes do not silently repair the URL. Unknown tabs,
malformed directives, and axis conflicts produce visible feedback;
the exact degradation rules are in
:doc:`../reference/schemas/index`.

Handling missing state content
-------------------------------

Choose placement policies before deciding how missing panels should look.
The usual ``on_missing`` and ``on_unavailable`` rules apply independently
to every expanded placement.

* ``on_unavailable: notice`` keeps a notice card in the affected state.
* ``on_unavailable: skip`` drops the unavailable placement and records
  a note. If no child survives, that state's panel disappears.
* ``on_unavailable: fail`` refuses the build if the required data is absent.

A missing selection at read time is different from an unavailable
artifact at build time. The selector only knows panels that survived
building; it cannot fetch or rebuild a missing panel.

Place ``type: diagnostics`` outside the repeated states subtree if you
want one copy of the build ledger. A marker inside states is repeated
with the template, and every copy shows the same complete ledger.

Budgeting and checking the complete report
------------------------------------------

States trade report size for self-contained reading. For N values, the
builder expands and renders the repeated template N times. Nested axes
can multiply the content: two batches with three steps each build six
step-content instances. Large tables and figures are embedded for every
instance that renders.

Selection reduces what is visible, not the HTML file's size or build
work. There is no runtime artifact fetching. Keep static content outside
states where possible, and choose a deliberate subset of values in the
layout when a full run would produce an impractically large report.

Before distributing a report, check it in the readers' browser:

* Change tabs and confirm that shared selections remain consistent.
* Change outer states and check nested choices and unavailable-selection
  feedback.
* Operate dropdowns and sliders with the keyboard. If a focused selector
  disappears after a context change, focus should move to the active tab
  button, or to the tab panel when there is no tab bar.
* Disable JavaScript: every tab and state should remain readable, with
  no selection controls.
* Inspect print preview: all tabs and states should appear, with controls
  and selection feedback hidden.
* Reveal figures in different states and confirm that they resize.

Build tests and the framework's minimal-DOM JavaScript tests do not
replace native browser, accessibility, or print checks.

When a component cannot render
------------------------------

Two independent gates, each with its own policy:

* ``on_missing`` — the component id resolves to nothing: the plugin
  is not installed, or the id is a typo. The default ``fail``
  refuses the build, because a dead id is probably an authoring
  mistake; ``notice`` renders the report without it and records the
  omission; ``skip`` drops it silently.
* ``on_unavailable`` — the component resolved, but its data is
  missing: the manifest declares the artifact ``partial``,
  ``failed``, or ``missing``, or does not declare it at all.
  The default ``notice`` renders a card saying so; ``skip`` omits
  the card and records a note; ``fail`` refuses the build.

Both can be set layout-wide or per placement; the placement wins. A
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
favicon, an empty derived states axis), problems (a missing component,
a plugin excluded over schema versions), and per-component facts
(an unavailable outcome under ``skip``). The ledger always records;
the panel renders only where the layout places ``type: diagnostics``.

Place the marker while constructing the report — it is where the
framework talks to you about your own report — and drop it when the
report is final, if your readers do not need it. A placed panel
always renders, and an empty ledger shows "No issues", so it never
leaves a blank.

Read-time selection feedback is separate from this build ledger.
It explains the current URL or shared-axis selection; it does not
rewrite the manifest or add build diagnostics.

Giving the report a look
------------------------

All presentation lives in the theme file; the layout only names it.
A theme is a small vocabulary — the required core color tokens, a
categorical ``series`` palette for figures, and two font stacks —
with its shapes documented in the schemas page. Three authoring
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
  the theme declares; never a color literal. Omitted means the
  theme's ``primary``. The bar's text color is picked automatically
  for contrast, on any theme. By default, the header is a solid color
  (``header_variant: fill``).
* ``logo`` — two vocabularies. A path addresses an image file next
  to the layout: raster formats embed as data, and an SVG file
  inlines as markup, so a logo authored with ``"currentColor"``
  follows the header's text color. Anything else is a bundled
  icon's name; the shipped vocabulary is documented in
  :doc:`../reference/framework/api/icons`.

``favicon`` takes a path, under the same declared-then-strict rule
as ``logo``: omitted is a recorded note; declared, the file must
exist and be what its extension claims.

When the build fails
--------------------

A refusal means one message that names the file, the problem, and
the fix — the message is the documentation. The families you will
meet:

* A manifest or layout that does not validate — an unknown key (a
  typo), a value of the wrong shape, a duplicated mapping key.
  The message identifies the offending location; duplicate-key
  messages also name the line.
* A states template with a malformed or unbound placeholder.
  The error names the layout and offending template.
* A theme or asset that will not load — a missing file, an
  unsupported extension, an image that does not match its
  extension, or a color literal where a token belongs
  (``header_color: "#ff0000"`` is taught: colors live in the theme).
* A component id that resolves to nothing under the default
  ``on_missing: fail`` — the message lists what *is* available.

An exit code of ``2`` is different: the command itself was wrong —
a missing argument, an unknown flag, a nonexistent path
(:doc:`../reference/cli`).

When the page renders, but...
-----------------------------

* **A quiet notice card** where a component should be: the
  component's data is missing. Check that the manifest declares
  the artifact type with ``status: complete``, and that the file is
  where the manifest says it is.
* **A red failure card**: the component raised while rendering.
  Read the quoted error: it may identify invalid component parameters,
  malformed artifact content, or a plugin bug. Correct the named input,
  or report an unexpected exception to the plugin author.
* **A placement missing, with the panel saying so**:
  ``on_missing: notice`` did its job — a typo'd id, or a plugin not
  installed. A ``plugin_excluded`` diagnostic means a version mismatch:
  the plugin does not support the manifest's ``schema_version``,
  and the diagnostic names both versions.
* **A whole section vanished**: every child resolved away, so the
  composition collapsed. The ledger's notes explain — place the
  panel to read them.
* **A selector disappeared after changing tabs**: its dimension does
  not affect the displayed tab or outer context. The shared selection
  remains in effect elsewhere.
* **States remain stacked with selection feedback**: inspect the URL
  and shared dimension declarations. The page is preserving content
  rather than guessing a replacement selection.

Where next
----------

* :doc:`plugin-development` — writing components of your own,
  beyond what ships.
* :doc:`../reference/core/index` — the components the framework
  ships, parameter by parameter.
* :doc:`../reference/schemas/index` — every key of every file
  and the read-time selection grammar.
