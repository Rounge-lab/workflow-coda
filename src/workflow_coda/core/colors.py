"""Shared color-grammar resolution for the core components.

The resolution half of the color story, factored out of the two
colored components: a color request arrives as a theme token name
(``primary``) or a categorical-series entry (``series-2``), and
resolves to the theme's own ``#rrggbb`` — never a literal.  The
grammar ``core.kpi`` established and ``core.chart`` reuses; one
implementation, so the two components can never drift apart in
what a color request means.

The theme side of the parse/resolution seam: this module owns the
series pattern and the resolution against
:class:`~workflow_coda.theme.Theme`, so the components' parse
halves stay theme-free and their color stories share one home.
The component id rides as the first argument, the
``reject_unknown_parameters`` precedent, so every teaching names
the component that raised it.

Underscore-private today, with an eventual home flagged: the theme
itself (``Theme.resolve_color``) is the natural promotion, making
the grammar available to every plugin — recorded in the skills
files as a release-train step, not taken silently here.
"""

import re
from typing import Final

from ..artifact_store import JsonValue
from ..theme import ColorHex, Theme

_SERIES_COLOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"^series-(\d+)$")
"""A categorical-palette request: ``series-<n>``, 1-based."""


def _resolve_color(component_id: str, theme: Theme, raw: JsonValue) -> ColorHex:
    """One color request — a theme token or a series entry — to hex.

    The grammar the core components share: a theme token this theme
    declares, or ``series-N`` within this theme's palette.  Every
    failure names the component, the request, and what the theme
    actually offers.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(
            f"{component_id}: 'color' must be a theme color token (e.g. "
            f"'primary') or a series entry like 'series-1', got {raw!r}"
        )
    match = _SERIES_COLOR_PATTERN.fullmatch(raw)
    if match is not None:
        index = int(match.group(1))
        if not 1 <= index <= len(theme.series):
            raise ValueError(
                f"{component_id}: 'color' names {raw!r}, but this theme's "
                f"series palette has {len(theme.series)} colors "
                f"(valid: series-1 to series-{len(theme.series)})"
            )
        return theme.series[index - 1]
    if raw in theme.colors:
        return theme.colors[raw]
    available = ", ".join(sorted(theme.colors))
    raise ValueError(
        f"{component_id}: 'color' must be a theme token this theme "
        f"declares ({available}) or a series entry like 'series-1', "
        f"got {raw!r}"
    )
