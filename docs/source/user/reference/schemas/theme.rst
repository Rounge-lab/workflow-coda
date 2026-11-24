==========
Theme file
==========

A theme file declares one complete palette and its fonts. A layout
selects two such declarations through its ``theme`` key: one for
light mode and one for dark mode.

If ``theme`` is omitted, the bundled ``default`` and
``default-dark`` pair is used and an informational diagnostic is
recorded. Explicitly selecting the default pair does not produce
that omission diagnostic.

Selection
---------

The framework ships these bundled themes:

* ``default``: the light default theme.
* ``default-dark``: its dark counterpart.

A layout selects both members:

.. code-block:: yaml

   theme:
     light: default
     dark: default-dark

Each member may instead select a custom theme file relative to the
layout:

.. code-block:: yaml

   theme:
     light: themes/daylight.yaml
     dark: themes/midnight.yaml

Bundled names and custom paths may be mixed:

.. code-block:: yaml

   theme:
     light: default
     dark: themes/midnight.yaml

Selection follows an explicit shape rule for each member:

* A value containing a dot or a path separator selects a custom file.
* A bare name selects a bundled theme.
* An unknown bundled name fails with the available names; it never
  falls back to a local file.

For an extensionless custom file, use an explicit path such as
``dark: ./midnight``. A bare ``dark: midnight`` requests a bundled
theme named ``midnight``.

Both ``light`` and ``dark`` are required when ``theme`` is declared.
A single name or path is not a paired selection.

Bundled selection names come from YAML filename stems. The ``name``
inside a theme declaration is a human-readable display name, not its
selection identifier.

Custom theme files remain complete, single-theme declarations.
There is no theme inheritance or plugin-contributed theme namespace.

Pair compatibility
------------------

The two declarations must have matching categorical palette lengths
and matching color-token names. The optional derivation overrides
``text``, ``header-background``, and ``header-text`` may be present
independently in either member.

Matching names let components use the same color reference in both
modes. The values, font stacks, and selected inks may differ.

Reader appearance
-----------------

On screen, the report follows the system or browser color preference
until the reader explicitly changes it. The sun/moon button at the
right of the header navigation switches between light and dark mode.
It is also available in single-tab reports.

The choice applies only to the current page. Reloading returns to
system preference; the choice is not stored or added to selection
URLs. Later system-preference changes affect the page only while no
explicit mode is selected.

The button is hidden without JavaScript and when printing. Without
JavaScript, CSS-based report styling still follows system preference;
interactive figure theme updates require JavaScript.

Structure
---------

.. list-table::
   :header-rows: 1

   * - Key
     - Required
     - Shape and meaning
   * - ``name``
     - yes
     - Non-empty human-readable name.
   * - ``colors``
     - yes
     - Mapping from token names to ``#rrggbb`` colors. All core tokens
       below are required; additional tokens are allowed.
   * - ``series``
     - yes
     - List of at least two colors for categorical series.
   * - ``font_body``
     - no
     - CSS ``font-family`` list. Defaults to the system stack.
   * - ``font_heading``
     - no
     - CSS ``font-family`` list. Defaults to the body font.

Font families cannot fetch external resources through ``url(...)``.
Reports are self-contained.

Core color tokens
-----------------

.. list-table::
   :header-rows: 1

   * - Token
     - Meaning
   * - ``background``
     - Page background.
   * - ``surface``
     - Card, group, and panel background.
   * - ``border``
     - Hairlines, rules, and badges.
   * - ``primary``
     - Principal accent and default header background.
   * - ``accent``
     - Interactive highlights.
   * - ``success``, ``warning``, ``danger``
     - Judgment colors.
   * - ``muted``
     - Secondary ink.
   * - ``text-dark``, ``text-light``
     - Candidate inks for colored surfaces.

Color references
----------------

Layouts and components reference theme colors by token name, such as
``primary``, or by categorical palette entry, such as ``series-2``.
Series indices start at 1 and must be within both members' palettes.
References are validated against both members of the pair.
Color literals belong in the theme file, not in layout color
references.

Each declared color is emitted as ``--coda-<token>``; series entries
are emitted as ``--coda-series-N``, starting at 1. The active mode
determines their values, so components using these properties follow
theme changes without being rendered again.

Derived ink and header properties
---------------------------------

Derivations are performed independently for the light and dark
members. A shared layout header configuration can therefore produce
different backgrounds and inks in each mode.
Ink is selected from ``text-light`` and ``text-dark`` by comparing
their contrast against the relevant surface. The renderer derives
``--coda-text`` against the page's ``background`` color.

The :doc:`layout <layout>` controls header presentation through
``header_variant`` and ``header_color``:

* ``fill`` (the default) derives ``--coda-header-background`` from a
  single color reference, using ``primary`` when omitted.
* ``gradient`` derives ``--coda-header-background`` as a 135-degree
  linear gradient from two required color references.

``--coda-header-text`` is selected against the effective header
background. For a gradient, selection uses the mean relative
luminance of both stops, matching ``core.kpi``. This rule selects the
stronger of the two candidate inks against that mean; it does not
guarantee sufficient contrast everywhere along the gradient.

Optional theme tokens override these derivations independently:

.. list-table::
   :header-rows: 1

   * - Token
     - Effect
   * - ``text``
     - Overrides the derived page ink.
   * - ``header-background``
     - Overrides the layout's header background with a solid color,
       including when the layout requests a gradient. Derived header
       ink is selected against this override.
   * - ``header-text``
     - Overrides the selected header ink.

These override tokens follow the ordinary theme color shape:
``#rrggbb``. In particular, ``header-background`` cannot contain a
CSS gradient expression; gradients are declared through the layout.
Layout color references are still validated against the theme when
an override is present.

If the theme itself declares ``text``, ``header-background``, or
``header-text``, its declared value is retained instead of the
corresponding derivation.

Loading rules
-------------

Themes are UTF-8 YAML. Bundled and custom declarations pass through
the same parsing and model-validation boundary. Duplicate mapping
keys and unknown top-level keys are rejected.

Token names are lowercase kebab-case. Colors contain exactly six
hexadecimal digits after ``#``; quote them in YAML because ``#``
starts a comment. Missing core tokens are reported together.

An unreadable or invalid custom theme is an authoring failure:
correct the file and build again. When selected through a layout,
the error names both the theme file and the layout that declared it.

A missing, unreadable, or invalid bundled theme is a framework
installation failure, not a layout mistake; reinstall workflow-coda.
An unknown bundled selection is instead an authoring error and lists
the available names.

See the :doc:`theme API <../framework/api/theme>` for discovery and
loading functions.

Example theme file
------------------

This is one complete dark theme declaration, not a layout selection.
Save it as ``themes/midnight.yaml`` and select it as the layout's
``theme.dark`` member.

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
