"""Resolved light/dark themes and their shared styling helpers.

These are in-memory contracts, not theme-file schemas. Each member
is an independently validated Theme; the pair adds the compatibility
rules needed for browser-time switching.
"""

from dataclasses import dataclass
from typing import Final

from .model import ColorHex, Theme

_DERIVED_OVERRIDES: Final[frozenset[str]] = frozenset(
    {"text", "header-background", "header-text"}
)
"""Independently optional tokens whose effective CSS properties the
renderer always emits, declared or derived."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ThemeColors:
    """One resolved color for each mode."""

    light: ColorHex
    dark: ColorHex


@dataclass(frozen=True, slots=True, kw_only=True)
class ThemePair:
    """Two validated themes with a shared styling vocabulary.

    Color-token names must match, except for independently optional
    page-derivation overrides. Series lengths must match so category
    assignment and palette cycling do not change with the mode.
    Names, color values, and font stacks may differ.
    """

    light: Theme
    dark: Theme

    def __post_init__(self) -> None:
        if not isinstance(self.light, Theme) or not isinstance(self.dark, Theme):
            raise ValueError("a ThemePair requires light and dark Theme instances")

        light_tokens = self.light.colors.keys() - _DERIVED_OVERRIDES
        dark_tokens = self.dark.colors.keys() - _DERIVED_OVERRIDES
        if light_tokens != dark_tokens:
            light_only = ", ".join(sorted(light_tokens - dark_tokens)) or "none"
            dark_only = ", ".join(sorted(dark_tokens - light_tokens)) or "none"
            raise ValueError(
                "light and dark themes must declare matching color-token "
                f"names; light-only: {light_only}; dark-only: {dark_only} "
                "— add the missing tokens to the other theme"
            )

        if len(self.light.series) != len(self.dark.series):
            raise ValueError(
                "light and dark themes must have matching series lengths "
                f"(light: {len(self.light.series)}, dark: {len(self.dark.series)}) "
                "— use the same number of categorical colors in both themes"
            )

    def resolve_color(self, requester: str, raw: object) -> ThemeColors:
        """Resolve a reference in both themes, naming the failing mode."""

        def resolve(theme: Theme, mode: str) -> ColorHex:
            try:
                return theme.resolve_color(requester, raw)
            except ValueError as e:
                raise ValueError(f"{e} (in the {mode} theme)") from e

        return ThemeColors(
            light=resolve(self.light, "light"),
            dark=resolve(self.dark, "dark"),
        )

    def css_color(self, requester: str, raw: object) -> str:
        """Validate a shared reference and return its CSS variable.

        Series references are normalized to the renderer's 1-based
        property names: series-01 and series-1 address the same entry.
        Optional derivation overrides must exist in both members
        to be requested through this helper; effective derived page
        properties remain the renderer's responsibility.
        """
        self.resolve_color(requester, raw)
        assert isinstance(raw, str)  # guaranteed by resolve_color
        if raw.startswith("series-") and raw[7:].isdigit():
            raw = f"series-{int(raw[7:])}"
        return f"var(--coda-{raw})"

    def text_on(self, *backgrounds: ThemeColors) -> ThemeColors:
        """Contrast-pick ink independently against each mode's backgrounds."""
        if not backgrounds:
            raise ValueError("text_on requires at least one background color")
        return ThemeColors(
            light=self.light.text_on(*(color.light for color in backgrounds)),
            dark=self.dark.text_on(*(color.dark for color in backgrounds)),
        )
