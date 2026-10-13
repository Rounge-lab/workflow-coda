"""Tests for the report layout model: shape validation."""

from datetime import date

import pytest
from factories import make_layout_payload
from pydantic import ValidationError

from workflow_coda.artifact_store import JsonValue
from workflow_coda.layout import (
    ComponentPlacement,
    MissingPolicy,
    ReportLayout,
)


def layout_with(sections: JsonValue) -> ReportLayout:
    """Validate a payload whose ``sections`` are replaced wholesale."""
    return ReportLayout.model_validate(make_layout_payload(sections=sections))


# ---------------------------------------------------------------------------
# Valid layouts and defaults
# ---------------------------------------------------------------------------


def test_valid_layout_loads_with_defaults() -> None:
    layout = ReportLayout.model_validate(make_layout_payload())
    assert layout.schema_version == "0.1.0"
    assert layout.title == "Metagenomic analysis"
    assert layout.subtitle is None
    assert layout.theme is None
    assert layout.logo is None
    assert layout.favicon is None
    assert layout.on_missing is MissingPolicy.FAIL
    (section,) = layout.sections
    assert section.title == "Quality control"
    (placement,) = section.components
    assert placement.id == "example_bio.qc"
    assert placement.parameters == {}
    assert placement.on_missing is None


def test_optional_identity_fields_round_trip() -> None:
    layout = ReportLayout.model_validate(
        make_layout_payload(
            subtitle="Optional one-liner",
            theme="themes/ntnu.yaml",
            logo="assets/logo.png",
            favicon="assets/favicon.ico",
        )
    )
    assert layout.subtitle == "Optional one-liner"
    assert layout.theme == "themes/ntnu.yaml"
    assert layout.logo == "assets/logo.png"
    assert layout.favicon == "assets/favicon.ico"


def test_placement_constructs_directly_with_defaults() -> None:
    # The builder assembles placements from resolved lookups, so direct
    # construction (validation included) is part of the contract.
    placement = ComponentPlacement(id="example_bio.qc")
    assert placement.parameters == {}
    assert placement.on_missing is None


# ---------------------------------------------------------------------------
# Visible-text gates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["title", "subtitle", "theme", "logo", "favicon"])
def test_identity_fields_require_visible_text(field: str) -> None:
    with pytest.raises(ValidationError, match="must contain visible text"):
        ReportLayout.model_validate(make_layout_payload(**{field: "   "}))


def test_empty_title_rejected() -> None:
    with pytest.raises(ValidationError, match="must contain visible text"):
        ReportLayout.model_validate(make_layout_payload(title=""))


def test_section_titles_require_visible_text() -> None:
    with pytest.raises(ValidationError, match="must contain visible text"):
        layout_with([{"title": "  ", "components": [{"id": "example_bio.qc"}]}])


# ---------------------------------------------------------------------------
# Component id shape and schema version
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "id",
    ["qc", "example.bio.qc", "Example.qc", "example.QC", "", ".qc"],
)
def test_placements_require_component_id_shape(id: str) -> None:
    # The grammar itself is pinned in test_components; these pin that
    # the placement path enforces the shared pattern.
    with pytest.raises(ValidationError, match="not a component id"):
        layout_with([{"title": "QC", "components": [{"id": id}]}])


def test_schema_version_is_required_and_must_be_known() -> None:
    payload = make_layout_payload()
    del payload["schema_version"]
    with pytest.raises(ValidationError, match="schema_version"):
        ReportLayout.model_validate(payload)
    with pytest.raises(ValidationError, match="schema_version"):
        ReportLayout.model_validate(make_layout_payload(schema_version="9.9.9"))


# ---------------------------------------------------------------------------
# Unknown keys and emptiness
# ---------------------------------------------------------------------------


def test_unknown_keys_rejected_at_every_level() -> None:
    # One concern, three levels: extra="forbid" on the layout, on each
    # section, and on each placement.  The unknown keys are typos of
    # real field names — the authoring mistake the strict models exist
    # to catch — and typo-keys can never become real fields, so the
    # fixture cannot rot.
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ReportLayout.model_validate(make_layout_payload(titel="Metagenomic analysis"))
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        layout_with(
            [
                {
                    "title": "QC",
                    "components": [{"id": "example_bio.qc"}],
                    "componets": [],
                }
            ]
        )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        layout_with(
            [{"title": "QC", "components": [{"id": "example_bio.qc", "paramters": {}}]}]
        )


def test_empty_sections_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        ReportLayout.model_validate(make_layout_payload(sections=[]))


def test_empty_component_lists_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        layout_with([{"title": "QC", "components": []}])


# ---------------------------------------------------------------------------
# Ordering and duplicate placements
# ---------------------------------------------------------------------------


def test_sections_preserve_declaration_order() -> None:
    layout = layout_with(
        [
            {"title": "Quality control", "components": [{"id": "example_bio.qc"}]},
            {"title": "Taxonomy", "components": [{"id": "example_bio.taxonomy"}]},
        ]
    )
    assert [section.title for section in layout.sections] == [
        "Quality control",
        "Taxonomy",
    ]


