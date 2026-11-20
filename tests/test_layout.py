"""Tests for the report layout model: shape validation — the
grammar of tabs and composition nodes."""

import re
from datetime import date

import pytest
from factories import make_layout_payload
from pydantic import ValidationError

from workflow_coda.artifact_store import JsonValue
from workflow_coda.layout import (
    LAYOUT_SCHEMA_VERSION,
    CardNode,
    ComponentPlacement,
    DiagnosticsNode,
    GridLayout,
    MissingPolicy,
    ReportLayout,
    RowNode,
    UnavailablePolicy,
)


def layout_with(tabs: JsonValue) -> ReportLayout:
    """Validate a payload whose ``tabs`` are replaced wholesale."""
    return ReportLayout.model_validate(make_layout_payload(tabs=tabs))


def kpi(**overrides: JsonValue) -> dict[str, JsonValue]:
    """A placement node for the factory's component."""
    node: dict[str, JsonValue] = {"id": "example_bio.qc"}
    node.update(overrides)
    return node


# ---------------------------------------------------------------------------
# Valid layouts and defaults
# ---------------------------------------------------------------------------


def test_valid_layout_loads_with_defaults() -> None:
    layout = ReportLayout.model_validate(make_layout_payload())
    assert layout.schema_version == LAYOUT_SCHEMA_VERSION
    assert layout.title == "Metagenomic analysis"
    assert layout.subtitle is None
    assert layout.theme is None
    assert layout.logo is None
    assert layout.favicon is None
    assert layout.header_color is None
    assert layout.on_missing is MissingPolicy.FAIL
    assert layout.on_unavailable is UnavailablePolicy.NOTICE
    (tab,) = layout.tabs
    assert tab.title == "Quality control"
    (placement,) = tab.components
    assert isinstance(placement, ComponentPlacement)
    assert placement.id == "example_bio.qc"
    assert placement.parameters == {}
    assert placement.on_missing is None
    assert placement.on_unavailable is None
    assert placement.title is None


def test_optional_identity_fields_round_trip() -> None:
    layout = ReportLayout.model_validate(
        make_layout_payload(
            subtitle="Optional one-liner",
            theme="themes/ntnu.yaml",
            logo="assets/logo.png",
            favicon="assets/favicon.ico",
            header_color="accent",
        )
    )
    assert layout.subtitle == "Optional one-liner"
    assert layout.theme == "themes/ntnu.yaml"
    assert layout.logo == "assets/logo.png"
    assert layout.favicon == "assets/favicon.ico"
    assert layout.header_color == "accent"


def test_placement_constructs_directly_with_defaults() -> None:
    # The builder assembles placements from resolved lookups, so direct
    # construction (validation included) is part of the contract.
    placement = ComponentPlacement(id="example_bio.qc")
    assert placement.parameters == {}
    assert placement.on_missing is None


def test_placement_title_overrides_the_default() -> None:
    layout = layout_with([{"title": "QC", "components": [kpi(title="Mean depth")]}])
    (placement,) = layout.tabs[0].components
    assert isinstance(placement, ComponentPlacement)
    assert placement.title == "Mean depth"


# ---------------------------------------------------------------------------
# The header color: one theme token, taught by shape
# ---------------------------------------------------------------------------


def test_header_color_literals_teach_the_token_law() -> None:
    # A color literal is not a token name: the validator teaches the
    # move before any theme is loaded — declare the color in the
    # report's theme and name the token here.
    with pytest.raises(ValidationError, match="never a color literal"):
        ReportLayout.model_validate(make_layout_payload(header_color="#ff0000"))


@pytest.mark.parametrize(
    "bad",
    ["Background", "1background", "-background", "background_color", ""],
)
def test_header_color_must_be_a_token_shape(bad: str) -> None:
    # The canonical ThemeToken pattern — lowercase kebab-case — the
    # same shape every theme token carries, reused, not re-declared.
    with pytest.raises(ValidationError):
        ReportLayout.model_validate(make_layout_payload(header_color=bad))


# ---------------------------------------------------------------------------
# The composition grammar
# ---------------------------------------------------------------------------


