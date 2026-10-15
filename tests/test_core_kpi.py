"""Tests for the core KPI component: the honest-data grammar.

One artifact-backed headline number, exercised family by family:
parse-time shape errors (teaching ValueErrors before any data is
touched), unavailable outcomes (missing data as facts about the run),
value-dependent judgments, the threshold policy, the variant and
color grammar against the default theme, icons, and display
formatting.  The plugin assembly that ships the component is pinned
in test_core_plugin.py."""

import json
from pathlib import Path

import pytest

from workflow_coda.artifact_store import ArtifactStore, JsonValue
from workflow_coda.components import ComponentParameters, ComponentStatus
from workflow_coda.context import RenderContext
from workflow_coda.core.kpi import render_kpi
from workflow_coda.theme import DEFAULT_THEME

_STATS_TYPE = "org.example.stats"

_DEFAULT_STATS: JsonValue = {
    "depth": 12.4,
    "count": 8,
    "label": "run-42",
    "flag": True,
    "nothing": None,
    "samples": {"a": 30, "b": 41},
}
"""The default artifact payload: scalars at several depths and shapes."""


def _write_bundle(
    tmp_path: Path,
    *,
    status: str = "complete",
    fmt: str = "json",
    content: object = _DEFAULT_STATS,
) -> ArtifactStore:
    """A one-artifact manifest bundle rooted at *tmp_path*.

    The manifest and its artifact are written as real files and loaded
    through the real loader, so every fixture is a valid bundle by
    construction — the serialized factory, not a hand-built model.
    """
    text = content if isinstance(content, str) else json.dumps(content)
    artifact_path = tmp_path / f"stats.{fmt}"
    artifact_path.write_text(text, encoding="utf-8")
    manifest = {
        "schema_version": "0.1.0",
        "producer": {"name": "kpi-fixture", "version": "1.0"},
        "artifacts": [
            {
                "id": "stats",
                "type": _STATS_TYPE,
                "schema_version": "0.1.0",
                "path": f"stats.{fmt}",
                "format": fmt,
                "status": status,
            }
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return ArtifactStore.from_manifest_file(manifest_path)


def _context(store: ArtifactStore) -> RenderContext:
    """The render context for one bundle under the default theme."""
    return RenderContext(store=store, theme=DEFAULT_THEME)


def _kpi(overrides: ComponentParameters | None = None) -> ComponentParameters:
    """The base placement parameters, optionally overridden."""
    base: dict[str, JsonValue] = {"artifact": _STATS_TYPE, "key": "depth"}
    if overrides is None:
        return base
    return {**base, **overrides}


def _html(context: RenderContext, parameters: ComponentParameters) -> str:
    """The rendered OK body, with the OK asserted at the call."""
    outcome = render_kpi(context, parameters)
    assert outcome.status is ComponentStatus.OK
    assert outcome.html is not None
    return outcome.html


def _unavailable_message(
    context: RenderContext, parameters: ComponentParameters
) -> str:
    """The rendered unavailable notice, status asserted at the call."""
    outcome = render_kpi(context, parameters)
    assert outcome.status is ComponentStatus.UNAVAILABLE
    assert outcome.message is not None
    return outcome.message


# ---------------------------------------------------------------------------
# Parse-time shape errors: teaching ValueErrors before any data is touched
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["artifact", "key"])
def test_required_parameters_must_be_given(tmp_path: Path, missing: str) -> None:
    # The two data pointers are the placement's minimum; each absence
    # teaches before anything else is read.
    context = _context(_write_bundle(tmp_path))
    params: dict[str, JsonValue] = {"artifact": _STATS_TYPE, "key": "depth"}
    del params[missing]
    with pytest.raises(ValueError, match=f"parameter {missing!r} is required"):
        render_kpi(context, params)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("artifact", 3),
        ("artifact", True),
        ("artifact", ""),
        ("key", None),
        ("key", "  "),
    ],
)
def test_required_text_rejects_non_strings(
    tmp_path: Path, name: str, value: JsonValue
) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="must be a non-empty string"):
        render_kpi(context, _kpi({name: value}))


@pytest.mark.parametrize(
    ("name", "value", "pin"),
    [
        ("variant", "bold", "must be one of 'fill', 'gradient', 'text'"),
        ("icon_position", "middle", "must be one of 'corner', 'inline'"),
        ("decimals", -1, "must be 0 or greater"),
        ("decimals", 1.5, "must be an integer"),
        ("decimals", True, "must be an integer"),
        ("decimals", "2", "must be an integer"),
    ],
)
def test_closed_vocabularies_and_decimals_teach(
    tmp_path: Path, name: str, value: JsonValue, pin: str
) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match=pin):
        render_kpi(context, _kpi({name: value}))