def test_same_component_may_be_placed_twice() -> None:
    # A placement is an instance, not a reference: one component with
    # two parameterizations is a feature, not a conflict.
    layout = layout_with(
        [
            {
                "title": "QC",
                "components": [
                    {"id": "example_bio.qc", "parameters": {"min_depth": 10}},
                    {"id": "example_bio.qc", "parameters": {"min_depth": 50}},
                ],
            }
        ]
    )
    (section,) = layout.sections
    assert [p.parameters["min_depth"] for p in section.components] == [10, 50]


# ---------------------------------------------------------------------------
# The missing policy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("policy", list(MissingPolicy))
def test_on_missing_accepts_every_policy_value(policy: MissingPolicy) -> None:
    layout = ReportLayout.model_validate(make_layout_payload(on_missing=policy.value))
    assert layout.on_missing is policy


def test_on_missing_rejects_unknown_values() -> None:
    with pytest.raises(ValidationError, match="on_missing"):
        ReportLayout.model_validate(make_layout_payload(on_missing="explode"))


def test_placement_on_missing_overrides_the_layout_default() -> None:
    layout = layout_with(
        [
            {
                "title": "QC",
                "components": [{"id": "example_bio.qc", "on_missing": "skip"}],
            }
        ]
    )
    assert layout.sections[0].components[0].on_missing is MissingPolicy.SKIP


# ---------------------------------------------------------------------------
# Parameter transport
# ---------------------------------------------------------------------------


def test_parameters_preserve_json_values_exactly() -> None:
    parameters: dict[str, JsonValue] = {
        "min_depth": 10,
        "min_abundance": 0.01,
        "show_legend": True,
        "label": "QC",
        "samples": ["A", "B"],
        "nested": {"a": 1},
        "nothing": None,
    }
    layout = layout_with(
        [
            {
                "title": "QC",
                "components": [{"id": "example_bio.qc", "parameters": parameters}],
            }
        ]
    )
    assert layout.sections[0].components[0].parameters == parameters


def test_parameters_reject_non_json_values() -> None:
    # YAML's richer types (dates, sets, binary) are rejected by the
    # model itself, with the field named.  The loader tests pin the
    # same rejection through a real YAML file.
    with pytest.raises(ValidationError, match="parameters.when"):
        layout_with(
            [
                {
                    "title": "QC",
                    "components": [
                        {
                            "id": "example_bio.qc",
                            "parameters": {"when": date(2026, 10, 12)},  # type: ignore[dict-item]
                        }
                    ],
                }
            ]
        )


# ---------------------------------------------------------------------------
# Frozen semantics
# ---------------------------------------------------------------------------


def test_layout_is_frozen() -> None:
    layout = ReportLayout.model_validate(make_layout_payload())
    # mypy's pydantic plugin already flags frozen-field writes at type
    # time; the ignores let the test pin the runtime ValidationError.
    with pytest.raises(ValidationError, match="frozen"):
        layout.title = "New title"  # type: ignore[misc]
    with pytest.raises(ValidationError, match="frozen"):
        layout.sections[0].components[0].id = "example.bio.other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# The table of contents toggle
# ---------------------------------------------------------------------------


def test_toc_defaults_to_true() -> None:
    layout = ReportLayout.model_validate(make_layout_payload())
    assert layout.toc is True


def test_toc_explicit_false_round_trips() -> None:
    layout = ReportLayout.model_validate(make_layout_payload(toc=False))
    assert layout.toc is False


def test_toc_rejects_non_boolean_values() -> None:
    with pytest.raises(ValidationError, match="toc"):
        ReportLayout.model_validate(make_layout_payload(toc="sometimes"))


# ---------------------------------------------------------------------------
# The author line
# ---------------------------------------------------------------------------


def test_author_is_optional_and_round_trips() -> None:
    layout = ReportLayout.model_validate(make_layout_payload())
    assert layout.author is None
    layout = ReportLayout.model_validate(
        make_layout_payload(author="The Genomics Group")
    )
    assert layout.author == "The Genomics Group"


def test_author_requires_visible_text() -> None:
    with pytest.raises(ValidationError, match="must contain visible text"):
        ReportLayout.model_validate(make_layout_payload(author="  "))


# ---------------------------------------------------------------------------
# The report version
# ---------------------------------------------------------------------------


def test_version_is_optional_and_round_trips() -> None:
    layout = ReportLayout.model_validate(make_layout_payload())
    assert layout.version is None
    layout = ReportLayout.model_validate(make_layout_payload(version="1.2.0"))
    assert layout.version == "1.2.0"


def test_version_requires_visible_text() -> None:
    with pytest.raises(ValidationError, match="must contain visible text"):
        ReportLayout.model_validate(make_layout_payload(version="  "))