def test_row_loads_with_split_ratios() -> None:
    layout = layout_with(
        [
            {
                "title": "QC",
                "components": [
                    {"type": "row", "split": [2, 1], "children": [kpi(), kpi()]}
                ],
            }
        ]
    )
    (node,) = layout.tabs[0].components
    assert isinstance(node, RowNode)
    assert node.split == (2.0, 1.0)
    assert len(node.children) == 2


def test_row_defaults_to_equal_widths_without_split() -> None:
    layout = layout_with(
        [{"title": "QC", "components": [{"type": "row", "children": [kpi(), kpi()]}]}]
    )
    (node,) = layout.tabs[0].components
    assert isinstance(node, RowNode)
    assert node.split is None


def test_row_split_must_match_children() -> None:
    with pytest.raises(ValidationError, match="one ratio per child"):
        layout_with(
            [
                {
                    "title": "QC",
                    "components": [
                        {"type": "row", "split": [1, 1, 1], "children": [kpi(), kpi()]}
                    ],
                }
            ]
        )


@pytest.mark.parametrize("bad", [0, -1, "1", "x"])
def test_split_ratios_must_be_positive_numbers(bad: JsonValue) -> None:
    with pytest.raises(ValidationError, match="split ratios must be"):
        layout_with(
            [
                {
                    "title": "QC",
                    "components": [
                        {"type": "row", "split": [bad, 1], "children": [kpi(), kpi()]}
                    ],
                }
            ]
        )


def test_split_ratios_reject_yaml_booleans() -> None:
    # A bare yes/no in a ratio list is a boolean in YAML 1.1 — it
    # would silently coerce to 1.0/0.0; the grammar refuses it first.
    with pytest.raises(ValidationError, match="parsed this entry as a boolean"):
        layout_with(
            [
                {
                    "title": "QC",
                    "components": [
                        {"type": "row", "split": [True, 1], "children": [kpi(), kpi()]}
                    ],
                }
            ]
        )


def test_splits_need_at_least_two_ratios() -> None:
    with pytest.raises(ValidationError, match="at least two ratios"):
        layout_with(
            [
                {
                    "title": "QC",
                    "components": [
                        {"type": "row", "split": [1], "children": [kpi(), kpi()]}
                    ],
                }
            ]
        )


def test_grid_requires_column_ratios() -> None:
    with pytest.raises(ValidationError, match="split"):
        layout_with(
            [{"title": "QC", "components": [{"type": "grid", "children": [kpi()]}]}]
        )


def test_grid_flows_children_into_ratio_columns() -> None:
    # A grid's split gives columns, not children: three children in
    # two columns leaves a short last row — valid by design.
    layout = layout_with(
        [
            {
                "title": "QC",
                "components": [
                    {"type": "grid", "split": [1, 1], "children": [kpi(), kpi(), kpi()]}
                ],
            }
        ]
    )
    (node,) = layout.tabs[0].components
    assert isinstance(node, GridLayout)
    assert node.split == (1.0, 1.0)
    assert len(node.children) == 3


def test_card_defaults_to_a_titled_stack() -> None:
    layout = layout_with(
        [{"title": "QC", "components": [{"type": "card", "children": [kpi()]}]}]
    )
    (node,) = layout.tabs[0].components
    assert isinstance(node, CardNode)
    assert node.title is None
    assert node.layout == "stack"
    assert node.split is None


def test_card_row_layout_takes_a_split() -> None:
    layout = layout_with(
        [
            {
                "title": "QC",
                "components": [
                    {
                        "type": "card",
                        "title": "Group",
                        "layout": "row",
                        "split": [2, 1],
                        "children": [kpi(), kpi()],
                    }
                ],
            }
        ]
    )
    (node,) = layout.tabs[0].components
    assert isinstance(node, CardNode)
    assert node.title == "Group"
    assert node.layout == "row"
    assert node.split == (2.0, 1.0)


def test_card_stack_rejects_a_split() -> None:
    with pytest.raises(ValidationError, match="a stack ignores 'split'"):
        layout_with(
            [
                {
                    "title": "QC",
                    "components": [
                        {"type": "card", "split": [1, 1], "children": [kpi(), kpi()]}
                    ],
                }
            ]
        )


