=======
Schemas
=======

The report framework reads two versioned files — the **manifest**,
the stable interface an artifact producer (the pipeline) writes, and
the **layout**, the report author's composition of the report — and,
when the layout declares one, a **theme** file of design tokens.
This page documents all three as the files are written — the wire
grammar, every field, its shape, and its meaning. It also documents
the URL-fragment grammar used to select tabs and states in the generated
report. The same models are documented for plugin developers as the
Python API: :doc:`api/manifest` and :doc:`api/layout`.

Unknown model keys are rejected. Text fields require strings, and the
two versioned files gate their versions — a file written against an
unknown schema version fails validation, because an unrecognized
document cannot be validated or consumed correctly. The theme file
has no version to gate: it is a data file of design tokens, validated
by shape alone.

The :doc:`tutorials <../../tutorials/index>` walk these files into a working
report, one key at a time. Task-oriented states guidance lives in
:doc:`../../how-to/report-authoring`.

The report manifest
-------------------

The manifest is a small JSON file written next to the artifacts a
pipeline produced, declaring who produced them and where each
artifact file lives with its claimed shape and status — and, when
the pipeline produced it through ``workflow-coda verify``, the
account of what the verification checked. Loading validates the
envelope only: artifact files are never touched until
a component reads one (:doc:`api/artifact_store`). The manifest's
schema version also gates plugins — a plugin runs only when the
manifest's version is one it declares support for; the story lives
in :doc:`../core/index`.

Envelope and producer
.....................

.. list-table::
   :header-rows: 1
   :widths: 16 10 24 50

   * - Key
     - Required
     - Shape
     - Meaning
   * - ``schema_version``
     - yes
     - the literal ``"0.3.0"``
     - The envelope contract version this file complies with; an unknown version
       fails with the declared and expected versions named. Version 0.3.0
       added the optional artifact ``verification`` record (below); earlier
       envelopes — ``0.2.0``, which widened the artifact ``format`` value
       space to namespaced plugin names — are not read: regenerate such
       manifests with ``workflow-coda verify``.
   * - ``producer``
     - yes
     - object
     - The workflow or application that produced the manifest and
       its artifacts (the table below).
   * - ``artifacts``
     - yes
     - list of objects; may be empty
     - The artifact declarations, in declaration order. Artifact
       ids are unique (they identify artifacts) and types are unique
       (the store resolves by type); violations are reported
       together, so every collision surfaces at once.

Producer fields:

.. list-table::
   :header-rows: 1
   :widths: 16 10 24 50

   * - Key
     - Required
     - Shape
     - Meaning
   * - ``name``
     - yes
     - non-empty string
     - Human-readable name of the producing workflow or application.
   * - ``version``
     - yes
     - non-empty string
     - The producer's own version, e.g. a release number.
   * - ``module_id``
     - no
     - non-empty string
     - Identifier of the specific workflow module that produced
       the artifacts.
   * - ``run_id``
     - no
     - non-empty string
     - Identifier of the specific run that produced the artifacts.

Artifact declarations
.....................

.. list-table::
   :header-rows: 1
   :widths: 16 10 28 46

   * - Key
     - Required
     - Shape
     - Meaning
   * - ``id``
     - yes
     - ``[a-z][a-z0-9_-]*``
     - Unique identifier of the artifact within the manifest, e.g.
       ``sample_metrics``.
   * - ``type``
     - yes
     - at least two dot-separated ``[a-z][a-z0-9_-]*`` segments
     - The namespaced artifact type, e.g.
       ``org.example.sample_metrics``. Components address artifacts
       by type, so types are unique across the manifest.
   * - ``schema_version``
     - yes
     - non-empty string
     - Version of the artifact's *content* schema, e.g. ``"1.0"`` —
       an axis distinct from the envelope version.
   * - ``path``
     - yes
     - relative path
     - The artifact's location relative to the manifest file:
       forward slashes, never absolute, no ``..`` segments.
   * - ``format``
     - yes
     - ``json`` | ``txt`` | ``bytes``, or a namespaced name
       (``core.tabular``, ``bio.newick``)
     - The artifact's format — a claim, not a service. ``json`` is
       an interpreted claim with a store reader; ``txt`` and
       ``bytes`` are interpretation-free (UTF-8 text, raw bytes) for
       consumers with their own parsers. A namespaced name is a
       plugin convention whose grammar lives in the owning plugin.
   * - ``status``
     - yes
     - ``complete`` | ``partial`` | ``failed`` | ``missing``
     - The artifact's lifecycle status — see below.
   * - ``sha256``
     - no
     - 64 lowercase hex characters
     - Optional SHA-256 checksum of the artifact file; the store
       verifies it when present.
   * - ``verification``
     - no
     - object
     - The pipeline's own account of how this artifact was
       verified: what was checked, under which reading, and on
       failure why. Written by ``workflow-coda verify``; opaque
       transport to the framework, which round-trips it without
       interpretation. Absent on hand-written declarations.

