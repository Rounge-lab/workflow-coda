"""Design-token themes for generated workflow-coda reports.

Import the theme model, constrained types, and default theme from this
package directly. The submodule layout is an implementation detail
and may change without notice.
"""

from typing import Final

from .bundled import (
    _load_bundled_theme,
    bundled_theme_names,
    load_bundled_theme,
)
from .loader import load_theme
from .model import (
    CORE_COLOR_TOKENS,
    ColorHex,
    FontStack,
    Theme,
    ThemeToken,
)
from .pair import ThemeColors, ThemePair

DEFAULT_THEME: Final[Theme] = _load_bundled_theme("default")
"""The bundled default theme, used when no theme is selected."""

DEFAULT_DARK_THEME: Final[Theme] = _load_bundled_theme("default-dark")
"""The bundled dark default theme."""

DEFAULT_THEME_PAIR: Final[ThemePair] = ThemePair(
    light=DEFAULT_THEME,
    dark=DEFAULT_DARK_THEME,
)
"""The browser-selectable default light/dark pair."""

__all__ = [
    "CORE_COLOR_TOKENS",
    "ColorHex",
    "DEFAULT_DARK_THEME",
    "DEFAULT_THEME",
    "DEFAULT_THEME_PAIR",
    "FontStack",
    "Theme",
    "ThemeColors",
    "ThemePair",
    "ThemeToken",
    "bundled_theme_names",
    "load_bundled_theme",
    "load_theme",
]
