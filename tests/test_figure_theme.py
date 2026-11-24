"""Tests for paired figure styling and escaped HTML transport."""

import html
import json
import re

import pytest

from workflow_coda.components import RenderedComponent
from workflow_coda.theme import FigureStyle, FigureTheme


def _style(color: str) -> FigureStyle:
    return FigureStyle(
        layout={"font.color": color, "font.family": "Arial, sans-serif"},
        traces=({"marker.color": color, "line.color": color},),
    )


def _theme() -> FigureTheme:
    return FigureTheme(
        light=_style("#123456"),
        dark=_style("#abcdef"),
    )


def test_theme_serializes_both_modes_without_figure_data() -> None:
    payload = json.loads(_theme().to_json())

    assert payload["light"]["layout"]["font.color"] == "#123456"
    assert payload["dark"]["traces"][0]["marker.color"] == "#abcdef"
    assert set(payload) == {"light", "dark"}
    assert set(payload["light"]) == {"layout", "traces"}


@pytest.mark.parametrize(
    "field",
    ["x", "y", "visible", "marker.size", "name"],
)
def test_trace_updates_reject_non_owned_fields(field: str) -> None:
    with pytest.raises(ValueError, match="unsupported styling field"):
        FigureStyle(layout={}, traces=({field: "value"},))


@pytest.mark.parametrize(
    "field",
    ["xaxis.type", "xaxis.range", "title.text", "showlegend", "uirevision"],
)
def test_layout_updates_reject_non_owned_fields(field: str) -> None:
    with pytest.raises(ValueError, match="unsupported styling field"):
        FigureStyle(layout={field: "value"}, traces=())


@pytest.mark.parametrize("value", ["", "   ", None, 5])
def test_style_values_require_non_empty_strings(value: object) -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        FigureStyle(
            layout={"font.color": value},  # type: ignore[dict-item]
            traces=(),
        )


def test_modes_require_matching_layout_fields() -> None:
    with pytest.raises(ValueError, match="matching layout fields"):
        FigureTheme(
            light=FigureStyle(layout={"font.color": "#123456"}, traces=()),
            dark=FigureStyle(layout={}, traces=()),
        )


def test_modes_require_matching_trace_counts() -> None:
    with pytest.raises(ValueError, match="matching trace counts"):
        FigureTheme(
            light=FigureStyle(layout={}, traces=({},)),
            dark=FigureStyle(layout={}, traces=()),
        )


def test_modes_require_matching_trace_fields() -> None:
    with pytest.raises(ValueError, match="matching styling fields"):
        FigureTheme(
            light=FigureStyle(layout={}, traces=({"marker.color": "#123456"},)),
            dark=FigureStyle(layout={}, traces=({"line.color": "#abcdef"},)),
        )


class _Figure:
    def to_html(self, **_kwargs: object) -> str:
        return '<div class="plotly-graph-div">one figure</div>'


def test_embedding_without_theme_preserves_existing_wrapper() -> None:
    outcome = RenderedComponent.from_figure(_Figure())
    assert outcome.html == (
        '<div class="coda-figure" ><div class="plotly-graph-div">one figure</div></div>'
    )


def test_embedding_carries_escaped_round_trippable_theme_json() -> None:
    style = FigureStyle(
        layout={"font.family": 'Example "Font" <family>, serif'},
        traces=(),
    )
    theme = FigureTheme(light=style, dark=style)
    outcome = RenderedComponent.from_figure(
        _Figure(),
        description="A chart",
        theme=theme,
    )
    assert outcome.html is not None

    match = re.search(r'data-coda-figure-theme="([^"]*)"', outcome.html)
    assert match is not None
    assert "&quot;" in match.group(1)
    assert "&lt;" in match.group(1)
    assert json.loads(html.unescape(match.group(1))) == json.loads(theme.to_json())
    assert outcome.html.count("one figure") == 1
    assert 'aria-label="A chart"' in outcome.html