``complete`` is the only status eligible for artifact reading; it does
not itself guarantee that the file exists or its content is valid.
``partial``, ``failed``, and ``missing`` describe artifacts a
partial or failed run declared but did not fully produce — expected
missing data. A component's unavailable outcome is handled by the
layout's ``on_unavailable`` policy.

The ``verification`` record is the verifier's account, and its
grammar belongs to the format that verified the artifact: every
record carries ``format`` and ``status`` — an ``ok`` record adds
what was checked in the format's own vocabulary (``json``'s
``keys_checked``; ``core.tabular``'s ``sep``, ``header``,
``rows``, ``columns_checked``, ``min_rows``), and a ``failed``
record carries ``message`` with the teaching that failed it. The
framework stores and round-trips the whole record without
interpreting it — the same transport law as component parameters
after any states-template expansion.

Loading rules
.............

A manifest whose declared schema version is not 0.3.0 fails with the declared
and expected versions named, before envelope validation — a ``0.2.0``
manifest is taught forward with the regeneration command
(``workflow-coda verify``), not parsed.
The loader reads the file as strict UTF-8 (a byte-order mark is
rejected with instructions), parses it as JSON, and validates the
envelope. Every failure — unreadable, invalid JSON at a named line
and column, or an envelope violation — is one teaching error with
the file path for context (:doc:`api/manifest`).

An example manifest
...................

.. code-block:: json

   {
     "schema_version": "0.3.0",
     "producer": {
       "name": "seq-pipeline",
       "version": "1.4.0",
       "run_id": "run-42"
     },
     "artifacts": [
       {
         "id": "sample_metrics",
         "type": "org.example.sample_metrics",
         "schema_version": "1.0",
         "path": "outputs/sample_metrics.json",
         "format": "json",
         "status": "complete",
         "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
         "verification": {
           "format": "json",
           "status": "ok",
           "keys_checked": ["depth"]
         }
       }
     ]
   }

The report layout
------------------

The layout is the report author's file: the report's identity, and
an ordered list of *tabs*, each composing components through a small
layout grammar. The layout's version is an axis entirely distinct
from manifest versions — the two are never compared.

The grammar's front door is shape dispatch: a node carrying ``id``
is a *placement* — one component instance; a node carrying
``type`` is a *composition* — ``row``, ``grid``, ``card``,
``diagnostics``, or ``states``. A node carrying both is a teaching error, as is
a node carrying neither. Nodes nest: a tab's list and the children of
rows, grids, cards, and states all speak the same grammar.

Identity
........

