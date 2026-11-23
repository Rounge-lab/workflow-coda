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

Default theme
-------------

.. autodata:: workflow_coda.theme.DEFAULT_THEME

The default is loaded from the bundled ``default.yaml`` declaration.
It remains the shared default used when no theme is selected.

.. theme-colors::
