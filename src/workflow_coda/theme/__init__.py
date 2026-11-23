"""Design-token themes for generated workflow-coda reports.

Import the theme model, constrained types, and default theme from this
package directly. The submodule layout is an implementation detail
and may change without notice.
"""

from typing import Final

from .bundled import _load_bundled_theme
from .model import (
    CORE_COLOR_TOKENS,
    ColorHex,
    FontStack,
    Theme,
    ThemeToken,
)

DEFAULT_THEME: Final[Theme] = _load_bundled_theme("default")
"""The bundled default theme, used when no theme is selected."""

__all__ = [
    "CORE_COLOR_TOKENS",
    "DEFAULT_THEME",
    "ColorHex",
    "FontStack",
    "Theme",
    "ThemeToken",
]