.. list-table::
   :header-rows: 1
   :widths: 16 12 24 48

   * - Key
     - Required
     - Shape
     - Meaning
   * - ``schema_version``
     - yes
     - the literal ``"0.3.0"``
     - The layout contract version; a ``0.1.0`` or ``0.2.0`` file fails with the
       migration spelled out (below).
   * - ``title``
     - yes
     - visible text
     - The report's title, rendered in the page header.
   * - ``subtitle``
     - no
     - visible text
     - One-line subtitle under the title.
   * - ``author``
     - no
     - visible text
     - Free-form credit line in the footer — a person, a group,
       several names.
   * - ``version``
     - no
     - visible text
     - Free-form report revision, shown in the header — "1.2.0",
       "v2", "draft", a date.
   * - ``theme``
     - no
     - relative path
     - Theme file; omitted means the built-in default theme (with a
       diagnostic). Declared, the file must load — the theme file's
       grammar is documented in its own section below.
   * - ``logo``
     - no
     - relative path, or a bundled icon name
     - Logo image; omitted renders without one (with a diagnostic
       explaining how to add one). A relative path addresses an
       image file next to the layout: raster formats embed as a data
       URI; an SVG file inlines as sanitized markup, so a logo
       authored with ``currentColor`` inherits the header's ink.
       Anything else — no path separators, no dots — is a bundled
       icon's name (``core-arrow-up`` and friends), loaded through
       the build's icon library and inlined the same way.
   * - ``favicon``
     - no
     - relative path
     - Same declared-then-strict rule as ``logo``.
   * - ``header_color``
     - no
     - theme token name — never a color literal
     - The page header's background as a theme token the report's
       theme declares, ``primary`` by default. The bar's ink is
       contrast-picked from the theme's text pair, so it reads on
       any theme. Declared, the token must exist in the loaded
       theme; omitted is a styling default, not a diagnostic-noted
       absence.
   * - ``on_missing``
     - no
     - ``fail`` (default) | ``notice`` | ``skip``
     - Layout-wide default for placements whose component id resolves
       to nothing; per-placement ``on_missing`` overrides.
   * - ``on_unavailable``
     - no
     - ``notice`` (default) | ``skip`` | ``fail``
     - Layout-wide default for unavailable outcomes (missing data);
       per-placement ``on_unavailable`` overrides.
   * - ``tabs``
     - yes
     - list, at least one
     - The report's tabs, in declaration order; each surviving tab
       becomes one panel, and the tab bar is generated from them.

``theme``, ``logo``, and ``favicon`` follow one rule: **declared,
then strict** — omitted is a valid, diagnostic-noted absence;
declared means the file must exist and load. ``header_color``
follows the strict half only: declared, the theme must carry the
token; omitted means ``primary``, silently — a styling default,
not a missing file. The report never references external files:
declared assets are embedded at build time (the favicon and raster
logos as data URIs; SVG logos and named icons as inlined svg
markup), so the written page is self-contained.

Tabs and placements
...................

A tab is a titled composition: ``title`` (visible text, its label in
the tab bar) and ``components`` (at least one node — an empty tab is
rejected; comment out the whole tab while composing). A
single-tab report renders no tab bar. A single-tab report containing
states can still carry state-selection enhancement.

.. list-table::
   :header-rows: 1
   :widths: 16 10 24 50

   * - Key
     - Required
     - Shape
     - Meaning
   * - ``id``
     - yes
     - ``<plugin_id>.<component_name>``
     - The component id, as a plugin declares it: lowercase
       snake_case on both sides of exactly one dot.
   * - ``title``
     - no
     - visible text
     - Title for *this instance*, overriding the declaration's
       default; absent means inherit. States placeholders expand
       before rendering when the placement is inside states.
   * - ``parameters``
     - no
     - object (default ``{}``)
     - Component-owned transport. Outside states, values pass to the
       render call as written. Inside states, the framework first
       substitutes placeholders in keys and string leaves, recursively.
       Each component then reads and validates its own keys. Values
       must be JSON-compatible — YAML's richer types (dates, sets,
       binary) are rejected, naming the field.
   * - ``on_missing``
     - no
     - ``fail`` | ``notice`` | ``skip``
     - Per-placement override of the layout-level default.
   * - ``on_unavailable``
     - no
     - ``notice`` | ``skip`` | ``fail``
     - Per-placement override of the layout-level default.

Composition nodes
..................

