"""Paired Plotly updates carried beside one embedded figure.

Plugins own update fields and values. The framework validates their
JSON transport and matching light/dark structure, not Plotly policy.

Prefer presentation updates: embed figure data once and preserve
the reader's interaction state when changing appearance.
"""

import json
from dataclasses import dataclass

from ..artifact_store import JsonValue


def _validate_json_shape(value: object, subject: str) -> None:
    """Require JSON types, without interpreting plugin-owned values."""
    if value is None or type(value) in (str, bool, int, float):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_shape(item, f"{subject}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(
                    f"figure style {subject}: mapping key {key!r} "
                    "must be a string — use JSON object keys"
                )
            _validate_json_shape(item, f"{subject}[{key!r}]")
        return
    raise ValueError(
        f"figure style {subject}: value {value!r} is not JSON-compatible "
        "— use null, booleans, numbers, strings, lists, or mappings "
        "with string keys"
    )


def _validate_json_transport(value: object, subject: str) -> None:
    """Reject non-finite numbers, cycles, and unserializable values."""
    try:
        json.dumps(value, ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as e:
        raise ValueError(
            f"figure style {subject}: cannot encode value as JSON "
            f"({e}) — use finite JSON-compatible values without "
            "circular references"
        ) from e
    _validate_json_shape(value, subject)


def _validate_fields(fields: object, subject: str) -> None:
    """Validate update transport, not the Plotly field vocabulary."""
    if not isinstance(fields, dict):
        raise ValueError(
            f"figure style {subject}: expected a mapping, got "
            f"{type(fields).__name__} — map Plotly update keys to "
            "JSON-compatible values"
        )
    for key, value in fields.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(
                f"figure style {subject}: update key {key!r} must be "
                "a non-empty string — use a Plotly update field name"
            )
        _validate_json_transport(value, f"{subject}[{key!r}]")


@dataclass(frozen=True, slots=True, kw_only=True)
class FigureStyle:
    """One mode's plugin-owned Plotly updates.

    Layout keys use Plotly's update vocabulary. Each trace mapping
    addresses the trace at the same position in the embedded figure.

    Values may be any JSON-compatible value, including arrays and
    nested mappings. Plotly determines whether a field or value is
    applicable to the figure; the framework does not restrict them.

    Prefer styling updates rather than duplicating data or resetting
    the reader's interaction state.
    """

    layout: dict[str, JsonValue]
    traces: tuple[dict[str, JsonValue], ...]

    def __post_init__(self) -> None:
        _validate_fields(self.layout, "layout")
        if not isinstance(self.traces, tuple):
            raise ValueError(
                "figure style traces must be a tuple of mappings "
                "— supply one update mapping per embedded trace"
            )
        for index, trace in enumerate(self.traces):
            _validate_fields(trace, f"trace {index}")


@dataclass(frozen=True, slots=True, kw_only=True)
class FigureTheme:
    """Matching light/dark update structures for one figure."""

    light: FigureStyle
    dark: FigureStyle

    def __post_init__(self) -> None:
        if not isinstance(self.light, FigureStyle) or not isinstance(
            self.dark, FigureStyle
        ):
            raise ValueError(
                "a FigureTheme requires two FigureStyle instances "
                "— supply light and dark updates"
            )
        if self.light.layout.keys() != self.dark.layout.keys():
            raise ValueError(
                "figure theme modes must update matching layout fields "
                "— declare the same update keys in light and dark"
            )
        if len(self.light.traces) != len(self.dark.traces):
            raise ValueError(
                "figure theme modes must have matching trace counts "
                "— supply corresponding updates for both modes"
            )
        for index, (light, dark) in enumerate(
            zip(self.light.traces, self.dark.traces, strict=True)
        ):
            if light.keys() != dark.keys():
                raise ValueError(
                    f"figure theme trace {index}: modes must update "
                    "matching fields — declare the same update keys "
                    "in light and dark"
                )

    def to_json(self) -> str:
        """Serialize the browser transport; callers own HTML escaping."""
        # Revalidate because frozen dataclasses do not freeze their
        # nested mappings and lists.
        self.light.__post_init__()
        self.dark.__post_init__()
        self.__post_init__()

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