def test_diagnostics_node_carries_no_keys() -> None:
    layout = layout_with([{"title": "QC", "components": [{"type": "diagnostics"}]}])
    (node,) = layout.tabs[0].components
    assert isinstance(node, DiagnosticsNode)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        layout_with(
            [{"title": "QC", "components": [{"type": "diagnostics", "title": "x"}]}]
        )


# ---------------------------------------------------------------------------
# Node dispatch: the grammar's front door
# ---------------------------------------------------------------------------


def test_a_node_is_a_placement_or_a_composition_never_both() -> None:
    with pytest.raises(ValidationError, match="never both"):
        layout_with(
            [{"title": "QC", "components": [{"id": "example_bio.qc", "type": "row"}]}]
        )


def test_a_node_needs_id_or_type() -> None:
    with pytest.raises(
        ValidationError,
        match=re.escape("needs either 'id' (to place a component) or 'type'"),
    ):
        layout_with([{"title": "QC", "components": [{"parameters": {}}]}])


def test_unknown_composition_types_teach_the_vocabulary() -> None:
    with pytest.raises(ValidationError, match="unknown composition type 'hero'"):
        layout_with([{"title": "QC", "components": [{"type": "hero"}]}])


def test_non_mapping_nodes_are_refused() -> None:
    with pytest.raises(ValidationError, match="must be a mapping"):
        layout_with([{"title": "QC", "components": ["just a string"]}])


def test_nodes_nest_through_every_level() -> None:
    # The grammar composes the way frames do: a card holding a
    # placement, a row, and a diagnostics marker inside that row.
    layout = layout_with(
        [
            {
                "title": "QC",
                "components": [
                    {
                        "type": "card",
                        "title": "Group",
                        "layout": "grid",
                        "split": [1, 1],
                        "children": [
                            kpi(),
                            {
                                "type": "row",
                                "split": [3, 1],
                                "children": [kpi(), {"type": "diagnostics"}],
                            },
                        ],
                    }
                ],
            }
        ]
    )
    (card,) = layout.tabs[0].components
    assert isinstance(card, CardNode)
    assert card.layout == "grid"
    row = card.children[1]
    assert isinstance(row, RowNode)
    assert isinstance(row.children[1], DiagnosticsNode)


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


def test_tab_titles_require_visible_text() -> None:
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
    with pytest.raises(ValidationError, match="not a component id"):
        layout_with([{"title": "QC", "components": [{"id": id}]}])


def test_schema_version_is_required_and_must_be_known() -> None:
    payload = make_layout_payload()
    del payload["schema_version"]
    with pytest.raises(
        ValidationError, match=f"Input should be '{LAYOUT_SCHEMA_VERSION}'"
    ):
        ReportLayout.model_validate(make_layout_payload(schema_version="9.9.9"))
    # Old versions are rejected here too; the loader teaches each
    # migration — 0.2.0 is this flip's own addition.
    with pytest.raises(
        ValidationError, match=f"Input should be '{LAYOUT_SCHEMA_VERSION}'"
    ):
        ReportLayout.model_validate(make_layout_payload(schema_version="0.2.0"))
    with pytest.raises(
        ValidationError, match=f"Input should be '{LAYOUT_SCHEMA_VERSION}'"
    ):
        ReportLayout.model_validate(make_layout_payload(schema_version="0.1.0"))


# ---------------------------------------------------------------------------
# Unknown keys and emptiness
# ---------------------------------------------------------------------------


def test_unknown_keys_rejected_at_every_level() -> None:
    # One concern, four levels: the layout, each tab, each node, and
    # each placement.  The unknown keys are typos of real field names
    # — the authoring mistake the strict models exist to catch — and
    # typo-keys can never become real fields, so the fixture cannot
    # rot.
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ReportLayout.model_validate(make_layout_payload(titel="Metagenomic analysis"))
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        layout_with(
            [{"title": "QC", "components": [{"id": "example_bio.qc"}], "componets": []}]
        )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        layout_with(
            [
                {
                    "title": "QC",
                    "components": [{"type": "row", "childrn": [], "children": [kpi()]}],
                }
            ]
        )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        layout_with(
            [{"title": "QC", "components": [{"id": "example_bio.qc", "paramters": {}}]}]
        )


def test_empty_tabs_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        ReportLayout.model_validate(make_layout_payload(tabs=[]))


