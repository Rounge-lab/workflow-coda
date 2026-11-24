"""Paired Plotly styling updates carried beside one embedded figure.

These are in-memory contracts. The chart data and initial figure
configuration remain embedded once; these values contain only the
styling fields a component owns.
"""

import json
from dataclasses import dataclass

from ..artifact_store import JsonValue

_LAYOUT_FIELDS = frozenset(
    {
        "font.color",
        "font.family",
        "paper_bgcolor",
        "plot_bgcolor",
        "xaxis.gridcolor",
        "xaxis.zerolinecolor",
        "yaxis.gridcolor",
        "yaxis.zerolinecolor",
    }
)
_TRACE_FIELDS = frozenset({"marker.color", "line.color"})


@dataclass(frozen=True, slots=True, kw_only=True)
class FigureStyle:
    """One mode's styling updates.

    Layout keys use Plotly's dotted update vocabulary.
    Each trace mapping addresses the trace at the same position
    in the embedded figure.
    """

    layout: dict[str, str]
    traces: tuple[dict[str, str], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.layout, dict):
            raise ValueError("figure style layout must be a mapping")
        if not isinstance(self.traces, tuple):
            raise ValueError("figure style traces must be a tuple of mappings")
        self._validate_fields(self.layout, _LAYOUT_FIELDS, "layout")
        for index, trace in enumerate(self.traces):
            if not isinstance(trace, dict):
                raise ValueError(f"figure style trace {index} must be a mapping")
            self._validate_fields(trace, _TRACE_FIELDS, f"trace {index}")

    @staticmethod
    def _validate_fields(
        fields: dict[str, str],
        allowed: frozenset[str],
        subject: str,
    ) -> None:
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(
                    f"figure style {subject}: unsupported styling field "
                    f"{key!r} — figure data and interaction settings "
                    "do not belong in theme updates"
                )
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"figure style {subject}: {key!r} requires a non-empty string"
                )


@dataclass(frozen=True, slots=True, kw_only=True)
class FigureTheme:
    """Compatible light/dark styling updates for one figure."""

    light: FigureStyle
    dark: FigureStyle

    def __post_init__(self) -> None:
        if not isinstance(self.light, FigureStyle) or not isinstance(
            self.dark, FigureStyle
        ):
            raise ValueError("a FigureTheme requires two FigureStyle instances")
        if self.light.layout.keys() != self.dark.layout.keys():
            raise ValueError("figure theme modes must update matching layout fields")
        if len(self.light.traces) != len(self.dark.traces):
            raise ValueError("figure theme modes must have matching trace counts")
        for index, (light, dark) in enumerate(
            zip(self.light.traces, self.dark.traces, strict=True)
        ):
            if light.keys() != dark.keys():
                raise ValueError(
                    f"figure theme trace {index}: modes must update "
                    "matching styling fields"
                )

    def to_json(self) -> str:
        """Serialize the browser transport; callers own HTML escaping."""

        def payload(style: FigureStyle) -> dict[str, JsonValue]:
            return {
                "layout": dict(style.layout),
                "traces": [dict(trace) for trace in style.traces],
            }

        return json.dumps(
            {"light": payload(self.light), "dark": payload(self.dark)},
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
