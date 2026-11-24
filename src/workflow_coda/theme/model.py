"""Design-token declarations for generated reports.

Each ``Theme`` describes one palette and its font stacks. The report
builder resolves the layout's light and dark selections into a
``ThemePair``, supplied to plugins through ``RenderContext.theme``.
The renderer emits both members as scoped ``--coda-*`` CSS custom
properties; the active appearance determines which values apply.

Themes may declare color tokens beyond the required core set.
Components can use those additional tokens through CSS references
or explicit resolution. Third-party plugins own their presentation
choices; theme-derived colors and contrast-selected ink are
recommended practices, not framework-enforced styling policy.

The theme owns the shared color-reference grammar:
:meth:`Theme.resolve_color` resolves a token name or ``series-N``
entry against one declaration, naming the requester in teaching
errors. :meth:`Theme.text_on` selects between the declaration's
candidate inks by comparing contrast against supplied backgrounds.

Three report properties may be derived independently for each
member: page ink ``--coda-text``, header background
``--coda-header-background``, and header ink ``--coda-header-text``.
The layout controls the derived header presentation. A theme's
explicit declaration of the corresponding token overrides its
derivation.
"""

import re
from typing import Annotated, Final

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from ..manifest import NonEmptyStr
from ..text import has_visible_text


def _require_font_stack(value: str) -> str:
    """Font tokens name families; they never fetch files."""
    if not has_visible_text(value):
        raise ValueError("must contain visible text, not only whitespace")
    if "url(" in value.lower():
        raise ValueError(
            "font tokens must be CSS font-family names, not fetched "
            "files — reports are self-contained and fetch no fonts; "
            "a custom font must be installed or embedded"
        )
    return value


FontStack = Annotated[str, AfterValidator(_require_font_stack)]
"""A CSS ``font-family`` list: family names and fallbacks, never a
fetched file — reports render with the fonts the reading machine has
installed."""

type ColorHex = Annotated[
    str, StringConstraints(strict=True, pattern=r"^#[0-9a-fA-F]{6}$")
]
"""An ``#rrggbb`` color literal, exactly as written in theme files."""

type ThemeToken = Annotated[
    str, StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9-]*$")
]
"""A lowercase kebab-case token name, e.g. ``background`` or ``sample-highlight``."""

_SERIES_COLOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"^series-(\d+)$")
"""A categorical-palette request: ``series-<n>``, 1-based."""

#: Semantic color tokens that every theme must provide.
CORE_COLOR_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "accent",
        "background",
        "border",
        "danger",
        "muted",
        "primary",
        "success",
        "surface",
        "text-dark",
        "text-light",
        "warning",
    }
)


def _relative_luminance(color: ColorHex) -> float:
    """WCAG relative luminance of an ``#rrggbb`` color, in [0, 1]."""

    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (channel(int(color[i : i + 2], 16) / 255) for i in (1, 3, 5))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


class Theme(BaseModel):
    """A validated design-token theme.

    ``colors`` must provide every token in :data:`CORE_COLOR_TOKENS` and may
    declare additional tokens.  ``series`` is the categorical palette for
    plots and other repeated-color contexts.  The model is strict like the
    manifest models: unknown structure and malformed colors fail validation,
    surfacing as typed errors at build time rather than a degraded report.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: NonEmptyStr
    """Human-readable name of the theme."""

    colors: dict[ThemeToken, ColorHex]
    """Semantic token to color mapping.  Core tokens are required;
    additional tokens are allowed."""

    series: tuple[ColorHex, ...] = Field(min_length=2)
    """Ordered categorical palette for plots and repeated-color contexts."""

    font_body: FontStack = (
        'system-ui, -apple-system, "Segoe UI", Roboto, '
        '"Helvetica Neue", Arial, sans-serif'
    )
    """The report body font, as a CSS ``font-family`` list.  The
    default is the system font stack: the report fetches nothing."""

    font_heading: FontStack = (
        'system-ui, -apple-system, "Segoe UI", Roboto, '
        '"Helvetica Neue", Arial, sans-serif'
    )
    """The heading font; defaults to the body stack."""

    @field_validator("colors")
    @classmethod
    def _validate_core_tokens(cls, value: dict[str, str]) -> dict[str, str]:
        """Require every core token to be declared."""
        missing = sorted(CORE_COLOR_TOKENS - value.keys())
        if missing:
            raise ValueError(
                f"theme is missing core color tokens: {', '.join(missing)}"
            )
        return value

    def text_on(self, *backgrounds: ColorHex) -> ColorHex:
        """Select the candidate ink with stronger contrast on *backgrounds*.

        Compare WCAG contrast ratios of ``text-light`` and ``text-dark``
        against the mean relative luminance of the supplied backgrounds.
        Return the stronger candidate; ties resolve to ``text-dark``.

        Supply one background for a solid surface or both stops for a
        gradient. Selection against mean luminance does not guarantee
        sufficient contrast everywhere along a gradient, nor does it
        guarantee that either candidate meets an accessibility threshold.
        """
        if not backgrounds:
            raise ValueError("text_on requires at least one background color")
        mean = sum(_relative_luminance(c) for c in backgrounds) / len(backgrounds)

        def contrast(text: ColorHex) -> float:
            luminance = _relative_luminance(text)
            return (max(mean, luminance) + 0.05) / (min(mean, luminance) + 0.05)

        light = self.colors["text-light"]
        dark = self.colors["text-dark"]
        return light if contrast(light) > contrast(dark) else dark

    def resolve_color(self, requester: str, raw: object) -> ColorHex:
        """One color request — a theme token or a series entry — to
        hex.

        The shared color grammar: a theme token this theme declares
        (``primary``) or a categorical-series entry (``series-2``),
        resolved to the theme's own ``#rrggbb`` — never a literal.
        *requester* names the placement that asked (a component id),
        so every teaching error points at the right door.  The
        grammar the core components established, promoted to the
        theme itself — the owner of the tokens and the palette — so
        plugins ask instead of re-implementing.
        """
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(
                f"{requester}: 'color' must be a theme color token (e.g. "
                f"'primary') or a series entry like 'series-1', got {raw!r}"
            )
        match = _SERIES_COLOR_PATTERN.fullmatch(raw)
        if match is not None:
            index = int(match.group(1))
            if not 1 <= index <= len(self.series):
                raise ValueError(
                    f"{requester}: 'color' names {raw!r}, but this theme's "
                    f"series palette has {len(self.series)} colors "
                    f"(valid: series-1 to series-{len(self.series)})"
                )
            return self.series[index - 1]
        if raw in self.colors:
            return self.colors[raw]
        available = ", ".join(sorted(self.colors))
        raise ValueError(
            f"{requester}: 'color' must be a theme token this theme "
            f"declares ({available}) or a series entry like 'series-1', "
            f"got {raw!r}"
        )