.. list-table::
   :header-rows: 1
   :widths: 12 30 58

   * - Type
     - Keys
     - Meaning
   * - ``row``
     - ``children`` (≥ 1); ``split`` optional
     - Children side by side under width ratios — one ratio per
       child; omitted, equal widths. Collapses to one column on
       small screens.
   * - ``grid``
     - ``children`` (≥ 1); ``split`` required
     - Children flow row-major into ratio-given columns; the last
       row may be short.
   * - ``card``
     - ``children`` (≥ 1); ``title``, ``layout``, ``split``
       optional
     - A titled grouping — the visual "these belong together".
       ``layout``: ``stack`` (the default), ``row``, or ``grid``;
       ``split`` sizes a row or grid layout; a stack rejects it.
   * - ``diagnostics``
     - none
     - Places the report's diagnostics panel here, always with
       state — an empty ledger shows "no issues". A report that
       places none shows no diagnostics at all; the builder still
       records everything.
   * - ``states``
     - ``dimension``; ``children`` (≥ 1); ``kind``, ``values``
       optional
     - Expands its children once per axis value at build time.
       The complete panels ship in the HTML; URL-driven enhancement
       selects visibility at read time. The fields and expansion
       rules are specified below.

States fields
.............

.. list-table::
   :header-rows: 1

   * - Key
     - Required
     - Shape
     - Meaning
   * - ``type``
     - yes
     - the literal ``states``
     - Selects this composition node.
   * - ``dimension``
     - yes
     - ``[a-z][a-z0-9_-]*``
     - The placeholder name and report-wide selection key, such as
       ``batch`` or ``sample_id``. Hyphens are also permitted.
   * - ``kind``
     - no
     - ``categorical`` (default) | ``ordered``
     - Categorical peers use a dropdown; an ordered sequence uses a
       single-position slider. Kind is declared, never inferred from
       numeric-looking labels.
   * - ``values``
     - no
     - non-empty list of unique visible-text strings
     - The declared axis, in written order. Labels retain case and
       whitespace. Omitted, or ``null``, derives the axis from distinct
       full manifest artifact types in declaration order.
   * - ``children``
     - yes
     - list of nodes, at least one
     - The template expanded for every axis value.

No other states keys are accepted. In particular, states has no
``title``, ``sanitize``, selector-placement, or subset-selection key.
Selection controls are automatic; their labels are dimension names.

Derivation uses artifact declarations, not file discovery or availability.
It includes types whose files are absent or whose status is not
``complete``. It does not extract a suffix or sample label from a type.

Declared-empty axes fail layout validation. Derived-empty axes collapse
at build time and record an informational ``states_empty`` diagnostic.

States expansion and collapse
..............................

Each states node expands at build time, one round per value. Raw values
substitute verbatim; they are not trimmed, lowercased, or slugified.

The substitution boundary includes:

* Placement titles.
* Every string leaf in parameters, including mapping keys, list items,
  and nested mapping values.
* Card titles.
* Nested states nodes' declared values and their template children.

Numbers, booleans, and null parameter values remain unchanged.
Structural fields do not substitute: placement ids, policies, splits,
dimension names, and kinds remain literal. If parameter keys expand to
the same spelling, the later assignment wins in mapping iteration order.

A placeholder has exactly the form ``{name}``, where ``name`` matches
the dimension grammar. Each round substitutes its own dimension and
passes through placeholders bound for other rounds. A malformed
placeholder or a name outside the round's scope raises an expansion
error wrapped as ``LayoutError`` with the layout path and chained cause.

Nested outer placeholders are substituted before inner expansion.
If an inner states node reuses the outer dimension name, the outer
round has already replaced that placeholder throughout the subtree:
the outer round wins. This does not create an independent read-time
selection key.

Only an opening ``{`` starts the placeholder language; a lone ``}``
is literal. There is no literal-opening-brace escape in states-templated
strings.

Valid ``{{ variable }}`` expressions in string-valued
``core.markdown.text`` are opaque to states expansion. The markdown
component resolves them from its artifact. This exception does not apply
to other fields, other components, non-string ``text`` values, or
verification specs. Malformed braces remain subject to the states rules.

Every expanded placement goes through the ordinary resolution and
unavailable-data policies. A panel whose children all resolve away drops;
a states node whose panels all drop also disappears. Collapse travels
upward through enclosing compositions and tabs.

