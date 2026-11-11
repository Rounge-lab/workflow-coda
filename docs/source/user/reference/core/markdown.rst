=============
core.markdown
=============

One block of report prose: methodology, conclusions, the
narrative around the numbers — author-written markdown in a
strict subset, with values substituted from one JSON artifact.
``core.markdown`` is a CARD component: the framework paints the
card and the placement's resolved ``title``, the component paints
the body.

The words are the report author's; the values inside ``{{ }}``
are the run's.  A pipeline writes its numbers once — the same
JSON shape ``core.kpi`` (:doc:`kpi`) reads for one headline — and
every sentence that needs them draws from the same artifact.  The
prose subset is fenced by teaching, not silence: tables, links,
images, and raw HTML never render as literal syntax — each
teaches with the move (the data belongs to ``core.table``
(:doc:`table`), navigation to the framework, figures to figure
components).

Identity
--------

* **Id:** ``core.markdown``
* **Default title:** ``Prose``; the placement's ``title`` key
  overrides it for that instance
* **Description:** author-written prose in a strict markdown
  subset, with values substituted from a JSON artifact
* **Chrome mode:** ``CARD`` — the framework paints the card and
  the placement's resolved title; the component paints the body
  alone.  Degradation is the framework's (see
  `Outcomes and chrome`_)

Placing it
----------

.. code-block:: yaml

   schema_version: "0.2.0"
   title: Run summary
   tabs:
     - title: Headlines
       components:
         - id: core.markdown
           title: What ran
           parameters:
             artifact: org.example.stats
             text: |
               We analyzed **{{ n_samples }}** samples during run
               `{{ run_id }}`.

               - host reads removed first
               - low-complexity reads dropped
         - id: core.markdown
           title: Methods
           parameters:
             text: |
               Filtering used the published defaults; no samples
               were excluded by hand.

A placement carries the component id, an optional per-instance
``title``, and the component's ``parameters``.  The two placement
gates — ``on_missing`` and ``on_unavailable`` — decide what
happens when things are absent; they are placement keys, siblings
of ``id`` and ``title``, never parameters, and shared by every
component: described once in :ref:`Placement gates
<core-placement-gates>`.

Parameters
----------

The parameter grammar follows the honest-data law, and the
vocabulary is closed: every key the component reads is in the
table, and an unknown key — a typo, or a placement key nested by
accident — raises a teaching error naming the accepted vocabulary
and, when close, the nearest match.

.. list-table::
   :header-rows: 1
   :widths: 16 14 26 44

   * - Key
     - Required
     - Shape
     - Meaning
   * - ``artifact``
     - no
     - non-empty string
     - The artifact's *type*; must be declared with format
       ``json``.  Omitted, the text renders as static prose —
       but a text that declares ``{{ }}`` variables requires it.
   * - ``text``
     - yes
     - non-empty string
     - The prose itself, written in the subset below.  A YAML
       block scalar (``|``) keeps paragraphs and indentation
       intact.

The honest-data split, as throughout: the artifact's payload is
data — values render as text, never as markup; ``text`` is
authorship, carried whole from the layout; ``artifact`` is the
binding between them.  Placement keys — ``title``,
``on_unavailable`` — live at the placement level, never inside
``parameters:``; a key nested by accident teaches the move.

Semantics
---------

The template language
.....................

