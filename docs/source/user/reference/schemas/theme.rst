==========
Theme file
==========

A layout declares a theme using its ``theme`` key and a path relative
to the layout. If omitted, the built-in theme is used and a diagnostic
is recorded. If declared, the file must load.

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

Ink is selected from the text pair by contrast against the relevant
surface. The renderer derives ``--coda-text`` against ``background``
and derives header background and text variables from the layout's
``header_color`` token, or ``primary`` by default.

Each declared color is emitted as ``--coda-<token>``; series entries
are emitted as ``--coda-series-N``, starting at 1. If the theme itself
declares ``text``, ``header-background``, or ``header-text``, its
declared value is retained instead of the corresponding derivation.

Loading rules
-------------

The theme is UTF-8 YAML, parsed with the strict layout loader.
Duplicate keys and unknown top-level keys are rejected. Token names are
lowercase kebab-case. Colors contain exactly six hexadecimal digits
after ``#``; quote them in YAML because ``#`` starts a comment.

Missing core tokens are reported together. Loading errors identify the
theme and the layout that declared it. See the
:doc:`theme API <../framework/api/theme>`.

Example
-------

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
