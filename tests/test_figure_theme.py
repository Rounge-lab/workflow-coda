"""Tests for paired figure styling and escaped HTML transport."""

import html
import json
import re
from typing import Any

import pytest

from workflow_coda.artifact_store import JsonValue
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


# Was a core-chart field allowlist with string-only values; now
# arbitrary JSON updates. Plugins own Plotly policy; the framework
# validates transport only.


@pytest.mark.parametrize(
    "field",
    ["x", "y", "visible", "marker.size", "name"],
)
def test_trace_updates_accept_plugin_owned_fields(field: str) -> None:
    style = FigureStyle(layout={}, traces=({field: "value"},))

    assert style.traces == ({field: "value"},)


@pytest.mark.parametrize(
    "field",
    ["xaxis.type", "xaxis.range", "title.text", "showlegend", "uirevision"],
)
def test_layout_updates_accept_plugin_owned_fields(field: str) -> None:
    style = FigureStyle(layout={field: "value"}, traces=())

    assert style.layout == {field: "value"}


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        None,
        True,
        5,
        0.75,
        [1, 2, 3],
        [[0, "#123456"], [1, "#abcdef"]],
        {"color": "#123456", "size": 5},
    ],
)
def test_style_values_accept_json_values(value: JsonValue) -> None:
    style = FigureStyle(
        layout={"plugin.field": value},
        traces=({"plugin.field": value},),
    )
    theme = FigureTheme(light=style, dark=style)
    payload = json.loads(theme.to_json())

    assert payload["light"]["layout"]["plugin.field"] == value
    assert payload["dark"]["traces"][0]["plugin.field"] == value


@pytest.mark.parametrize("key", ["", "   ", None, 5])
@pytest.mark.parametrize("subject", ["layout", "trace"])
def test_update_keys_require_non_empty_strings(key: Any, subject: str) -> None:
    fields: dict[str, JsonValue] = {key: "value"}
    with pytest.raises(ValueError, match="must be a non-empty string"):
        if subject == "layout":
            FigureStyle(layout=fields, traces=())
        else:
            FigureStyle(layout={}, traces=(fields,))


@pytest.mark.parametrize(
    "value",
    [
        (1, 2),
        {1, 2},
        object(),
        {"nested": (1, 2)},
    ],
)
def test_style_values_reject_non_json_types(value: Any) -> None:
    with pytest.raises(ValueError, match="JSON-compatible"):
        FigureStyle(layout={"plugin.field": value}, traces=())


def test_nested_mapping_keys_require_strings() -> None:
    value: Any = {"nested": {5: "value"}}

    with pytest.raises(ValueError, match="mapping key 5 must be a string"):
        FigureStyle(layout={"plugin.field": value}, traces=())


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf")],
)
def test_style_values_reject_non_finite_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="use finite JSON-compatible values") as exc:
        FigureStyle(layout={"plugin.field": value}, traces=())

    assert isinstance(exc.value.__cause__, ValueError)


def test_style_values_reject_circular_references() -> None:
    value: list[Any] = []
    value.append(value)

    with pytest.raises(ValueError, match="circular references") as exc:
        FigureStyle(layout={"plugin.field": value}, traces=())

    assert isinstance(exc.value.__cause__, ValueError)


def test_theme_serialization_revalidates_nested_mutations() -> None:
    values: list[JsonValue] = [1, 2]
    style = FigureStyle(layout={}, traces=({"marker.size": values},))
    theme = FigureTheme(light=style, dark=style)
    values.append(float("nan"))

    with pytest.raises(ValueError, match="use finite JSON-compatible values"):
        theme.to_json()


def test_updates_preserve_array_values_and_declaration_order() -> None:
    style = FigureStyle(
        layout={"showlegend": False, "xaxis.range": [0, 10]},
        traces=(
            {
                "marker.size": [4, 8],
                "marker.colorscale": [[0, "#123456"], [1, "#abcdef"]],
            },
        ),
    )
    payload = json.loads(FigureTheme(light=style, dark=style).to_json())

    assert list(payload["light"]["layout"]) == ["showlegend", "xaxis.range"]
    trace = payload["light"]["traces"][0]
    assert list(trace) == ["marker.size", "marker.colorscale"]
    assert trace["marker.size"] == [4, 8]
    assert trace["marker.colorscale"] == [[0, "#123456"], [1, "#abcdef"]]


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
    with pytest.raises(ValueError, match="matching fields"):
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


class _RecordingFigure:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def to_html(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return '<div class="plotly-graph-div">one figure</div>'


def test_unthemed_embedding_does_not_require_post_script() -> None:
    figure = _RecordingFigure()
    RenderedComponent.from_figure(figure)

    (call,) = figure.calls
    assert set(call) == {"full_html", "include_plotlyjs", "config"}
    assert call["full_html"] is False
    assert call["include_plotlyjs"] is False


def test_themed_embedding_requests_initialization_completion() -> None:
    figure = _RecordingFigure()
    RenderedComponent.from_figure(figure, theme=_theme())

    (call,) = figure.calls
    script = call["post_script"]
    assert "document.getElementById('{plot_id}')" in script
    assert "data-coda-figure-ready" in script
    assert "coda:figure-ready" in script
    assert "bubbles: true" in script
    assert call["config"]["responsive"] is True


class _LegacyFigure:
    def to_html(
        self,
        *,
        full_html: bool,
        include_plotlyjs: bool,
        config: dict[str, Any] | None = None,
    ) -> str:
        return "<div>legacy figure</div>"


def test_legacy_serializer_remains_supported_without_theme() -> None:
    outcome = RenderedComponent.from_figure(_LegacyFigure())
    assert outcome.html is not None
    assert "legacy figure" in outcome.html


def test_themed_serializer_must_support_completion_hook() -> None:
    with pytest.raises(TypeError, match="post_script"):
        RenderedComponent.from_figure(_LegacyFigure(), theme=_theme())


def test_real_plotly_embedding_contains_completion_hook() -> None:
    go = pytest.importorskip("plotly.graph_objects")
    figure = go.Figure(go.Scatter(x=[1, 2], y=[3, 4]))
    outcome = RenderedComponent.from_figure(figure, theme=_theme())

    assert outcome.html is not None
    assert "Plotly.newPlot" in outcome.html
    assert ".then(" in outcome.html
    assert "data-coda-figure-ready" in outcome.html
    assert "coda:figure-ready" in outcome.html
    assert "{plot_id}" not in outcome.html
