Composing reports
=================

A pipeline run produces a *manifest*: machine-written data
describing what happened — which artifacts were produced, which
passed or failed.  A report is composed from that data by a
*layout*: a small, human-authored YAML file declaring what the
report shows — its title and branding, and an ordered list of
sections, each placing the components that appear in it.  The
manifest is written by the pipeline; the layout is written by you.

The layout is the framework's most human-facing input, and its
design rules follow from that.  Everything is declared in plain
words.  Every mistake produces an error naming the file, the spot
inside it, and the fix.  And nothing you wrote is silently
reinterpreted.

This page covers authoring the layout file and building a report
from it.  The Plugins page describes how components come to exist;
this page describes how you place them.

The layout file
---------------

A complete layout:

.. code-block:: yaml

   schema_version: "0.1.0"
   title: Metagenomic analysis — run ABC123
   subtitle: Sequencing depth and taxonomic composition
   theme: themes/ntnu.yaml
   logo: assets/ntnu_logo.png
   favicon: assets/favicon.ico
   on_missing: notice

   sections:
     - title: Quality control
       components:
         - id: example_bio.qc
           parameters:
             min_depth: 10
             show_legend: true
     - title: Taxonomy
       components:
         - id: virmake.abundance
           parameters:
             min_abundance: 0.01

Only ``schema_version``, ``title``, and ``sections`` are required.
The minimal report:

.. code-block:: yaml

   schema_version: "0.1.0"
   title: Metagenomic analysis
   sections:
     - title: Quality control
       components:
         - id: example_bio.qc

The file is conventionally named ``report_layout.yaml`` and lives
next to the theme and images it references; any path works.

The fields:

``schema_version``
   The layout contract's own version — currently ``"0.1.0"``.
   This is a different axis from the manifest's schema version,
   which gates plugins; the two are never compared.

``title``, ``subtitle``
   The report's title and optional one-line subtitle.  Both must
   contain visible text — a whitespace-only value here is always an
   authoring mistake.

``author``
   Optional free-form author line shown in the report footer — a
   person, a group, several names; whatever should be credited.

``theme``
   Optional path to a theme file, relative to the layout file.
   Omitted, the report renders with the built-in default theme and
   the diagnostics explain how to declare one.  Declared, the file
   must load — see `Theme and branding`_.

``logo``, ``favicon``
   Optional paths to images, relative to the layout file, embedded
   into the report.  Same declared-or-diagnostic rule as the theme.

