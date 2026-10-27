=======
Schemas
=======

The report framework reads two versioned files — the **manifest**,
the stable interface an artifact producer (the pipeline) writes, and
the **layout**, the report author's composition of the report — and,
when the layout declares one, a **theme** file of design tokens.
This page documents all three as the files are written — the wire
grammar, every field, its shape, and its meaning.  The same models
are documented for plugin developers as the Python API:
:doc:`api/manifest` and :doc:`api/layout`.

Every model is strict: unknown keys are rejected and values are
never coerced, and the two versioned files gate their versions — a
file written against an unknown schema version fails validation,
because an unrecognized document cannot be validated or consumed
correctly.  The theme file has no version to gate: it is a data file
of design tokens, validated by shape alone.

The report manifest
-------------------

The manifest is a small JSON file the pipeline writes next to the
artifacts it produced, declaring who produced them and where each
artifact file lives with its claimed shape and status.  Loading
validates the envelope only: artifact files are never touched until
a component reads one (:doc:`api/artifact_store`).  The manifest's
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
     - the literal ``"0.2.0"``
     - The envelope contract version this file complies with; an unknown version
       fails with the declared and expected versions named. Version 0.2.0
       widened the artifact format`` value space to include namespaced plugin
       formats.
   * - ``producer``
     - yes
     - object
     - The workflow or application that produced the manifest and
       its artifacts (the table below).
   * - ``artifacts``
     - yes
     - list of objects; may be empty
     - The artifact declarations, in declaration order.  Artifact
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
       ``org.example.sample_metrics``.  Components address artifacts
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
       (``core.table``, ``bio.newick``)
     - The artifact's format — a claim, not a service.  ``json`` is
       an interpreted claim with a store reader; ``txt`` and
       ``bytes`` are interpretation-free (UTF-8 text, raw bytes) for
       consumers with their own parsers.  A namespaced name is a
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

``complete`` is the only status guaranteed to be loadable.
``partial``, ``failed``, and ``missing`` describe artifacts a
partial or failed run declared but did not fully produce — expected
missing data, never fatal report-build errors.

Loading rules
.............

A manifest whose declared schema version is not 0.2.0 fails with the declared
and expected versions named, before envelope validation.
The loader reads the file as strict UTF-8 (a byte-order mark is
rejected with instructions), parses it as JSON, and validates the
envelope.  Every failure — unreadable, invalid JSON at a named line
and column, or an envelope violation — is one teaching error with
the file path for context (:doc:`api/manifest`).

An example manifest
...................

.. code-block:: json

   {
     "schema_version": "0.2.0",
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
         "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
       }
     ]
   }

The report layout
------------------

The layout is the report author's file: the report's identity, and
an ordered list of *tabs*, each composing components through a small
layout grammar.  The layout's version is an axis entirely distinct
from manifest versions — the two are never compared.

The grammar's front door is shape dispatch: a node carrying ``id``
is a *placement* — one component instance; a node carrying
``type`` is a *composition* — ``row``, ``grid``, ``card``, or
``diagnostics``.  A node carrying both is a teaching error, as is a
node carrying neither.  Nodes nest: a tab's list, a row's, a grid's,
and a card's children all speak the same grammar.

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
     - the literal ``"0.2.0"``
     - The layout contract version; a ``0.1.0`` file fails with the
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
       diagnostic).  Declared, the file must load — the theme file's
       grammar is documented in its own section below.
   * - ``logo``
     - no
     - relative path
     - Logo image; omitted renders without one (with a diagnostic
       explaining how to add one).  Embedded as a data URI at build
       time.
   * - ``favicon``
     - no
     - relative path
     - Same declared-then-strict rule as ``logo``.
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
     - The report's tabs, in declaration order; each becomes one
       panel, and the tab bar is generated from them.

``theme``, ``logo``, and ``favicon`` follow one rule: **declared,
then strict** — omitted is a valid, diagnostic-noted absence;
declared means the file must exist and load.  The report never
references external files: declared assets are embedded as data
URIs at build time, so the written page is self-contained.

Tabs and placements
...................

A tab is a titled composition: ``title`` (visible text, its label in
the tab bar) and ``components`` (at least one node — an empty tab is
rejected; comment out the whole tab while composing).  A
single-tab report renders no tab bar.

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
       default; absent means inherit.
   * - ``parameters``
     - no
     - object (default ``{}``)
     - Transport: values pass to the component's render call exactly
       as written.  The framework interprets none of them; each
       plugin reads its own keys.  Values must be JSON-compatible —
       YAML's richer types (dates, sets, binary) are rejected,
       naming the field.
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
       child; omitted, equal widths.  Collapses to one column on
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
       state — an empty ledger shows "no issues".  A report that
       places none shows no diagnostics at all; the builder still
       records everything.

