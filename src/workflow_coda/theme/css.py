"""Validated CSS references for theme-responsive component markup."""

import re
from typing import Final

from .model import ColorHex
from .pair import ThemePair

_SERIES_REFERENCE: Final[re.Pattern[str]] = re.compile(r"^series-(\d+)$")


def color_css(pair: ThemePair, requester: str, raw: object) -> str:
    """Validate one color request in both modes and return its CSS reference.

    Theme.resolve_color owns the request grammar and teaching errors.
    Resolution here validates existence only: the browser's active
    custom properties supply the actual color.

    Series requests normalize their numeric index because the renderer
    emits --coda-series-1, not --coda-series-01.

    ThemePair already requires matching token names and palette lengths.
    Both resolutions are checked explicitly so this boundary continues
    to use each theme's own color grammar and names the failing mode.
    """
    for mode, theme in (("light", pair.light), ("dark", pair.dark)):
        try:
            theme.resolve_color(requester, raw)
        except ValueError as e:
            raise ValueError(f"{mode} theme: {e}") from e

    assert isinstance(raw, str)  # both resolutions accepted the request
    match = _SERIES_REFERENCE.fullmatch(raw)
    reference = f"series-{int(match.group(1))}" if match else raw
    return f"var(--coda-{reference})"


def plate_inks(
    pair: ThemePair,
    requester: str,
    *references: object,
) -> tuple[ColorHex, ColorHex]:
    """Return light/dark contrast-picked ink for a requested plate.

    One reference describes a solid plate; two describe gradient stops.
    References use the shared theme color grammar, never literal hexes.

    Resolution and contrast selection happen independently in each mode.
    The returned order is always (light ink, dark ink).
    """
    if len(references) not in (1, 2):
        raise ValueError(
            f"{requester}: a plate requires one color reference "
            "or two gradient-stop references"
        )

    def ink(mode: str) -> ColorHex:
        theme = pair.light if mode == "light" else pair.dark
        try:
            backgrounds = tuple(
                theme.resolve_color(requester, reference) for reference in references
            )
            return theme.text_on(*backgrounds)
        except ValueError as e:
            raise ValueError(f"{mode} theme: {e}") from e

    return ink("light"), ink("dark")