A variable is ``{{ name }}`` or ``{{name}}`` — a name, optionally
dotted, resolving against the artifact's top-level JSON object.
Scalars render: strings verbatim (the producer's own formatting is
data), numbers as written, booleans as their JSON literals.
Structure teaches: a variable resolving to null, a list, or an
object is an authoring mistake — the artifact's shape does not fit
the sentence — and the teaching names the variable and its kind.
A variable the artifact does not carry teaches too: the prose
promised a value the artifact does not hold.  And a stray ``{{``
with no closing braces is not a variable at all — it renders as
the characters it is.

Values are text, never markup
.............................

The template parses first; values substitute inside the parsed
content afterwards, escaping per context.  A value carrying
``*stars*`` or ``<tags>`` therefore renders as the characters it
is — data cannot inject presentation, because no re-parse ever
happens.  The same law carries into code: variables substitute
inside code spans and fenced blocks as readily as in text, and
land there as literal characters.

The prose subset
................

What is prose renders:

* **paragraphs** — the base unit; a blank line separates them.
* **headings** — ``##`` through ``####``, rendered one level down
  (``##`` becomes ``h3``): the card's own title is the section's
  heading, so prose headings start at ``##`` and stay below it.
* **strong and emphasis** — ``**bold`` and ``*italic*``.
* **code** — inline code spans and fenced blocks; content
  renders as literal characters, escaped.
* **lists** — ordered and unordered, nested; tight and loose
  lists render per CommonMark's own distinction.
* **definition lists** — a term line, a ``: description`` line
  under it — the reference-prose construct (a column guide, a
  glossary).  Terms are inline content: code spans mark
  identifiers.  Descriptions ride the same inline vocabulary, and
  a term may carry several descriptions.
* **blockquotes** — quotation set off by a hairline, for
  citations.
* **thematic breaks** — ``---`` between paragraphs.

What the framework owns or refuses teaches, each with the move:

* ``#`` headings — the card's title is the section's heading;
  prose sections start at ``##``.  Deeper than ``####`` teaches
  too.
* **links** — the framework owns navigation.
* **images** — figures belong to figure components
  (``core.chart``, or a plugin's).
* **pipe tables** — the data belongs to ``core.table``.
* **raw HTML** — a styling hole the report refuses.

The engine is CommonMark (markdown-it-py), and the fence is the
walk, not the parser: the walk emits an allowlist of token types,
and every other construct teaches by its token name — a parser
update can never silently widen the subset.

Styling
.......

The component styles its own body through its page chrome, scoped
under one class (``coda-prose``) and drawn from theme tokens
alone: ink, hairlines, and code plates recessed one step below
the card's surface.  There is no color parameter to configure —
presentation belongs to the theme, and the prose inherits it.
Headings stay visually below the card's title, carrying the
demotion law into the look.

Outcomes and chrome
-------------------

Three families, kept distinct — who is wrong decides what the
reader sees.

.. list-table::
   :header-rows: 1

   * - Family
     - Raised as
     - Shown as
   * - The layout is wrong: a missing or blank ``text``, an
       unknown key (with a suggestion), a placement key nested in
       ``parameters:``, variables with no ``artifact`` declared, a
       variable resolving to structure, a variable the artifact
       does not carry, an out-of-subset construct (a table, a
       link, an image, raw HTML, a ``#`` heading), variables
       against an artifact whose payload is not an object, or a
       non-``json`` artifact
     - ``ValueError``
     - a plugin failure, collected and shown in place
   * - The run is partial: the artifact is undeclared, declared
       with a non-``complete`` status, or its file is missing
     - ``ArtifactUnavailableError``
     - the unavailable notice card — a fact about the run
   * - The artifact lies about its content: not valid UTF-8, not
       valid JSON, or a failed checksum
     - ``ArtifactReadError`` / ``ArtifactChecksumError``
     - a plugin failure, collected and shown in place

The component produces ``ok`` or ``unavailable`` outcomes;
``skipped`` is part of the component vocabulary but not this
component's behavior.  Its page chrome is self-hosted through the
component channel: the stylesheet inlines once per report, in
first-placement order, exactly when at least one prose placement
renders ``ok`` — landing after the framework stylesheet under the
``/* core.markdown */`` banner — and a report without healthy
prose placements carries no prose styles at all.  The component
declares no script: prose is static content.

Honest boundaries
-----------------

* Author entities survive in text, not in code.  CommonMark
  guarantees no raw ``<`` reaches a text token, so escaping
  ``<`` and ``>`` alone keeps the author's own ``&amp;`` an
  entity.  Code is different by design: its content renders as
  literal characters, so ``&amp;`` inside a code span shows as
  the characters ``&amp;``.  Write entities where they are prose,
  and nowhere.
* The walk cannot refuse what the parser never sees.  A
  construct the grammar does not tokenize renders as the literal
  characters it is — exactly like a stray ``{{``.  The fence is
  the walk's allowlist over the parser's tokens; the in-set list
  above is the vocabulary.

Example
-------

A manifest declaration and a layout placement, together:

.. code-block:: json

   {
     "id": "stats",
     "type": "org.example.stats",
     "schema_version": "1.0.0",
     "path": "stats.json",
     "format": "json",
     "status": "complete"
   }

.. code-block:: yaml

   - id: core.markdown
     title: What ran
     parameters:
       artifact: org.example.stats
       text: |
         ## Headlines

         We analyzed **{{ n_samples }}** samples during run
         `{{ run_id }}`.

         - host reads removed first
         - low-complexity reads dropped
