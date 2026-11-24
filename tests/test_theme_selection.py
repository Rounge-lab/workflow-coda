"""Tests for the layout's explicit light/dark theme declaration."""

import pytest
from pydantic import ValidationError

from workflow_coda.layout import ThemeSelection


def test_selection_accepts_bundled_names() -> None:
    selection = ThemeSelection(light="default", dark="default-dark")
    assert selection.light == "default"
    assert selection.dark == "default-dark"


def test_selection_accepts_independent_name_and_path_vocabularies() -> None:
    selection = ThemeSelection(
        light="default",
        dark="./themes/custom-dark.yaml",
    )
    assert selection.light == "default"
    assert selection.dark == "./themes/custom-dark.yaml"


def test_selection_preserves_values_exactly_and_round_trips() -> None:
    payload = {
        "light": "themes/My Light Theme.yaml",
        "dark": "./my-dark-theme",
    }
    selection = ThemeSelection.model_validate(payload)
    assert selection.model_dump() == payload
    assert ThemeSelection.model_validate(selection.model_dump()) == selection


@pytest.mark.parametrize(
    ("payload", "missing"),
    [
        ({}, {"light", "dark"}),
        ({"light": "default"}, {"dark"}),
        ({"dark": "default-dark"}, {"light"}),
    ],
)
def test_selection_requires_both_entries(
    payload: dict[str, str],
    missing: set[str],
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ThemeSelection.model_validate(payload)

    assert {
        error["loc"][0]
        for error in exc_info.value.errors()
        if error["type"] == "missing"
    } == missing


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_selection_requires_visible_text(mode: str, value: str) -> None:
    payload = {"light": "default", "dark": "default-dark"}
    payload[mode] = value

    with pytest.raises(ValidationError, match="must contain visible text"):
        ThemeSelection.model_validate(payload)


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize("value", [None, True, 5, [], {}])
def test_selection_rejects_non_string_entries(mode: str, value: object) -> None:
    payload: dict[str, object] = {
        "light": "default",
        "dark": "default-dark",
    }
    payload[mode] = value

    with pytest.raises(ValidationError):
        ThemeSelection.model_validate(payload)


def test_selection_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ThemeSelection.model_validate(
            {
                "light": "default",
                "dark": "default-dark",
                "system": "default",
            }
        )


def test_selection_is_frozen() -> None:
    selection = ThemeSelection(light="default", dark="default-dark")

    with pytest.raises(ValidationError, match="frozen"):
        selection.light = "other"  # type: ignore[misc]


def test_selection_does_not_resolve_names_or_paths() -> None:
    # Shape belongs here; existence belongs to the builder.
    selection = ThemeSelection(
        light="not-a-shipped-theme",
        dark="./missing-theme.yaml",
    )
    assert selection.light == "not-a-shipped-theme"
    assert selection.dark == "./missing-theme.yaml"
