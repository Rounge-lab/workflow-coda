"""Tests for the design-token theme model."""

import pytest
from factories import make_theme_payload
from helpers import assert_frozen, invalid_fields
from pydantic import ValidationError

from workflow_coda.theme import CORE_COLOR_TOKENS, DEFAULT_THEME, Theme

VALID_HEX = "#123456"
"""A syntactically valid color literal, distinct from the default palette."""


def make_valid_colors() -> dict[str, str]:
    """Core tokens mapped to one valid color, for single-token tests."""
    return {token: VALID_HEX for token in CORE_COLOR_TOKENS}


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_default_theme_is_valid() -> None:
    # Import-time construction already exercises this; the assertion makes
    # the invariant explicit and gives the constant a coverage home.
    assert DEFAULT_THEME.name == "default"
    assert CORE_COLOR_TOKENS <= DEFAULT_THEME.colors.keys()
    assert len(DEFAULT_THEME.series) >= 2


def test_valid_theme_parses() -> None:
    theme = Theme.model_validate(make_theme_payload())
    assert theme.name == "default"
    assert theme.colors["primary"] == "#0d6efd"
    assert theme.series == ("#0d6efd", "#d63384", "#fd7e14", "#20c997", "#6610f2")


def test_series_coerces_list_to_tuple() -> None:
    theme = Theme.model_validate(make_theme_payload())
    assert isinstance(theme.series, tuple)


def test_extra_color_tokens_are_accepted() -> None:
    # Themes extend the token set; plugins consume.  This pins the open
    # direction of the token contract.
    colors = make_valid_colors() | {"sample-highlight": "#0d6efd"}
    theme = Theme.model_validate(make_theme_payload(colors=colors))
    assert theme.colors["sample-highlight"] == "#0d6efd"


def test_hex_colors_preserve_case() -> None:
    # Exact-preservation house rule: "#FF0000" validates and stays as written.
    colors = make_valid_colors() | {"primary": "#FF0000"}
    theme = Theme.model_validate(make_theme_payload(colors=colors))
    assert theme.colors["primary"] == "#FF0000"


def test_theme_round_trips() -> None:
    original = Theme.model_validate(make_theme_payload())
    rebuilt = Theme.model_validate(original.model_dump())
    assert rebuilt == original


# ---------------------------------------------------------------------------
# Required structure
# ---------------------------------------------------------------------------


def test_all_fields_required() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Theme.model_validate({})
    assert invalid_fields(exc_info.value) == {"name", "colors", "series"}


def test_extra_top_level_keys_are_forbidden() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Theme.model_validate(make_theme_payload(typography="serif"))
    assert invalid_fields(exc_info.value) == {"typography"}


def test_missing_core_tokens_are_aggregated_and_sorted() -> None:
    colors = make_valid_colors()
    del colors["accent"]
    del colors["primary"]
    with pytest.raises(ValidationError) as exc_info:
        Theme.model_validate(make_theme_payload(colors=colors))
    assert "theme is missing core color tokens: accent, primary" in str(exc_info.value)


def test_missing_core_tokens_names_every_missing_token() -> None:
    colors = {"background": VALID_HEX}
    with pytest.raises(ValidationError) as exc_info:
        Theme.model_validate(make_theme_payload(colors=colors))
    for token in CORE_COLOR_TOKENS - {"background"}:
        assert token in str(exc_info.value)


def test_empty_colors_is_rejected_with_full_report() -> None:
    with pytest.raises(ValidationError, match="missing core color tokens"):
        Theme.model_validate(make_theme_payload(colors={}))


# ---------------------------------------------------------------------------
# Token and color syntax
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token",
    [
        "Background",
        "1background",
        "",
        "-background",
        "background_color",
        "background color",
    ],
)
def test_rejects_malformed_tokens(token: str) -> None:
    colors = make_valid_colors() | {token: VALID_HEX}
    with pytest.raises(ValidationError):
        Theme.model_validate(make_theme_payload(colors=colors))


def test_rejects_uppercase_token() -> None:
    # Redundant with the parametrize above but pinned explicitly: token
    # pattern is case-sensitive.
    colors = make_valid_colors() | {"Primary": VALID_HEX}
    with pytest.raises(ValidationError):
        Theme.model_validate(make_theme_payload(colors=colors))


@pytest.mark.parametrize(
    "color",
    ["#12345", "#1234567", "123456", "#12345g", "#12345G", " #123456", "#123456 "],
)
def test_rejects_malformed_colors(color: str) -> None:
    colors = make_valid_colors() | {"primary": color}
    with pytest.raises(ValidationError):
        Theme.model_validate(make_theme_payload(colors=colors))


def test_rejects_non_string_color() -> None:
    colors = make_valid_colors() | {"primary": 65280}
    with pytest.raises(ValidationError):
        Theme.model_validate(make_theme_payload(colors=colors))


# ---------------------------------------------------------------------------
# Series palette
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("length", [0, 1])
def test_series_requires_two_colors_minimum(length: int) -> None:
    payload = make_theme_payload(series=["#123456"] * length)
    with pytest.raises(ValidationError):
        Theme.model_validate(payload)


def test_series_accepts_repeated_colors() -> None:
    # Distinctness is deliberately not enforced; a repeated palette color
    # is harmless and unrequested strictness.
    theme = Theme.model_validate(make_theme_payload(series=["#123456", "#123456"]))
    assert theme.series == ("#123456", "#123456")


def test_series_rejects_malformed_colors() -> None:
    with pytest.raises(ValidationError):
        Theme.model_validate(make_theme_payload(series=["#123456", "red"]))


# ---------------------------------------------------------------------------
# Value semantics
# ---------------------------------------------------------------------------


def test_theme_is_frozen() -> None:
    theme = Theme.model_validate(make_theme_payload())
    assert_frozen(theme, "name", "renamed")


def test_theme_compares_by_value() -> None:
    first = Theme.model_validate(make_theme_payload())
    second = Theme.model_validate(make_theme_payload())
    assert first == second
    assert first is not DEFAULT_THEME


def test_font_defaults_are_system_stacks() -> None:
    assert "system-ui" in DEFAULT_THEME.font_body
    assert "system-ui" in DEFAULT_THEME.font_heading


def test_theme_fonts_override_and_round_trip() -> None:
    payload = DEFAULT_THEME.model_dump()
    payload["font_body"] = "Georgia, serif"
    payload["font_heading"] = '"Helvetica Neue", Arial, sans-serif'
    theme = Theme.model_validate(payload)
    assert theme.font_body == "Georgia, serif"
    assert theme.font_heading == '"Helvetica Neue", Arial, sans-serif'


def test_theme_fonts_must_be_visible_text() -> None:
    payload = DEFAULT_THEME.model_dump()
    payload["font_body"] = "   "
    with pytest.raises(ValidationError, match="must contain visible text"):
        Theme.model_validate(payload)


def test_theme_fonts_reject_fetched_files() -> None:
    payload = DEFAULT_THEME.model_dump()
    payload["font_body"] = "url(https://fonts.example.com/font.woff2)"
    with pytest.raises(ValidationError, match="font-family names, not fetched"):
        Theme.model_validate(payload)
