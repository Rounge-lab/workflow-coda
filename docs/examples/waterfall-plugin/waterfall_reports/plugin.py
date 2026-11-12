"""A minimal report plugin: one component, one waterfall figure.

This is the module the tutorial walks through: it reads one JSON
artifact and renders it as a Plotly waterfall chart through the
framework's figure channel.
"""

from workflow_coda.components import (
    ComponentParameters,
    PlacementInfo,
    PluginMetadata,
    RenderedComponent,
    ReportComponent,
    SupportsToHtml,
    reject_unknown_parameters,
)
from workflow_coda.context import RenderContext
from workflow_coda.errors import ArtifactUnavailableError, RenderError
from workflow_coda.plugins import ReportPlugin

ACCEPTED_PARAMETERS = frozenset({"artifact", "unit"})
"""The component's closed parameter vocabulary."""


def _parse_steps(artifact_type: str, data: object) -> list[tuple[str, float]]:
    """Validate the artifact's content and return its steps."""
    if not isinstance(data, dict):
        raise ValueError(
            f"waterfall.plot: artifact {artifact_type!r} must be a JSON object"
        )
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError(
            f"waterfall.plot: artifact {artifact_type!r} must carry a "
            "non-empty 'steps' list"
        )
    steps: list[tuple[str, float]] = []
    for index, step in enumerate(raw_steps):
        if not isinstance(step, dict):
            raise ValueError(
                f"waterfall.plot: step {index} must be an object with "
                "'label' and 'value'"
            )
        label = step.get("label")
        value = step.get("value")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(
                f"waterfall.plot: step {index} 'label' must be visible text"
            )
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"waterfall.plot: step {index} 'value' must be a number")
        steps.append((label, float(value)))
    return steps


def _waterfall_figure(
    context: RenderContext, steps: list[tuple[str, float]], unit: str | None
) -> SupportsToHtml:
    """The dressed figure: theme colors, transparent backgrounds."""
    try:
        from plotly.graph_objects import Figure, Waterfall
    except ImportError as e:
        raise RenderError(
            "waterfall.plot needs the plotly package to draw its figure — "
            "install plotly and build the report again"
        ) from e
    theme = context.theme
    up = theme.resolve_color("waterfall.plot", "series-1")
    down = theme.resolve_color("waterfall.plot", "series-2")
    figure = Figure(
        Waterfall(
            x=[label for label, _ in steps],
            y=[value for _, value in steps],
            measure=["absolute"] + ["relative"] * (len(steps) - 1),
            increasing={"marker": {"color": up}},
            decreasing={"marker": {"color": down}},
            connector={"line": {"color": theme.colors["border"], "width": 1}},
        )
    )
    figure.update_layout(
        paper_bgcolor="rgba(0, 0, 0, 0)",
        plot_bgcolor="rgba(0, 0, 0, 0)",
        font={"color": theme.text_on(theme.colors["surface"])},
        yaxis={"title": unit} if unit is not None else {},
        showlegend=False,
    )
    return figure


def render_waterfall(
    context: RenderContext, info: PlacementInfo, parameters: ComponentParameters
) -> RenderedComponent:
    """Render one waterfall figure from one JSON artifact."""
    reject_unknown_parameters("waterfall.plot", parameters, ACCEPTED_PARAMETERS)
    artifact_type = parameters.get("artifact")
    if not isinstance(artifact_type, str) or not artifact_type.strip():
        raise ValueError(
            "waterfall.plot: requires an 'artifact' parameter naming "
            "the artifact type to plot"
        )
    unit = parameters.get("unit")
    if unit is not None and (not isinstance(unit, str) or not unit.strip()):
        raise ValueError(
            "waterfall.plot: 'unit' must be visible text — it labels "
            "the figure's y axis"
        )
    try:
        artifact = context.store.require(artifact_type)
        data = artifact.read_json()
    except ArtifactUnavailableError as e:
        return RenderedComponent.unavailable(str(e))
    steps = _parse_steps(artifact_type, data)
    figure = _waterfall_figure(context, steps, unit)
    description = f"Waterfall chart: {info.title} across {len(steps)} steps"
    return RenderedComponent.from_figure(figure, description=description)


def get_plugin() -> ReportPlugin:
    """Assemble the plugin value — the entry point calls this."""
    return ReportPlugin(
        metadata=PluginMetadata(
            id="waterfall",
            name="Waterfall reports",
            version="0.1.0",
            description="A waterfall chart component, built in the tutorial.",
            supported_schema_versions=frozenset({"0.3.0"}),
        ),
        components=(
            ReportComponent(
                id="waterfall.plot",
                title="Waterfall",
                description="A step-by-step waterfall figure.",
                render=render_waterfall,
            ),
        ),
    )
