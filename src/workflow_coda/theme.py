"""Design-token theming for generated reports.

Every visual element of a report draws its colors from a single validated
theme: the page CSS, plugin-generated figures, and report JavaScript.  A
theme is a set of semantic tokens, decided at report build time, and it is
injected in two places: as ``--wc-*`` CSS custom properties emitted by the
report template, and as ``context.theme`` on the render context handed to
plugins.

The token set is open in exactly one direction: themes may declare color
tokens beyond the core set, which CSS and plugins may use
opportunistically.  Plugins never declare tokens of their own and never
hard-code colors, so a plugin renders correctly against any theme and a
theme restyles any plugin's output.
"""

from typing import Annotated, Final

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from .manifest import NonEmptyStr
from .text import has_visible_text


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
        """The theme's light or dark text color, whichever reads on *backgrounds*.

        Compares WCAG contrast ratios of ``text-light`` and ``text-dark``
        against the mean relative luminance of the given backgrounds, and
        returns the stronger — text over a filled or gradient surface, a
        colored header, or any future colored background stays readable
        without the author choosing.  A gradient passes both stops; a
        solid color passes one.  Ties resolve to ``text-dark``.
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


#: The built-in ``default`` theme, used when no theme is explicitly
#: selected at build time.
DEFAULT_THEME: Final[Theme] = Theme.model_validate(
    {
        "name": "default",
        "colors": {
            "accent": "#6e91d2",
            "background": "#f5f7fa",
            "border": "#dee2e6",
            "danger": "#d2574c",
            "muted": "#6c757d",
            "primary": "#3e65b9",
            "success": "#75a941",
            "surface": "#ffffff",
            "text-dark": "#212529",
            "text-light": "#ffffff",
            "warning": "#ece860",
        },
        "series": [
            "#6e91d2",
            "#acc6f5",
            "#f38d4d",
            "#fcc29f",
            "#75a941",
            "#a9cd86",
            "#d2574c",
            "#e89c9a",
            "#9560af",
            "#c798dc",
            "#7b533a",
            "#ab9080",
            "#d084b2",
            "#dfaac9",
            "#86c3c5",
            "#bad9da",
            "#ece860",
            "#f8f6c2",
            "#343131",
            "#655f5f",
        ],
    }
)
