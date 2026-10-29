========
core.kpi
========

``core.kpi`` renders one artifact-backed headline number — a depth,
a runtime, a count — as a big value with an optional unit, an
optional author caption, and an optional icon, on an optional colored
plate.  It is a ``TILE`` component: it paints its own card, title
included, and the framework contributes only the ``data-component``
wrapper around the healthy render.

Identity
--------

* **Id:** ``core.kpi``
* **Default title:** ``Key metric``; the placement's ``title`` key
  overrides it for that instance
* **Description:** one artifact-backed headline number
* **Chrome mode:** ``TILE`` — the component paints its own card;
  degradation is the framework's (see `Outcomes and chrome`_)

Placing it
----------

.. code-block:: yaml

   schema_version: "0.2.0"
   title: Run summary
   tabs:
     - title: Headlines
       components:
         - id: core.kpi
           title: Mean depth
           parameters:
             artifact: org.example.stats
             key: depth
             unit: x

A placement carries the component id, an optional per-instance
``title``, and the component's ``parameters``.  The two placement
gates — ``on_missing`` and ``on_unavailable`` — decide what happens
when things are absent; they are placement keys, siblings of
``id`` and ``title``, never parameters, and shared by every
component: described once in :ref:`Placement gates <core-placement-gates>`.

Parameters
----------

The parameter grammar follows the honest-data law, and the
vocabulary is closed: every key the KPI reads is in the table, and
an unknown key — a typo, or a placement key nested by accident —
raises a teaching error naming the accepted vocabulary and, when
close, the nearest match.

.. list-table::
   :header-rows: 1
   :widths: 16 14 26 44

   * - Key
     - Required
     - Shape
     - Meaning
   * - ``artifact``
     - yes
     - non-empty string
     - The artifact's *type*, as the manifest declares it.  The
       artifact must be JSON.
   * - ``key``
     - yes
     - non-empty string
     - A dotted key path into the artifact's JSON payload; it must
       land on a scalar (a string or a number).
   * - ``variant``
     - no — default ``text``
     - ``text`` | ``fill`` | ``gradient``
     - The plate: none, one solid color, or a two-color gradient.
   * - ``color``
     - no
     - theme token or ``series-N``; a two-entry list with
       ``gradient``
     - The plate color (or gradient stops), or the value's ink for
       ``text``; always resolved from the report's theme, never a
       literal.
   * - ``thresholds``
     - no
     - object: ``ok`` and/or ``notice``, each with optional
       inclusive ``above`` and ``below``
     - The author's policy for when the number counts as good.
   * - ``unit``
     - no
     - non-empty string
     - Shown after the value, smaller.
   * - ``decimals``
     - no
     - non-negative integer
     - Rounds a numeric value for display.
   * - ``caption``
     - no
     - non-empty string
     - Author prose under the value — honest because visibly prose.
   * - ``icon``
     - no
     - non-empty string
     - A shipped icon name (``core-arrow-up`` and friends).
       User-supplied SVG icons are a planned extension.
   * - ``icon_position``
     - no — default ``inline``
     - ``inline`` | ``corner``
     - In the value line, or pinned to the card's top-right corner.

Three variant/color rules apply:

* ``gradient`` requires ``color`` as a two-entry list
  ``[from-color, to-color]``.
* ``color`` as a two-entry list is only valid with ``gradient``.
* ``fill`` requires ``color`` — or a ``thresholds`` policy, whose
  status supplies one.

Semantics
---------

Reading the value
.................

The value is data.  ``artifact`` addresses the report's
:py:class:`~workflow_coda.artifact_store.ArtifactStore`; ``key``
walks the JSON payload; the KPI shows the scalar it lands on.
Strings render verbatim — the producer's own formatting is data —
numbers stringify honestly, and ``decimals`` rounds for display when
the author asks.

Thresholds
..........

Bounds are inclusive: ``above`` means *at or above*, ``below`` means
*at or below*:

.. code-block:: yaml

   thresholds:
     ok: {above: 10, below: 1000}
     notice: {above: 5}

The policy evaluates ``ok`` first, then ``notice``; a value matching
neither is ``failure``.  An empty ``thresholds`` object — policy
declared, nothing judged — is a teaching error, and so are
thresholds on a text value: policy cannot compare prose.  A declared
status rides the card as ``coda-kpi--<status>`` and, when the author
declared no explicit ``color``, supplies it — the ``fill`` plate, or
the ``text`` variant's value ink — from the theme's judgment
vocabulary: ``ok`` wears ``success``, ``notice`` wears ``warning``,
``failure`` wears ``danger``.

Colors
......

Colors resolve from the report's
:py:class:`~workflow_coda.theme.Theme` — never literals.  A single
color is a theme token (any token the theme declares, e.g.
``primary``) or a categorical-palette entry (``series-1`` … bounded
by the palette's length); gradient stops resolve the same way, one
entry each.  On a plate, the ink is the theme's own light-or-dark
text choice for that background.

Icons
.....

Icons load from the report build's icon library through the render
context — every installed plugin's shipped, namespaced, sanitized
icons — so the report stays self-contained; ``inline`` sits in the
value line, ``corner`` pins to the card's top-right.

Outcomes and chrome
-------------------

The KPI's two failure families are kept distinct.

**Missing data** is a fact about the run.  An artifact type the
manifest does not declare, or a key path the payload does not carry,
raises :py:class:`~workflow_coda.errors.ArtifactUnavailableError`
and renders the *unavailable notice* under the placement's
``on_unavailable`` policy — the framework's notice card in place,
headed by the same resolved title, carrying the store's own message.

**Authoring errors** are facts about the layout.  Every malformed
parameter — an unknown key, a wrong shape, ``thresholds`` on a text
value, a non-JSON artifact, a key that lands on a non-scalar —
teaches where it is found and lands as a *plugin failure*: the
framework's failure card in place with the teaching message, and a
``plugin_bug`` diagnostic.  Fix the layout.

Checksum and read failures — a corrupt or unreadable artifact —
propagate as plugin failures too: a corrupt artifact is the manifest
lying, never a quiet notice.

The KPI produces ``ok`` or ``unavailable`` outcomes; ``skipped`` is
part of the component vocabulary but not this component's behavior.
Its page chrome is self-hosted through the component channel: the
card stylesheet inlines once per report, in first-placement order,
exactly when at least one KPI placement renders ``ok`` — landing
after the framework stylesheet under the ``/* core.kpi */`` banner —
and a report without healthy KPI placements carries no KPI styles at
all.  The component declares no script: a KPI is static content.
