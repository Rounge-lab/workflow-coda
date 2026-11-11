===========
core.notice
===========

One block of author prose with a stance — a note, a success, a
warning, a failure — rendered as a card in the framework's own
notice vocabulary, optionally collapsed behind its title.
``core.notice`` is a TILE component: it paints its own card as a
native ``<details>`` disclosure whose ``<summary>`` is the card's
header, and the framework contributes only the ``data-component``
wrapper around the healthy render.

The stance is the border, and the border is a theme token: the
levels wear the same ``coda-card--<level>`` family the framework's
degradation cards wear — an unavailable outcome is a notice, a
plugin bug a failure — so the author's judgments and the
framework's read as one language on any theme.

Identity
--------

* **Id:** ``core.notice``
* **Default title:** ``Notice``; the placement's ``title`` key
  overrides it for that instance
* **Description:** author prose with a stance — note, success,
  warning, or failure — optionally collapsed
* **Chrome mode:** ``TILE`` — the component paints its own card as
  a native disclosure; degradation is the framework's (see
  `Outcomes and chrome`_)

Placing it
----------

.. code-block:: yaml

   schema_version: "0.2.0"
   title: Sample QC
   tabs:
     - title: Samples
       components:
         - id: core.notice
           title: Column guide
           parameters:
             collapsed: true
             text: |
               `sample_id`
               : The producer's sample identifier.

               `depth`
               : Mean sequencing depth for the sample.

A placement carries the component id, an optional per-instance
``title``, and the component's ``parameters``.  The two placement
gates — ``on_missing`` and ``on_unavailable`` — decide what happens
when things are absent; they are placement keys, siblings of
``id`` and ``title``, never parameters, and shared by every
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
   * - ``level``
     - no — default ``note``
     - ``note`` | ``success`` | ``warning`` | ``failure``
     - The stance, worn as the card's left border through the
       framework's notice family.
   * - ``color``
     - no
     - theme token
     - The note level's border color, resolved from the report's
       theme — never a literal.  Pairs with ``level: note`` only,
       and never ``success``, ``warning``, or ``danger``, which
       would forge a status.
   * - ``collapsed``
     - no — default ``false``
     - boolean
     - Whether the card starts collapsed.  The initial state only:
       the summary row is always the toggle.
   * - ``text``
     - yes
     - non-empty string
     - The notice's prose, written in the prose subset
       (:doc:`markdown`) — definition lists included.

Three rules apply:

* ``color`` pairs with ``level: note``; the judgment levels wear
  their own theme tokens and refuse it.
* ``color`` may not name ``success``, ``warning``, or ``danger``.
* ``text`` is static authorship: template variables teach
  toward ``core.markdown``, which resolves them from a declared
  artifact.

A notice reads no artifacts, so the grammar has no data half:
``level`` is the author's judgment, ``color`` presentation, and
``text`` authorship — which is also why the component's outcome
family is the roster's smallest.

Semantics
---------

The notice family
.................

The levels map one-to-one onto the framework's card family classes
and the theme's judgment tokens: ``note`` wears ``muted``,
``success`` wears ``success``, ``warning`` wears ``warning``, and
``failure`` wears ``danger`` — the same classes the framework's own
degradation cards wear, and the same judgment vocabulary
``core.kpi``'s threshold policy assigns (``ok`` → ``success``,
``notice`` → ``warning``, ``failure`` → ``danger``).  The stance is
the border, and the border is a theme token, so the family reads
coherently on any theme.

``note`` alone makes no semantic claim, so it alone accepts
``color``: a theme token named by the author — ``primary``,
``accent``, any extra token the theme declares — rendered inline
as the border's color.  The judgment levels refuse it, and the
reserved tokens teach rather than render: a note wearing ``danger``
would be a failure the author never judged.

The collapse
............

The disclosure is native ``<details>``/``<summary>``: the toggle,
the keyboard behavior, and the expanded-state announcement are the
browser's own, and the component declares no script — a reader
without scripting gets the complete behavior.  ``collapsed`` sets
the initial state only; the summary row is always the toggle, so
readers close an open notice as readily as they open a closed one.
The summary carries the placement's resolved title beside a
CSS-drawn chevron that follows the card's ink.  The printed page
honors the state: a notice expanded at print time prints its whole
content, a collapsed one its summary.

The prose body
..............

The body parses through the same strict subset as ``core.markdown``
(:doc:`markdown`) — the same teachings, the same walk.  A link in a
notice teaches exactly as it does in prose; a definition list
renders as the term-and-description block it is, the reference
construct for column guides and glossaries.  A notice is prose with
a stance, nothing more.

Outcomes and chrome
-------------------

**Authoring errors** are facts about the layout.  An unknown key
(with a suggestion), a placement key nested in ``parameters:``, a
``level`` outside the vocabulary, ``color`` outside its rules, a
template variable in static text, or an out-of-subset construct —
each teaches where it is found and lands as a *plugin failure*: the
framework's failure card in place with the teaching message, and a
``plugin_bug`` diagnostic.  Fix the layout.

The notice produces ``ok`` outcomes only: it reads no artifacts,
so nothing about a run can be missing.  ``unavailable`` and
``skipped`` are part of the component vocabulary but not this
component's behavior.

Its page chrome is self-hosted through the component channel: the
prose vocabulary's stylesheet concatenated with the notice's own
rules inlines once per report, in first-placement order, exactly
when at least one notice placement renders ``ok`` — landing after
the framework stylesheet under the ``/* core.notice */`` banner.
A page that renders both ``core.markdown`` and ``core.notice``
carries the prose rules under two banners — CSS is idempotent, and
a notice-only page still styles its prose.  The component declares
no script: the collapse is native.

Honest boundaries
-----------------

* The framework cannot judge the stance's truth.  ``level`` is the
  author's claim, honest only if the author verified it; the
  framework renders the claim faithfully.  A derived level — judged
  from an artifact, the pattern ``core.kpi``'s thresholds already
  own — is a parked extension, designed to arrive with values from
  the same artifact riding the text, so facts and stance can only
  agree.
* Static text is why the level is static too.  A data-derived
  border under author-static words could lie — the border would
  change with the run while the words stood still, a failure edge
  over "every sample cleared."

Example
-------

A layout placement — no manifest declaration, because a notice
reads no artifacts:

.. code-block:: yaml

   - id: core.notice
     title: Column guide
     parameters:
       collapsed: true
       text: |
         `sample_id`
         : The producer's sample identifier.

         `depth`
         : Mean sequencing depth for the sample.

         `status`
         : The QC verdict: `passed`, `failed`, or `pending`.
