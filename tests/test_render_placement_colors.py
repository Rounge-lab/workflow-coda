"""Tests for render-local paired property scopes and generated CSS."""

from workflow_coda.components import (
    ComponentChrome,
    RenderedComponent,
    ThemeColorProperty,
)
from workflow_coda.render import _component_entry_html, _PlacementColors
from workflow_coda.report import ComponentEntry, EntryKind


def _entry(chrome: ComponentChrome = ComponentChrome.CARD) -> ComponentEntry:
    return ComponentEntry(
        kind=EntryKind.RENDERED,
        component_id="core.kpi",
        title="Metric",
        chrome=chrome,
        outcome=RenderedComponent.from_html(
            "<p>one body</p>",
            theme_colors=(
                ThemeColorProperty(
                    name="--coda-kpi-ink",
                    light="#123456",
                    dark="#abcdef",
                ),
            ),
        ),
    )


def test_repeated_entry_gets_distinct_placement_scopes() -> None:
    colors = _PlacementColors()
    entry = _entry()

    first = _component_entry_html(entry, colors)
    second = _component_entry_html(entry, colors)

    assert 'data-coda-placement="coda-placement-1"' in first
    assert 'data-coda-placement="coda-placement-2"' in second
    assert first.count("one body") == 1
    assert second.count("one body") == 1
    assert 'style="' not in first
    assert "<style" not in first


def test_tile_scope_is_on_framework_wrapper() -> None:
    body = _component_entry_html(_entry(ComponentChrome.TILE), _PlacementColors())

    assert body.startswith(
        '<article class="coda-tile" data-component="core.kpi" '
        'data-coda-placement="coda-placement-1">'
    )
    assert "<h3>" not in body


def test_generated_rules_cover_screen_modes_and_light_print() -> None:
    colors = _PlacementColors()
    _component_entry_html(_entry(), colors)
    css = colors.css()

    assert css.startswith(
        '[data-coda-placement="coda-placement-1"] {\n  --coda-kpi-ink: #123456;\n}'
    )
    assert "@media screen and (prefers-color-scheme: dark)" in css
    assert ":root:not([data-coda-theme]) [data-coda-placement=" in css
    assert ':root[data-coda-theme="light"] [data-coda-placement=' in css
    assert ':root[data-coda-theme="dark"] [data-coda-placement=' in css

    print_css = css.split("@media print {", 1)[1]
    assert "#123456" in print_css
    assert "#abcdef" not in print_css
    assert "data-coda-theme" not in print_css


def test_scope_allocation_is_local_to_each_render_walk() -> None:
    first = _component_entry_html(_entry(), _PlacementColors())
    second = _component_entry_html(_entry(), _PlacementColors())

    assert first == second
    assert 'data-coda-placement="coda-placement-1"' in first


def test_outcome_without_properties_preserves_existing_wrapper() -> None:
    colors = _PlacementColors()
    entry = ComponentEntry(
        kind=EntryKind.RENDERED,
        component_id="core.example",
        title="Example",
        outcome=RenderedComponent.from_html("<p>body</p>"),
    )

    body = _component_entry_html(entry, colors)

    assert "data-coda-placement" not in body
    assert colors.css() == ""
