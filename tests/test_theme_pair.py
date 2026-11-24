"""Tests for resolved theme pairs and mode-aware styling helpers."""

from dataclasses import FrozenInstanceError

import pytest

from workflow_coda.theme import (
    DEFAULT_DARK_THEME,
    DEFAULT_THEME,
    DEFAULT_THEME_PAIR,
    Theme,
    ThemeColors,
    ThemePair,
)


def _theme(
    *,
    extra_colors: dict[str, str] | None = None,
    series: tuple[str, ...] | None = None,
) -> Theme:
    payload = DEFAULT_THEME.model_dump()
    payload["colors"] = DEFAULT_THEME.colors | (extra_colors or {})
    if series is not None:
        payload["series"] = series
    return Theme.model_validate(payload)


def test_default_pair_carries_bundled_defaults() -> None:
    assert DEFAULT_THEME_PAIR.light is DEFAULT_THEME
    assert DEFAULT_THEME_PAIR.dark is DEFAULT_DARK_THEME


def test_pair_accepts_matching_custom_tokens() -> None:
    pair = ThemePair(
        light=_theme(extra_colors={"sample-highlight": "#123456"}),
        dark=_theme(extra_colors={"sample-highlight": "#abcdef"}),
    )
    assert pair.resolve_color("core.example", "sample-highlight") == ThemeColors(
        light="#123456",
        dark="#abcdef",
    )


def test_pair_reports_sorted_tokens_missing_from_each_mode() -> None:
    with pytest.raises(ValueError) as exc_info:
        ThemePair(
            light=_theme(extra_colors={"zebra": "#123456", "alpha": "#123456"}),
            dark=_theme(extra_colors={"other": "#abcdef"}),
        )
    message = str(exc_info.value)
    assert "light-only: alpha, zebra" in message
    assert "dark-only: other" in message


@pytest.mark.parametrize("token", ["text", "header-background", "header-text"])
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_pair_allows_independently_optional_derivation_overrides(
    token: str,
    mode: str,
) -> None:
    members = {"light": _theme(), "dark": _theme()}
    members[mode] = _theme(extra_colors={token: "#123456"})
    ThemePair(light=members["light"], dark=members["dark"])


def test_pair_requires_matching_series_lengths() -> None:
    with pytest.raises(ValueError, match="matching series lengths"):
        ThemePair(
            light=_theme(series=("#123456", "#abcdef")),
            dark=_theme(series=("#123456", "#abcdef", "#fedcba")),
        )


def test_pair_requires_theme_instances() -> None:
    with pytest.raises(ValueError, match="Theme instances"):
        ThemePair(light=None, dark=DEFAULT_DARK_THEME)  # type: ignore[arg-type]


def test_pair_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        DEFAULT_THEME_PAIR.light = DEFAULT_DARK_THEME  # type: ignore[misc]


def test_resolve_color_returns_both_mode_values() -> None:
    pair = DEFAULT_THEME_PAIR
    assert pair.resolve_color("core.example", "primary") == ThemeColors(
        light=pair.light.colors["primary"],
        dark=pair.dark.colors["primary"],
    )
    assert pair.resolve_color("core.example", "series-2") == ThemeColors(
        light=pair.light.series[1],
        dark=pair.dark.series[1],
    )


@pytest.mark.parametrize("raw", [5, "", "   ", "#123456", "unknown", "series-0"])
def test_resolve_color_preserves_requester_and_names_mode(raw: object) -> None:
    with pytest.raises(ValueError) as exc_info:
        DEFAULT_THEME_PAIR.resolve_color("core.example", raw)
    assert "core.example" in str(exc_info.value)
    assert "in the light theme" in str(exc_info.value)


def test_resolve_color_names_dark_mode_when_only_dark_lacks_override() -> None:
    pair = ThemePair(
        light=_theme(extra_colors={"header-text": "#123456"}),
        dark=_theme(),
    )
    with pytest.raises(ValueError, match="in the dark theme"):
        pair.resolve_color("core.example", "header-text")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("primary", "var(--coda-primary)"),
        ("series-2", "var(--coda-series-2)"),
        ("series-02", "var(--coda-series-2)"),
    ],
)
def test_css_color_returns_validated_normalized_reference(
    raw: str,
    expected: str,
) -> None:
    assert DEFAULT_THEME_PAIR.css_color("core.example", raw) == expected


def test_css_color_rejects_unknown_reference() -> None:
    with pytest.raises(ValueError):
        DEFAULT_THEME_PAIR.css_color("core.example", "unknown")


def test_text_on_derives_ink_independently_for_solid_and_gradient() -> None:
    pair = DEFAULT_THEME_PAIR
    first = pair.resolve_color("core.example", "primary")
    second = pair.resolve_color("core.example", "accent")

    assert pair.text_on(first) == ThemeColors(
        light=pair.light.text_on(first.light),
        dark=pair.dark.text_on(first.dark),
    )
    assert pair.text_on(first, second) == ThemeColors(
        light=pair.light.text_on(first.light, second.light),
        dark=pair.dark.text_on(first.dark, second.dark),
    )


def test_text_on_rejects_no_backgrounds() -> None:
    with pytest.raises(ValueError, match="at least one background"):
        DEFAULT_THEME_PAIR.text_on()


def test_paired_colors_are_frozen() -> None:
    colors = ThemeColors(light="#123456", dark="#abcdef")
    with pytest.raises(FrozenInstanceError):
        colors.light = "#ffffff"  # type: ignore[misc]
