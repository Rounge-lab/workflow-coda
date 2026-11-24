"""Tests for validated, mode-independent CSS color references."""

import pytest

from workflow_coda.theme import (
    DEFAULT_THEME_PAIR,
    Theme,
    ThemePair,
    color_css,
    plate_inks,
)


@pytest.mark.parametrize(
    ("color_request", "expected"),
    [
        ("primary", "var(--coda-primary)"),
        ("accent", "var(--coda-accent)"),
        ("series-1", "var(--coda-series-1)"),
        ("series-01", "var(--coda-series-1)"),
    ],
)
def test_color_css_returns_validated_reference(
    color_request: str, expected: str
) -> None:
    assert color_css(DEFAULT_THEME_PAIR, "core.kpi", color_request) == expected


@pytest.mark.parametrize(
    "color_request",
    [None, True, 5, [], {}, "", "   ", "#123456", "series-0", "missing"],
)
def test_color_css_preserves_requester_in_teaching(
    color_request: object,
) -> None:
    with pytest.raises(ValueError, match="light theme: core.kpi:"):
        color_css(DEFAULT_THEME_PAIR, "core.kpi", color_request)


def _with_custom_token(theme: Theme) -> Theme:
    payload = theme.model_dump()
    payload["colors"]["custom-plate"] = "#123456"
    return Theme.model_validate(payload)


def test_custom_token_present_in_both_modes_returns_reference() -> None:
    pair = ThemePair(
        light=_with_custom_token(DEFAULT_THEME_PAIR.light),
        dark=_with_custom_token(DEFAULT_THEME_PAIR.dark),
    )

    assert color_css(pair, "core.notice", "custom-plate") == (
        "var(--coda-custom-plate)"
    )


def test_series_request_must_fit_the_paired_palette() -> None:
    pair = DEFAULT_THEME_PAIR
    color_request = f"series-{len(pair.light.series) + 1}"

    with pytest.raises(ValueError, match="light theme: core.chart:"):
        color_css(pair, "core.chart", color_request)


@pytest.mark.parametrize(
    "references",
    [
        ("primary",),
        ("series-1",),
        ("primary", "accent"),
        ("series-1", "series-2"),
    ],
)
def test_plate_inks_use_each_modes_own_colors(
    references: tuple[str, ...],
) -> None:
    pair = DEFAULT_THEME_PAIR

    expected = tuple(
        theme.text_on(*(theme.resolve_color("core.kpi", ref) for ref in references))
        for theme in (pair.light, pair.dark)
    )

    assert plate_inks(pair, "core.kpi", *references) == expected


def test_plate_inks_can_choose_different_ink_in_each_mode() -> None:
    defaults = DEFAULT_THEME_PAIR
    light_payload = defaults.light.model_dump()
    dark_payload = defaults.dark.model_dump()

    for payload in (light_payload, dark_payload):
        payload["colors"]["text-light"] = "#ffffff"
        payload["colors"]["text-dark"] = "#000000"

    light_payload["colors"]["primary"] = "#ffffff"
    dark_payload["colors"]["primary"] = "#000000"

    pair = ThemePair(
        light=Theme.model_validate(light_payload),
        dark=Theme.model_validate(dark_payload),
    )

    assert plate_inks(pair, "core.kpi", "primary") == (
        "#000000",
        "#ffffff",
    )


@pytest.mark.parametrize(
    "references",
    [
        (),
        ("primary", "accent", "success"),
    ],
)
def test_plate_inks_require_one_or_two_references(
    references: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError, match="core.kpi: a plate requires"):
        plate_inks(DEFAULT_THEME_PAIR, "core.kpi", *references)


@pytest.mark.parametrize(
    "color_request",
    [None, True, "#123456", "missing", "series-0"],
)
def test_plate_inks_preserve_mode_and_requester_in_errors(
    color_request: object,
) -> None:
    with pytest.raises(ValueError, match="light theme: core.kpi:"):
        plate_inks(DEFAULT_THEME_PAIR, "core.kpi", color_request)


def test_plate_inks_validate_the_second_gradient_stop() -> None:
    with pytest.raises(ValueError, match="light theme: core.kpi:"):
        plate_inks(DEFAULT_THEME_PAIR, "core.kpi", "primary", "missing")