An unavailable notice, a failure entry, or a deliberate ``skipped``
outcome remains a document entry under the existing builder contract.
The renderer suppresses a deliberate skipped outcome; it is not itself
a build-time collapse trigger.

Diagnostics markers inside states repeat with the template. Every marker
renders the same complete build ledger, not a state-specific subset.

All surviving state content is embedded in the page. For N values,
the repeated template is built N times; nested axes can multiply these
instances. Read-time selection reduces visibility, not build work or
HTML size. No content is fetched when a selection changes.

Read-time selection grammar
............................

Selection uses the URL hash fragment, including for local-file reports.
Structured fragments contain ``&``-separated ``key=value`` directives:

.. code-block:: text

   #tab=1-headlines&state.batch=b

.. list-table::
   :header-rows: 1

   * - Directive
     - Value
     - Meaning
   * - ``tab``
     - Generated tab-panel id
     - Selects one tab. Ids are prefixed by their 1-based document
       position, followed by a slug of the tab title.
   * - ``state.<dimension>``
     - Raw axis value
     - Selects the value report-wide for that dimension.

Keys and values are percent-encoded UTF-8. Raw values are never
normalized. ``Run A`` is addressed as ``Run%20A`` and remains distinct
from ``run-a``. A literal plus sign is not interpreted as a space.

A directive splits at its first ``=``. Unknown keys, invalid dimension
names, duplicate keys, empty values, and malformed percent encoding
produce feedback. Each tab or state dimension may be selected at most
once.

A fragment without either ``=`` or ``&`` is accepted as a legacy
tab-panel anchor, such as ``#1-headlines``. An empty fragment declares
no selection.

Initial load and ``hashchange`` read the URL without rewriting it.
Tab and widget interactions serialize selections while preserving other
parsed state directives. Malformed directives are not carried through
serialization. When the History API is available, interactions use
``replaceState`` rather than adding history entries; otherwise they
update the hash directly.

Defaults and shared axes
........................

Without a tab directive, the default is the first document tab.
Without a state directive, the default is the first available value
in first-occurrence order in the selected outer context.

Each dimension has one report-wide selection. Shared categorical axes
use the union of surviving values in first-occurrence document order.

Shared ordered axes merge their declared precedence constraints.
Compatible partial sequences are permitted; first occurrence breaks
ties between unconstrained values. The default is chosen from
first-occurrence order before this ordered merge. Contradictory ordering
or differing shared kinds disables selection for that dimension.

Nested availability is calculated from nodes whose ancestor panels match
the selected outer dimensions. An unselected or degraded outer dimension
leaves its contexts available. Cyclic cross-dimension dependencies
disable selection for the unresolved dimensions rather than inventing
an evaluation order.

Controls and degradation
........................

One shared control per dimension appears above tab content when:

* The dimension is not disabled.
* Its available shared axis contains at least two values.
* An active states node using it exists on the displayed tab.

A locally singleton node can still have a selector when the shared axis
contains other choices: changing the value can hide or restore that
node's content. With tabs stacked, relevance is evaluated across all
displayed tabs. Changing tabs hides irrelevant controls without resetting
shared selections.

Categorical controls are labeled dropdowns. Ordered controls are
single-position sliders indexed over available values, with the raw
label exposed as ``aria-valuetext`` and visible text. A degraded ordered
selection uses a temporary ``-1`` non-axis position labeled as unselected;
choosing a real value restores the ordinary axis range. This is not
subset selection or an additional axis value.

Controls replan after tab or outer-context changes. Focus returns to
the same dimension's control when it remains available. If it disappears,
focus moves to the active tab button (or the first tab button when tabs
are stacked); without a tab bar, the tab panel is the fallback.

Selection failures preserve content:

* An explicit value absent from the global axis or selected outer context
  produces feedback and leaves the affected dimension stacked. The URL
  retains the explicit value until an interaction changes it.
* Malformed, duplicate, or empty directives for a valid state dimension
  leave that dimension stacked.
