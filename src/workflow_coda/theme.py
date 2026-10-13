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
        "background",
        "surface",
        "text",
        "muted",
        "border",
        "primary",
        "accent",
        "success",
        "warning",
        "danger",
    }
)


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


#: The built-in ``default`` theme, used when no theme is explicitly
#: selected at build time.
DEFAULT_THEME: Final[Theme] = Theme.model_validate(
    {
        "name": "default",
        "colors": {
            "background": "#ffffff",
            "surface": "#f5f7fa",
            "text": "#212529",
            "muted": "#6c757d",
            "border": "#dee2e6",
            "primary": "#0d6efd",
            "accent": "#6610f2",
            "success": "#198754",
            "warning": "#ffc107",
            "danger": "#dc3545",
        },
        "series": ["#0d6efd", "#d63384", "#fd7e14", "#20c997", "#6610f2"],
    }
)
