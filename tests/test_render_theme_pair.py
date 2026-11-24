"""Tests for generated light/dark CSS and its mode selectors."""

import pytest

from workflow_coda.render import _css_theme_pair, _css_tokens
from workflow_coda.theme import DEFAULT_THEME_PAIR, Theme, ThemePair


def _indented(rule: str) -> str:
    return "\n".join(f"  {line}" for line in rule.splitlines())


def _expected_rule(
    theme: Theme,
    selector: str,
    mode: str,
    header_color: str | tuple[str, str] | None = None,
    header_variant: str = "fill",
) -> str:
    # Expected declarations derive from the established single-theme
    # generator; these tests pin pair wiring and the cascade.
    rule = _css_tokens(
        theme,
        header_color,
        header_variant,  # type: ignore[arg-type]
    )
    rule = rule.replace(":root {", f"{selector} {{", 1)
    return rule.replace("\n}", f"\n  color-scheme: {mode};\n}}", 1)


def test_pair_emits_browser_preference_and_explicit_screen_modes() -> None:
    pair = DEFAULT_THEME_PAIR
    css = _css_theme_pair(pair, None)

    assert css.startswith(_expected_rule(pair.light, ":root", "light"))
    assert (
        "@media screen and (prefers-color-scheme: dark) {\n"
        + _indented(
            _expected_rule(
                pair.dark,
                ":root:not([data-coda-theme])",
                "dark",
            )
        )
        + "\n}"
    ) in css
    assert "@media screen {" in css
    assert (
        _indented(
            _expected_rule(
                pair.light,
                ':root[data-coda-theme="light"]',
                "light",
            )
        )
        in css
    )
    assert (
        _indented(
            _expected_rule(
                pair.dark,
                ':root[data-coda-theme="dark"]',
                "dark",
            )
        )
        in css
    )


def test_print_rule_is_light_and_has_no_explicit_mode_selector() -> None:
    pair = DEFAULT_THEME_PAIR
    css = _css_theme_pair(pair, None)
    print_css = css.split("@media print {", 1)[1]

    assert "data-coda-theme" not in print_css
    assert print_css == (
        "\n" + _indented(_expected_rule(pair.light, ":root", "light")) + "\n}"
    )


@pytest.mark.parametrize(
    ("header_color", "header_variant"),
    [
        ("accent", "fill"),
        (("primary", "accent"), "gradient"),
        (("series-1", "series-2"), "gradient"),
    ],
)
def test_header_declarations_derive_independently_in_both_modes(
    header_color: str | tuple[str, str],
    header_variant: str,
) -> None:
    pair = DEFAULT_THEME_PAIR
    css = _css_theme_pair(
        pair,
        header_color,
        header_variant,  # type: ignore[arg-type]
    )

    for theme, selector, mode in (
        (pair.light, ':root[data-coda-theme="light"]', "light"),
        (pair.dark, ':root[data-coda-theme="dark"]', "dark"),
    ):
        assert (
            _indented(
                _expected_rule(
                    theme,
                    selector,
                    mode,
                    header_color,
                    header_variant,
                )
            )
            in css
        )


def test_optional_overrides_and_fonts_remain_mode_specific() -> None:
    payload = DEFAULT_THEME_PAIR.dark.model_dump()
    payload["colors"]["header-text"] = "#123456"
    payload["font_body"] = "Georgia, serif"
    dark = Theme.model_validate(payload)
    pair = ThemePair(light=DEFAULT_THEME_PAIR.light, dark=dark)

    css = _css_theme_pair(pair, None)

    assert (
        _indented(
            _expected_rule(
                dark,
                ':root[data-coda-theme="dark"]',
                "dark",
            )
        )
        in css
    )
    assert "--coda-header-text: #123456;" in css
    assert "--coda-font-body: Georgia, serif;" in css