@pytest.mark.parametrize(
    ("thresholds", "pin"),
    [
        ([], "must be an object like"),
        ({}, "must declare an 'ok' and/or 'notice' group"),
        ({"ok": 3}, "must be an object with optional 'above' and 'below'"),
        ({"ok": {"above": "10"}}, "must be a number"),
        ({"ok": {"above": True}}, "must be a number"),
        ({"great": {"above": 10}}, "must declare an 'ok' and/or 'notice' group"),
    ],
)
def test_threshold_shapes_teach(
    tmp_path: Path, thresholds: JsonValue, pin: str
) -> None:
    # Every malformed policy shape teaches — including a typo'd group
    # name, which would otherwise judge nothing, silently.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match=pin):
        render_kpi(context, _kpi({"thresholds": thresholds}))


def test_color_grammar_matches_the_variant(tmp_path: Path) -> None:
    # The three consistency rules: a gradient requires its pair, a
    # pair belongs to gradient alone, fill needs a color source.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="variant 'gradient' requires 'color'"):
        render_kpi(context, _kpi({"variant": "gradient"}))
    with pytest.raises(ValueError, match="only variant 'gradient' accepts"):
        render_kpi(context, _kpi({"color": ["primary", "accent"]}))
    with pytest.raises(ValueError, match="variant 'fill' requires 'color'"):
        render_kpi(context, _kpi({"variant": "fill"}))


def test_color_must_be_theme_vocabulary(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="must be a theme token this theme declares"):
        render_kpi(context, _kpi({"color": "shiny"}))
    with pytest.raises(ValueError, match="this theme's series palette has"):
        render_kpi(context, _kpi({"color": "series-9"}))


def test_unknown_icon_teaches(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="unknown icon"):
        render_kpi(context, _kpi({"icon": "core-nope"}))


# ---------------------------------------------------------------------------
# Missing data: unavailable outcomes, carrying the store's own messages
# ---------------------------------------------------------------------------


def test_undeclared_artifact_renders_unavailable(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    message = _unavailable_message(context, _kpi({"artifact": "org.example.absent"}))
    assert "manifest declares no artifact" in message


def test_incomplete_artifact_renders_unavailable(tmp_path: Path) -> None:
    # A partial run's declaration is a fact about the run, not a bug
    # in the report.
    context = _context(_write_bundle(tmp_path, status="failed"))
    message = _unavailable_message(context, _kpi())
    assert "declared with status 'failed'" in message


def test_missing_artifact_file_renders_unavailable(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    (tmp_path / "stats.json").unlink()
    message = _unavailable_message(context, _kpi())
    assert "does not exist at" in message


def test_missing_key_renders_unavailable(tmp_path: Path) -> None:
    # The dotted path is data too: a key the artifact does not carry
    # is missing data, at any depth.
    context = _context(_write_bundle(tmp_path))
    assert "carries no key" in _unavailable_message(context, _kpi({"key": "absent"}))
    assert "carries no key" in _unavailable_message(context, _kpi({"key": "samples.z"}))


# ---------------------------------------------------------------------------
# Value-dependent judgments: the data's shape, taught where the data is
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["samples", "flag", "nothing"])
def test_key_must_name_a_scalar(tmp_path: Path, key: str) -> None:
    # Dicts, booleans, and null exist but are not headline numbers;
    # pointing 'key' at them is an authoring mistake.
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="does not name a scalar"):
        render_kpi(context, _kpi({"key": key}))


def test_thresholds_refuse_text_values(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    with pytest.raises(ValueError, match="thresholds cannot compare text"):
        render_kpi(context, _kpi({"key": "label", "thresholds": {"ok": {"above": 1}}}))


def test_non_json_artifact_is_a_layout_mistake(tmp_path: Path) -> None:
    context = _context(
        _write_bundle(tmp_path, fmt="tsv", content="depth\tcount\n12.4\t8\n")
    )
    with pytest.raises(ValueError, match="core.kpi reads JSON artifacts"):
        render_kpi(context, _kpi())


# ---------------------------------------------------------------------------
# The threshold policy: ok first, then notice, else failure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("thresholds", "expected_class"),
    [
        ({"ok": {"above": 10}}, "coda-kpi--ok"),
        ({"ok": {"above": 12.4}}, "coda-kpi--ok"),  # bounds are inclusive
        ({"ok": {"above": 10}, "notice": {"above": 5}}, "coda-kpi--ok"),  # ok wins
        ({"ok": {"above": 15}, "notice": {"above": 10}}, "coda-kpi--notice"),
        ({"ok": {"above": 15}, "notice": {"above": 20}}, "coda-kpi--failure"),
        ({"notice": {"above": 20}}, "coda-kpi--failure"),
        ({"ok": {"below": 20}}, "coda-kpi--ok"),
    ],
)
def test_threshold_policy_orders_statuses(
    tmp_path: Path, thresholds: JsonValue, expected_class: str
) -> None:
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _kpi({"thresholds": thresholds}))
    assert expected_class in html


