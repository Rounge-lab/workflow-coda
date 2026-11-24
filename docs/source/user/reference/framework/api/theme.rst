Theme
=====

.. automodule:: workflow_coda.theme

Token aliases
-------------

.. autodata:: workflow_coda.theme.ColorHex
.. autodata:: workflow_coda.theme.ThemeToken
.. autodata:: workflow_coda.theme.FontStack
   :no-value:

Core tokens and model
---------------------

.. autodata:: workflow_coda.theme.CORE_COLOR_TOKENS

.. autoclass:: workflow_coda.theme.Theme
   :members:
   :exclude-members: model_config

Discovery and loading
---------------------

Bundled themes are framework-owned YAML assets. Their filename stems
form the selection vocabulary; the declaration's ``name`` is a
human-readable display name and need not match its filename.

.. autofunction:: workflow_coda.theme.bundled_theme_names

.. autofunction:: workflow_coda.theme.load_bundled_theme

.. autofunction:: workflow_coda.theme.load_theme

``load_bundled_theme`` accepts a bundled selection name, not a file
path. Unknown names raise ``ValueError``; missing, unreadable, or
invalid bundled assets raise
:class:`~workflow_coda.errors.FrameworkAssetError`, indicating a
broken installation.

``load_theme`` accepts a custom file path. Read, parse, and validation
failures raise :class:`~workflow_coda.errors.LayoutError`.

Each load returns a freshly validated theme. Layout-relative path
resolution and the choice between bundled names and custom paths
belong to the report builder; see the
:doc:`theme schema <../../schemas/theme>`.

Resolved pairs and mode-aware colors
------------------------------------

The report builder resolves the layout's two selections into a
``ThemePair``. ``RenderContext.theme`` carries this pair, not a
single ``Theme``.

.. autoclass:: workflow_coda.theme.ThemeColors
   :members:

.. autoclass:: workflow_coda.theme.ThemePair
   :members:

Use ``pair.light`` or ``pair.dark`` when constructing styling for one
specific mode. Pair-level color resolution returns the two resolved
values together.

For HTML and CSS, prefer validated CSS references rather than
embedding one member's hexadecimal value:

.. autofunction:: workflow_coda.theme.color_css

.. autofunction:: workflow_coda.theme.plate_inks

Figure update bindings
----------------------

.. autoclass:: workflow_coda.theme.FigureStyle
   :members:

.. autoclass:: workflow_coda.theme.FigureTheme
   :members:

Default themes
--------------

.. autodata:: workflow_coda.theme.DEFAULT_THEME

.. autodata:: workflow_coda.theme.DEFAULT_DARK_THEME

.. autodata:: workflow_coda.theme.DEFAULT_THEME_PAIR

The individual defaults are loaded from the bundled ``default.yaml``
and ``default-dark.yaml`` declarations. ``DEFAULT_THEME_PAIR`` is the
shared pair used when a layout omits its theme selection.

See :doc:`../../themes` for previews and palettes of all bundled declarations.