``toc``
   Whether the report includes a table of contents — a navigation
   list linking to each section.  The default is ``true``.
   ``toc: false`` turns it off (``toc: no`` also works — the one
   place YAML's boolean ``no`` is exactly what you mean).

``on_missing``
   What happens when a placement names a component no loaded
   plugin supports for this manifest.  One of ``fail``, ``notice``
   or ``skip``; the default is ``fail``.  See
   `When a component is missing`_.

Sections and placements
-----------------------

A report is an ordered list of sections; each section is a title
plus an ordered list of *placements*.  A placement names one
component by its globally unique id — ``example_bio.qc`` is the
``qc`` component of the ``example_bio`` plugin — with two optional
fields:

``parameters``
   Values handed to the component's render call; see
   `Parameters: transport, not interpretation`_.

``on_missing``
   Per-placement override of the layout-level policy.

A placement is an *instance*, not a reference: the same component
may be placed twice, in the same or different sections, each time
with its own parameters — one component with two parameterizations
is a feature, not a conflict.

A section must list at least one component.  To remove a section
temporarily, comment out the whole block, title line included:

.. code-block:: yaml

   #  - title: Quality control
   #    components:
   #      - id: example_bio.qc

Parameters: transport, not interpretation
------------------------------------------

Parameters travel to the component's render call *exactly as
written*:

.. code-block:: yaml

   - id: example_bio.qc
     parameters:
       min_depth: 10
       show_legend: true
       min_abundance: 0.01

``10`` stays an integer, ``true`` stays a boolean, ``0.01`` stays
a float.  The framework interprets none of the keys; each plugin
reads and validates the keys it cares about.  A boolean parameter
like ``show_legend: true`` is correct YAML and arrives as a
boolean.

Because parameters travel as *JSON-compatible* values, YAML's
richer types are rejected with an error naming the field — write
a date as text and let the plugin parse it:

.. code-block:: yaml

   - id: example_bio.qc
     parameters:
       cutoff_date: "2026-10-12"   # text; the plugin parses it

YAML notes for authors
----------------------

Comments start with ``#`` and work everywhere.  Two traps are
worth knowing; the loader catches both with an explanation:

* **Bare ``no``, ``yes``, ``on``, ``off``, ``true``, ``false`` are
  booleans in YAML** — ``title: no`` is the boolean ``False``, not
  the word "no".  Quote the word to make it text: ``title: "no"``.
  When a boolean lands where text was expected, the error shows
  the quoting rule with an example.
* **Duplicate keys are rejected.**  Plain YAML keeps only the last
  occurrence without an error — a block pasted twice would
  silently swallow half your report.  The loader refuses the
  file, naming the key and its line.

When a component is missing
---------------------------

A placement names a component; whether it resolves depends on the
installed plugins *and* the manifest — plugins declare the
manifest schema versions they support, and only supporting plugins
render.  The ``on_missing`` policy decides what an unresolvable
placement does:

``fail``
   The build fails with an explanation.  The default, because an
   unknown id in a layout you just wrote is an authoring bug — and
   the error teaches: it lists the component ids that *are*
   available.
``notice``
   The report builds without the component; the diagnostics
   section records which component was omitted and why.  The
   shared-layout scenario: one layout serving runs whose installed
   plugins vary.
``skip``
   The component is omitted silently.

The layout-level ``on_missing`` is the default; a placement's own
``on_missing`` overrides it:

.. code-block:: yaml

   sections:
     - title: Optional extras
       components:
         - id: example_bio.provenance
           on_missing: skip

The explanation distinguishes the two ways a component can be
unresolvable.  An unknown id lists what is available.  An id whose
plugin exists but supports only older manifest schema versions
names the plugin and both sides' versions — so "the plugin needs
an update" and "the layout has a typo" are told apart.

Theme and branding
------------------

``theme``, ``logo`` and ``favicon`` follow one rule: **declared,
then strict**.  Omitted, the report renders with the built-in
default theme and no logo or favicon, and the diagnostics explain
how to declare each.  Declared, the build fails — with an error
naming the file and the fix — unless it loads:

* the theme file must be readable, valid YAML with unique keys,
  and a valid theme (a mapping of theme tokens; see the theming
  documentation);
* the logo and favicon must exist next to the layout file, have a
  supported image extension — ``png``, ``jpg``, ``jpeg``, ``gif``,
  ``svg``, ``ico`` or ``webp`` — and actually be that image type
  (checked by file signature, not by extension alone).

Assets are embedded into the report as data URIs at build time.
The finished report is one self-contained HTML file; it references
no files that only the build machine could resolve.

Building a report
-----------------

Building is one call — the manifest's artifact store, the layout
file, and the installed plugins:

.. code-block:: python

   from pathlib import Path

   from workflow_coda.artifact_store import ArtifactStore
   from workflow_coda.builder import build_report

   store = ArtifactStore.from_manifest_file("artifacts/report_manifest.json")
   document = build_report(Path("report_layout.yaml"), store)

The build:

1. loads and validates the layout file;
2. loads the installed plugins and gates them by the manifest's
   schema version;
3. loads the theme and embeds the declared assets;
4. resolves every placement, applying the missing policy;
5. renders each resolved component — the plugin's render call,
   with the report's render context (the artifact store and the
   theme) and the placement's parameters;
6. assembles the result into a *report document*: the complete,
   resolved content of the report.

What can fail, and whose fix it is:

* ``LayoutError`` — the layout file, the theme file it declares,
  or a declared asset is unreadable or invalid.  An authoring
  failure: fix the file, build again.
* ``PluginLoadError`` / ``PluginConflictError`` — the installed
  plugin environment is broken.  A plugin's problem, not the
  layout's.
* ``ComponentUnavailableError`` — the ``fail`` policy met an
  unresolvable placement; the message explains, as above.
* **A plugin bug never fails the build.**  A render call that
  raises is caught, recorded as a failed entry in place — the
  section shows where the component would have been — and the
  details go to diagnostics.

The document's diagnostics carry two groups of entries.
*Informational*: the report is complete and the entry explains
what was left out (default theme, no logo, no favicon).
*Problems*: an excluded plugin, an omitted component under the
``notice`` policy, or a plugin bug.  Sections whose placements all
resolved away are dropped — an empty titled header would look
broken, and the diagnostics already explain the absences.

The document itself holds everything, resolved: the theme, the
embedded assets, the manifest (for the provenance footer), and
the sections with each component's render outcome or failure.  It
holds no paths and no plugin references — nothing that only the
build machine could resolve.

Testing a layout
----------------

Layout validation is pure data, so it tests cheaply.  Constructing
the layout models from payload dictionaries exercises every shape
rule; loader tests write real YAML files and pin the teaching
messages; and ``build_report`` accepts a fixed registry, so a
build test needs no installed plugins — construct plugins in the
test and inject them.  The framework's own suite works exactly
this way.