Split ratios
............

``split`` gives width ratios: at least two positive numbers,
relative — ``[2, 1]`` makes the first region twice the second.  A
row takes exactly one ratio per child (or no ``split``, for equal
widths); a grid takes the column ratios and requires them.  Three
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
* A ``0.1.0`` layout fails with the migration spelled out: rename
  ``sections:`` to ``tabs:``, remove the ``toc:`` key (tabs are the
  navigation), and set ``schema_version: "0.2.0"``.
* Everything else is standard YAML, preserved exactly as written —
  the loader never silently reinterprets what the author wrote
  (:doc:`api/layout_loader`).

An example layout
.................

.. code-block:: yaml

   schema_version: "0.2.0"
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

The layout example reads the manifest example's artifact — the two
files are a buildable pair.

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
     - The theme's human-readable name (the default-theme
       diagnostic names it).
   * - ``colors``
     - yes
     - object: token → ``#rrggbb``
     - The design tokens.  Must declare every core token (below);
       may declare additional tokens, each emitted as a CSS custom
       property for styles and plugins to use.
   * - ``series``
     - yes
     - list of at least two colors
     - The categorical palette for plots and repeated-color
       contexts; entries emit as ``--coda-series-N``, 1-based.
   * - ``font_body``
     - no
     - CSS ``font-family`` list
     - The report body font; defaults to the system stack.  Family
       names only — ``url(...)`` fetches are refused: reports are
       self-contained and load no fonts.
   * - ``font_heading``
     - no
     - CSS ``font-family`` list
     - The heading font; defaults to the body stack.

The core color tokens
.....................

Every theme declares these eleven tokens; the required set is
exactly this list.

.. list-table::
   :header-rows: 1
   :widths: 14 86

   * - Token
     - Meaning
   * - ``background``
     - The page background — and the header bar's ink (the bar wears
       ``primary``).
   * - ``surface``
     - Cards', groups', and panels' background.
   * - ``border``
     - Hairlines: card and group borders, section rules, badges.
   * - ``primary``
     - The header bar's color; the theme's principal accent.
   * - ``accent``
     - Interactive highlights (tab hover).
   * - ``success`` / ``warning`` / ``danger``
     - The judgment colors: threshold-supplied plates and inks, the
       notice and failure card rules, problem badges.
   * - ``muted``
     - Secondary ink: footers, diagnostics, notice text.
   * - ``text-dark`` / ``text-light``
     - The ink pair for colored surfaces — see below.

Ink is chosen, not declared
...........................

A single ink color cannot serve every surface it might sit on —
light text fails on light plates, dark text on dark ones — so the
theme declares a *pair*, and the framework picks: WCAG contrast
between each candidate and the surface's luminance, computed at
build time.  Components receive the choice through the render
context — ``theme.text_on(background)`` returns the stronger ink
for one background (a gradient passes both stops); plugin css never
picks its own.

The page's own body ink follows the same rule and is **derived**:
the renderer emits ``--coda-text`` as the pair's contrast winner
against the theme's ``background``, beside one ``--coda-<token>``
per declared color, the ``--coda-series-N`` entries, and the two
font stacks.  The ``text`` token is retired — no longer required,
and themes need not declare it.  A theme that still declares
``text`` keeps its own ink: declared tokens ride through, and the
derivation steps aside.

Loading rules
.............

The theme file is read as UTF-8, parsed through the same strict YAML
loader as the layout — duplicate mapping keys are rejected, and
booleans are booleans — and validated.  Colors are exactly
``#rrggbb`` (six hex digits, case preserved as written); in YAML
the leading ``#`` starts a comment, so colors must be quoted:
``background: "#10141a"``.  Token names are lowercase kebab-case.
Missing core tokens are reported together, sorted; unknown
top-level keys are rejected.  Every failure is one teaching error
naming the theme file and the layout that declared it.

An example theme
................

.. code-block:: yaml

   name: midnight
   colors:
     background: "#10141a"
     surface: "#1a2029"
     border: "#2c3542"
     primary: "#6e91d2"
     accent: "#acc6f5"
     success: "#75a941"
     warning: "#ece860"
     danger: "#d2574c"
     muted: "#8b95a1"
     text-dark: "#10141a"
     text-light: "#f5f7fa"
   series:
     - "#6e91d2"
     - "#f38d4d"
     - "#75a941"

A dark theme, deliberately: the derived body ink is the pair's light
color against the dark ``background``, and no ``text`` token is
declared — the derivation owns it.  Declare it from the layout with
``theme:`` and the path to this file.

The files meet at one command: ``workflow-coda build MANIFEST
LAYOUT`` (:doc:`cli`).
