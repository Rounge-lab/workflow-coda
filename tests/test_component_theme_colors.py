"""Contracts for placement-local paired color declarations."""

import pytest

from workflow_coda.components import (
    ComponentStatus,
    RenderedComponent,
    ThemeColorProperty,
)


def _property(name: str = "--coda-kpi-ink") -> ThemeColorProperty:
    return ThemeColorProperty(
        name=name,
        light="#123456",
        dark="#abcdef",
    )


def test_html_helper_carries_paired_properties() -> None:
    declaration = _property()
    outcome = RenderedComponent.from_html(
        "<p>one body</p>",
        theme_colors=(declaration,),
    )

    assert outcome.theme_colors == (declaration,)
    assert outcome.html == "<p>one body</p>"


def test_existing_outcomes_default_to_no_paired_properties() -> None:
    assert RenderedComponent.from_html("<p>body</p>").theme_colors == ()
    assert RenderedComponent.unavailable("missing").theme_colors == ()
    assert RenderedComponent.skipped().theme_colors == ()


@pytest.mark.parametrize(
    "name",
    [
        "",
        "color",
        "--other-ink",
        "--coda-Uppercase",
        "--coda-ink; color",
        "--coda-ink}",
        "--coda-ink</style>",
        None,
    ],
)
def test_property_names_are_closed_css_identifiers(name: object) -> None:
    with pytest.raises(ValueError, match="custom-property name"):
        ThemeColorProperty(
            name=name,  # type: ignore[arg-type]
            light="#123456",
            dark="#abcdef",
        )


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize(
    "value",
    ["red", "#fff", "#12345678", "#gggggg", "#123456;", "", None],
)
def test_values_require_six_digit_hexes(mode: str, value: object) -> None:
    with pytest.raises(ValueError, match=f"{mode} requires"):
        ThemeColorProperty(
            name="--coda-kpi-ink",
            light=value if mode == "light" else "#123456",  # type: ignore[arg-type]
            dark=value if mode == "dark" else "#abcdef",  # type: ignore[arg-type]
        )


def test_duplicate_property_names_are_rejected() -> None:
    with pytest.raises(ValueError, match="unique property names"):
        RenderedComponent.from_html(
            "<p>body</p>",
            theme_colors=(_property(), _property()),
        )


@pytest.mark.parametrize(
    "status",
    [ComponentStatus.UNAVAILABLE, ComponentStatus.SKIPPED],
)
def test_degraded_outcomes_cannot_carry_paired_properties(
    status: ComponentStatus,
) -> None:
    with pytest.raises(ValueError, match="OK outcomes only"):
        RenderedComponent(
            status=status,
            message="missing" if status is ComponentStatus.UNAVAILABLE else None,
            theme_colors=(_property(),),
        )


def test_transport_requires_a_tuple_of_typed_declarations() -> None:
    with pytest.raises(ValueError, match="tuple of ThemeColorProperty"):
        RenderedComponent.from_html(
            "<p>body</p>",
            theme_colors=[_property()],  # type: ignore[arg-type]
        )


def test_paired_properties_preserve_outcome_value_semantics() -> None:
    first = RenderedComponent.from_html("<p>body</p>", theme_colors=(_property(),))
    second = RenderedComponent.from_html("<p>body</p>", theme_colors=(_property(),))

    assert first == second
    assert hash(first) == hash(second)