# ---------------------------------------------------------------------------
# Variants and colors, against the default theme
# ---------------------------------------------------------------------------


def test_text_variant_renders_plain_by_default(tmp_path: Path) -> None:
    # No variant, no color, no policy: a neutral, uncolored card.
    context = _context(_write_bundle(tmp_path))
    assert _html(context, _kpi()).startswith('<div class="coda-kpi">')


def test_explicit_color_inks_the_value(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _kpi({"color": "primary"}))
    assert '<p class="coda-kpi__value" style="color: #0d6efd;">' in html


def test_series_colors_resolve(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _kpi({"color": "series-2"}))
    assert 'style="color: #d63384;"' in html  # the default palette's second entry


def test_status_supplies_the_ink_when_uncolored(tmp_path: Path) -> None:
    # The threshold policy's vocabulary colors the value: a failing
    # KPI wears danger ink without the author choosing it.
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _kpi({"thresholds": {"ok": {"above": 100}}}))
    assert 'style="color: #dc3545;"' in html
    assert "coda-kpi--failure" in html


def test_explicit_color_overrides_status_ink(tmp_path: Path) -> None:
    # One number, one ink: the author's color wins; the status class
    # stays for semantics.
    context = _context(_write_bundle(tmp_path))
    html = _html(
        context,
        _kpi({"color": "primary", "thresholds": {"ok": {"above": 100}}}),
    )
    assert 'style="color: #0d6efd;"' in html
    assert "coda-kpi--failure" in html


def test_fill_paints_the_plate_and_computes_readable_ink(tmp_path: Path) -> None:
    # White text on the dark primary plate — computed, not chosen.
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _kpi({"variant": "fill", "color": "primary"}))
    assert (
        '<div class="coda-kpi coda-kpi--fill" '
        'style="background: #0d6efd; color: #ffffff;">' in html
    )


def test_fill_on_warning_computes_dark_ink(tmp_path: Path) -> None:
    # The picker is not a hardcoded white: the light warning plate
    # takes the theme's dark text color.
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _kpi({"variant": "fill", "color": "warning"}))
    assert 'style="background: #ffc107; color: #212529;"' in html


def test_gradient_paints_both_stops(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _kpi({"variant": "gradient", "color": ["primary", "accent"]}))
    assert "linear-gradient(135deg, #0d6efd, #6610f2); color: #ffffff;" in html
    assert "coda-kpi--gradient" in html


def test_status_can_paint_the_fill(tmp_path: Path) -> None:
    # A threshold policy supplies the plate too: failing, uncolored,
    # filled — a solid danger card with readable ink.
    context = _context(_write_bundle(tmp_path))
    html = _html(
        context, _kpi({"variant": "fill", "thresholds": {"ok": {"above": 100}}})
    )
    assert 'style="background: #dc3545; color: #ffffff;"' in html


# ---------------------------------------------------------------------------
# Icons: shipped, namespaced, sanitized
# ---------------------------------------------------------------------------


def test_inline_icon_embeds_sanitized_markup(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _kpi({"icon": "core-check"}))
    assert 'class="coda-icon"' in html
    assert 'aria-hidden="true"' in html
    assert "</svg></p>" in html  # inline: inside the value line


def test_corner_icon_pins_to_the_cards_corner(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _kpi({"icon": "core-warning", "icon_position": "corner"}))
    assert '<span class="coda-kpi__corner">' in html
    assert "</svg></span>" in html
    assert "</svg></p>" not in html  # the value line stays icon-free


# ---------------------------------------------------------------------------
# Display formatting and escaping
# ---------------------------------------------------------------------------


def test_string_values_pass_through_verbatim(tmp_path: Path) -> None:
    # The producer's own formatting is data: strings render exactly as
    # the artifact wrote them, decimals or not.
    context = _context(_write_bundle(tmp_path))
    assert ">run-42<" in _html(context, _kpi({"key": "label"}))
    assert ">run-42<" in _html(context, _kpi({"key": "label", "decimals": 2}))


def test_decimals_round_for_display(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    assert ">12.4<" in _html(context, _kpi({"decimals": 1}))
    assert ">12<" in _html(context, _kpi({"decimals": 0}))


def test_unit_and_caption_escape_html(tmp_path: Path) -> None:
    # Unit and caption are author text inside a data page: anything
    # that looks like markup must render as visible text.
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _kpi({"unit": "<b>x</b>", "caption": "<i>note</i>"}))
    assert "&lt;b&gt;x&lt;/b&gt;" in html
    assert "&lt;i&gt;note&lt;/i&gt;" in html


def test_caption_renders_under_the_value(tmp_path: Path) -> None:
    context = _context(_write_bundle(tmp_path))
    html = _html(context, _kpi({"caption": "Falling fast"}))
    assert '<p class="coda-kpi__caption">Falling fast</p>' in html