* A malformed structured fragment, including an unknown directive key,
  invalid dimension name, or invalid tab directive, marks the fragment
  invalid: tabs and state dimensions remain stacked.
* A syntactically valid but unknown tab id stacks tabs; otherwise valid
  state selections still apply.
* A syntactically valid directive for a dimension absent from the report
  produces feedback; known dimensions continue their ordinary selection.
* Shared-kind conflicts, contradictory ordered axes, and cyclic
  dependencies disable selection for the affected dimensions and show
  feedback.
* A globally valid selection missing from one active states node hides
  that node's nonmatching panels and shows an explicit no-content message
  there. It does not choose another value locally.

Independent or nested dimensions can still filter content while another
dimension is stacked. Stacked degradation for one dimension does not
necessarily display every descendant state.

Without JavaScript, every tab and state is present and visible, and
selection controls are absent or hidden. Print styles restore all tabs
and state panels, and hide navigation controls, state controls, and
read-time selection feedback.

Reveal events notify visible content through ``coda:tab-shown`` and
``coda:state-shown``. The framework uses them to resize visible Plotly
figures. The build diagnostics ledger is independent of read-time
selection feedback.

Split ratios
............

``split`` gives width ratios: at least two positive numbers,
relative — ``[2, 1]`` makes the first region twice the second. A
row takes exactly one ratio per child (or no ``split``, for equal
widths); a grid takes the column ratios and requires them. Three
shapes are teaching errors: a boolean (bare ``yes``/``no`` are
booleans in YAML, not words), any non-number, and a non-positive
value.

YAML authoring rules
....................

* Text fields require *visible* text: whitespace-only is always an
  authoring mistake.
* Duplicate mapping keys are rejected — plain YAML silently keeps
  the last occurrence; the error names the key and its line.
* Boolean traps are explained, not shown opaquely: when
  ``title: no`` arrives as the boolean ``False``, the error explains
  that bare ``true``/``false``/``yes``/``no``/``on``/``off`` are
  booleans in YAML, and quotes the word for you.
* A ``0.1.0`` or ``0.2.0`` layout fails with the migration spelled
  out. For ``0.1.0``: rename ``sections:`` to ``tabs:`` and remove
  the ``toc:`` key (tabs are the navigation). For ``0.2.0``: the
  file is otherwise current — ``0.3.0`` adds the ``states``
  composition node and changes nothing else. Then set
  ``schema_version: "0.3.0"``.
* An opening ``{`` outside states teaches at load in placement titles,
  parameters, and card titles. Valid markdown variables in
  string-valued ``core.markdown.text`` are the component-owned exception.
* Report identity strings and tab titles cannot be bound by states;
  their orphan-brace teaching requires literal text, not a wrapping node.
* Placement ids cannot contain placeholders, even inside states.
* Declared theme, logo, and favicon paths are resolution strings:
  they are not states templates and are not orphan-checked. They
  must satisfy their own build-time resolution rules.
* Everything else is standard YAML — the loader never silently
  reinterprets what the author wrote (:doc:`api/layout_loader`).

An example layout
.................

.. code-block:: yaml

   schema_version: "0.3.0"
   title: Run summary
   tabs:
     - title: Headlines
       components:
         - id: core.kpi
           title: Mean depth
           parameters:
             artifact: org.example.sample_metrics
             key: depth
             unit: x
         - type: diagnostics

The layout example addresses the manifest example's artifact type.
The declared artifact file must contain the ``depth`` key and match
its recorded checksum for the component to render successfully.

For a complete shipped states bundle, see the optional two-batch
outcome in :doc:`../../tutorials/hello-report`.

The theme file
--------------

The layout's ``theme:`` key is the only door to the theme file.
Omitted, the report renders with the built-in default theme (and a
diagnostic noting it); declared, the file must load — the same
declared-then-strict rule as ``logo`` and ``favicon``.

Structure
.........

.. list-table::
   :header-rows: 1
   :widths: 16 10 24 50

   * - Key
     - Required
     - Shape
     - Meaning
   * - ``name``
     - yes
     - non-empty string
     - The theme's human