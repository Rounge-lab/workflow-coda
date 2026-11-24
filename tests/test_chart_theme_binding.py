"""Core chart styling bindings contain style only, in both modes."""

import pytest

from workflow_coda.core.chart import _figure_theme, _parse_spec
from workflow_coda.theme import DEFAULT_THEME_PAIR


@pytest.mark.parametrize(
    ("chart", "extra", "expected_fields"),
    [
        ("scatter", {"x": "x", "y": "y"}, {"marker.color"}),
        ("line", {"x": "x", "y": "y"}, {"marker.color", "line.color"}),
        ("bar", {"x": "x", "y": "y"}, {"marker.color"}),
        ("histogram", {"x": "x"}, {"marker.color"}),
        ("box", {"y": "y"}, {"marker.color", "line.color"}),
    ],
)
def test_binding_uses_each_modes_palette(
    chart: str,
    extra: dict[str, str],
    expected_fields: set[str],
) -> None:
    spec = _parse_spec({"artifact": "measurements", "chart": chart, **extra})
    pair = DEFAULT_THEME_PAIR
    binding = _figure_theme(pair, spec, 1)

    for style, theme in (
        (binding.light, pair.light),
        (binding.dark, pair.dark),
    ):
        assert set(style.traces[0]) == expected_fields
        assert set(style.traces[0].values()) == {theme.series[0]}
        assert style.layout["font.family"] == theme.font_body
        assert style.layout["font.color"] == theme.text_on(theme.colors["surface"])
        assert "xaxis.type" not in style.layout
        assert "yaxis.type" not in style.layout


def test_hue_binding_cycles_matching_palettes() -> None:
    spec = _parse_spec(
        {
            "artifact": "measurements",
            "chart": "scatter",
            "x": "x",
            "y": "y",
            "hue": "group",
        }
    )
    pair = DEFAULT_THEME_PAIR
    count = len(pair.light.series) + 1
    binding = _figure_theme(pair, spec, count)

    for style, theme in (
        (binding.light, pair.light),
        (binding.dark, pair.dark),
    ):
        assert len(style.traces) == count
        assert style.traces[-1]["marker.color"] == theme.series[0]