def test_empty_component_lists_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        layout_with([{"title": "QC", "components": []}])


def test_the_toc_key_is_gone() -> None:
    # 0.2.0 removed the toc toggle: tabs are the navigation.  A stale
    # toc key is the likeliest leftover from a migrated file, so the
    # strict model refuses it like any unknown key.
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ReportLayout.model_validate(make_layout_payload(toc=False))


# ---------------------------------------------------------------------------
# Ordering and duplicate placements
# ---------------------------------------------------------------------------


def test_tabs_preserve_declaration_order() -> None:
    layout = layout_with(
        [
            {"title": "Quality control", "components": [{"id": "example_bio.qc"}]},
            {"title": "Taxonomy", "components": [{"id": "example_bio.taxonomy"}]},
        ]
    )
    assert [tab.title for tab in layout.tabs] == ["Quality control", "Taxonomy"]


def test_same_component_may_be_placed_twice() -> None:
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
    (tab,) = layout.tabs
    depths = []
    for node in tab.components:
        assert isinstance(node, ComponentPlacement)
        depths.append(node.parameters["min_depth"])
    assert depths == [10, 50]


# ---------------------------------------------------------------------------
# The placement policy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("policy", list(MissingPolicy))
def test_on_missing_accepts_every_policy_value(policy: MissingPolicy) -> None:
    layout = ReportLayout.model_validate(make_layout_payload(on_missing=policy.value))
    assert layout.on_missing is policy


def test_on_missing_rejects_unknown_values() -> None:
    with pytest.raises(ValidationError, match="on_missing"):
        ReportLayout.model_validate(make_layout_payload(on_missing="explode"))


def test_placement_on_missing_travels_into_composition_nodes() -> None:
    layout = layout_with(
        [
            {
                "title": "QC",
                "components": [
                    {
                        "type": "row",
                        "children": [{"id": "example_bio.qc", "on_missing": "skip"}],
                    }
                ],
            }
        ]
    )
    row = layout.tabs[0].components[0]
    assert isinstance(row, RowNode)
    placement = row.children[0]
    assert isinstance(placement, ComponentPlacement)
    assert placement.on_missing is MissingPolicy.SKIP


@pytest.mark.parametrize("policy", list(UnavailablePolicy))
def test_on_unavailable_accepts_every_policy_value(policy: UnavailablePolicy) -> None:
    layout = ReportLayout.model_validate(
        make_layout_payload(on_unavailable=policy.value)
    )
    assert layout.on_unavailable is policy


def test_on_unavailable_rejects_unknown_values() -> None:
    with pytest.raises(ValidationError, match="on_unavailable"):
        ReportLayout.model_validate(make_layout_payload(on_unavailable="explode"))


def test_placement_on_unavailable_travels_into_composition_nodes() -> None:
    layout = layout_with(
        [
            {
                "title": "QC",
                "components": [
                    {
                        "type": "row",
                        "children": [
                            {"id": "example_bio.qc", "on_unavailable": "skip"}
                        ],
                    }
                ],
            }
        ]
    )
    row = layout.tabs[0].components[0]
    assert isinstance(row, RowNode)
    placement = row.children[0]
    assert isinstance(placement, ComponentPlacement)
    assert placement.on_unavailable is UnavailablePolicy.SKIP


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
    (placement,) = layout.tabs[0].components
    assert isinstance(placement, ComponentPlacement)
    assert placement.parameters == parameters


def test_parameters_reject_non_json_values() -> None:
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
    with pytest.raises(ValidationError, match="frozen"):
        layout.title = "New title"  # type: ignore[misc]
    (placement,) = layout.tabs[0].components
    assert isinstance(placement, ComponentPlacement)
    with pytest.raises(ValidationError, match="frozen"):
        placement.id = "example.bio.other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# The author and version lines
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


def test_version_is_optional_and_round_trips() -> None:
    layout = ReportLayout.model_validate(make_layout_payload())
    assert layout.version is None
    layout = ReportLayout.model_validate(make_layout_payload(version="1.2.0"))
    assert layout.version == "1.2.0"


def test_version_requires_visible_text() -> None:
    with pytest.raises(ValidationError, match="must contain visible text"):
        ReportLayout.model_validate(make_layout_payload(version="  "))
