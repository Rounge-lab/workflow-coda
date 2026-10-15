"""Tests for the layout loader: YAML text to a validated 0.2.0
layout, with the 0.1.0 migration taught."""

import re
from pathlib import Path

import pytest

from workflow_coda.errors import LayoutError
from workflow_coda.layout import (
    ComponentPlacement,
    DiagnosticsNode,
    MissingPolicy,
    ReportLayout,
    RowNode,
)
from workflow_coda.layout_loader import load_layout


def write_layout(tmp_path: Path, text: str) -> Path:
    """Write *text* to a layout file and return its path."""
    path = tmp_path / "report_layout.yaml"
    path.write_text(text, encoding="utf-8")
    return path


MINIMAL_YAML = """\
schema_version: "0.2.0"
title: Metagenomic analysis
tabs:
  - title: Quality control
    components:
      - id: example_bio.qc
        parameters:
          min_depth: 10
"""

COMPOSITION_YAML = """\
schema_version: "0.2.0"
title: Metagenomic analysis
tabs:
  - title: Quality control
    components:
      - type: row
        split: [3, 1]
        children:
          - id: example_bio.qc
          - type: diagnostics
"""


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_loads_minimal_layout_with_defaults(tmp_path: Path) -> None:
    layout = load_layout(write_layout(tmp_path, MINIMAL_YAML))
    assert isinstance(layout, ReportLayout)
    assert layout.title == "Metagenomic analysis"
    assert layout.subtitle is None
    assert layout.theme is None
    assert layout.logo is None
    assert layout.favicon is None
    assert layout.on_missing is MissingPolicy.FAIL
    (tab,) = layout.tabs
    assert tab.title == "Quality control"
    (placement,) = tab.components
    assert isinstance(placement, ComponentPlacement)
    assert placement.id == "example_bio.qc"
    assert placement.parameters == {"min_depth": 10}
    assert isinstance(placement.parameters["min_depth"], int)


def test_optional_fields_and_policy_round_trip_through_file(
    tmp_path: Path,
) -> None:
    text = """\
schema_version: "0.2.0"
title: Metagenomic analysis
subtitle: Optional one-liner
theme: themes/ntnu.yaml
logo: assets/logo.png
favicon: assets/favicon.ico
on_missing: notice
tabs:
  - title: Quality control
    components:
      - id: example_bio.qc
        parameters:
          show_legend: true
          min_abundance: 0.01
"""
    layout = load_layout(write_layout(tmp_path, text))
    assert layout.subtitle == "Optional one-liner"
    assert layout.theme == "themes/ntnu.yaml"
    assert layout.logo == "assets/logo.png"
    assert layout.favicon == "assets/favicon.ico"
    # The YAML word "notice" becomes the enum member by value.
    assert layout.on_missing is MissingPolicy.NOTICE
    (tab,) = layout.tabs
    (placement,) = tab.components
    assert isinstance(placement, ComponentPlacement)
    assert placement.parameters["show_legend"] is True
    assert placement.parameters["min_abundance"] == 0.01


def test_composition_loads_through_a_file(tmp_path: Path) -> None:
    # The dispatch's end-to-end proof through real YAML: a row with a
    # split, a placement child, and a diagnostics marker child all
    # become their real node models.
    layout = load_layout(write_layout(tmp_path, COMPOSITION_YAML))
    (tab,) = layout.tabs
    (node,) = tab.components
    assert isinstance(node, RowNode)
    assert node.split == (3.0, 1.0)
    assert isinstance(node.children[0], ComponentPlacement)
    assert isinstance(node.children[1], DiagnosticsNode)


# ---------------------------------------------------------------------------
# Reading and parsing failures
# ---------------------------------------------------------------------------


def test_missing_file_raises_layout_error(tmp_path: Path) -> None:
    with pytest.raises(LayoutError, match="cannot read the layout file"):
        load_layout(tmp_path / "does_not_exist.yaml")


def test_invalid_yaml_raises_layout_error(tmp_path: Path) -> None:
    text = "tabs:\n  - [unclosed\n"
    with pytest.raises(LayoutError, match="not valid YAML"):
        load_layout(write_layout(tmp_path, text))


def test_duplicate_key_reports_key_and_line(tmp_path: Path) -> None:
    text = "title: Run report\ntitle: Other\n"
    with pytest.raises(
        LayoutError,
        match=re.escape("duplicate key 'title' on line 2"),
    ):
        load_layout(write_layout(tmp_path, text))


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "contains nothing (the file is empty)"),
        (
            "- title: Quality control\n  components:\n    - id: example_bio.qc\n",
            "contains a list — did the first tab line lose its 'title:' key?",
        ),
        ("Metagenomic analysis\n", "contains a single str value"),
    ],
)
def test_non_mapping_documents_rejected(
    tmp_path: Path, content: str, message: str
) -> None:
    with pytest.raises(LayoutError, match=re.escape(message)):
        load_layout(write_layout(tmp_path, content))


# ---------------------------------------------------------------------------
# The schema version: the 0.1.0 migration, and unknown or trapped
# versions
# ---------------------------------------------------------------------------


def test_0_1_0_layout_is_taught_the_migration(tmp_path: Path) -> None:
    # The likeliest real file in the wild: last week's layout.  The
    # loader names the version and spells out every edit.
    text = MINIMAL_YAML.replace('"0.2.0"', '"0.1.0"').replace("tabs:", "sections:")
    with pytest.raises(
        LayoutError,
        match=re.escape("declares schema_version 0.1.0")
        + ".*"
        + re.escape("rename 'sections:' to 'tabs:'"),
    ):
        load_layout(write_layout(tmp_path, text))


def test_unknown_schema_versions_are_refused(tmp_path: Path) -> None:
    text = MINIMAL_YAML.replace('"0.2.0"', '"9.9.9"')
    with pytest.raises(
        LayoutError,
        match=re.escape('must be "0.2.0"') + ".*" + re.escape("declares '9.9.9'"),
    ):
        load_layout(write_layout(tmp_path, text))


def test_boolean_schema_version_teaches_the_quoting_rule(tmp_path: Path) -> None:
    # A bare yes in the version field is a YAML boolean; the version
    # check passes it through to the strict model, whose refusal the
    # loader explains with the trap.
    text = MINIMAL_YAML.replace('schema_version: "0.2.0"', "schema_version: yes")
    with pytest.raises(LayoutError, match="YAML parsed this as the boolean True"):
        load_layout(write_layout(tmp_path, text))


# ---------------------------------------------------------------------------
# Model violations through files, with teaching messages
# ---------------------------------------------------------------------------


def test_boolean_in_title_teaches_the_quoting_rule(tmp_path: Path) -> None:
    text = MINIMAL_YAML.replace("title: Metagenomic analysis", "title: no")
    with pytest.raises(
        LayoutError,
        match=r'YAML parsed this as the boolean False.*e\.g\. title: "yes"',
    ):
        load_layout(write_layout(tmp_path, text))


def test_boolean_in_policy_field_explains_too(tmp_path: Path) -> None:
    text = MINIMAL_YAML.replace(
        'schema_version: "0.2.0"', 'schema_version: "0.2.0"\non_missing: no'
    )
    # The union field produces the explanation per branch; the valid
    # values ride along in pydantic's parenthetical message.
    with pytest.raises(LayoutError, match="YAML parsed this as the boolean False"):
        load_layout(write_layout(tmp_path, text))


def test_model_violation_names_the_path_into_the_file(tmp_path: Path) -> None:
    # Every node goes through the dispatch, so even a top-level
    # placement folds its member errors at the node: the node path
    # first, the field riding in the message after it.
    text = MINIMAL_YAML.replace("- id: example_bio.qc", "- id: qc")
    with pytest.raises(
        LayoutError,
        match=re.escape("tabs[0].components[0]: id") + ".*not a component id",
    ):
        load_layout(write_layout(tmp_path, text))


def test_every_problem_is_listed_not_just_the_first(tmp_path: Path) -> None:
    text = MINIMAL_YAML.replace("title: Metagenomic analysis", 'title: "   "').replace(
        "- id: example_bio.qc", "- id: qc"
    )
    with pytest.raises(LayoutError) as excinfo:
        load_layout(write_layout(tmp_path, text))
    message = str(excinfo.value)
    assert "must contain visible text" in message
    assert "not a component id" in message


def test_non_json_parameter_names_the_field(tmp_path: Path) -> None:
    # The fold names the node path, then the field — with the JSON
    # union's branch attempts riding along after it.
    text = MINIMAL_YAML.replace("min_depth: 10", "when: 2026-10-12")
    with pytest.raises(
        LayoutError,
        match=re.escape("tabs[0].components[0]: parameters.when"),
    ):
        load_layout(write_layout(tmp_path, text))


def test_unknown_top_level_key_rejected_through_file(tmp_path: Path) -> None:
    text = MINIMAL_YAML + "titel: Run report\n"
    with pytest.raises(
        LayoutError,
        match=re.escape("titel: Extra inputs are not permitted"),
    ):
        load_layout(write_layout(tmp_path, text))


# ---------------------------------------------------------------------------
# Composition violations through files: the dispatch's folded
# teaching messages
# ---------------------------------------------------------------------------


def test_row_split_mismatch_teaches_through_a_file(tmp_path: Path) -> None:
    text = COMPOSITION_YAML.replace("split: [3, 1]", "split: [1, 1, 1]")
    with pytest.raises(LayoutError, match="one ratio per child"):
        load_layout(write_layout(tmp_path, text))


def test_boolean_split_ratio_teaches_the_yaml_trap(tmp_path: Path) -> None:
    # The ratio validator refuses the boolean before pydantic could
    # coerce it to 1.0 — the silent nonsense split, caught and
    # explained through a real file.
    text = COMPOSITION_YAML.replace("split: [3, 1]", "split: [yes, 1]")
    with pytest.raises(
        LayoutError,
        match=re.escape(
            "split ratios must be numbers — YAML parsed this entry as a boolean"
        ),
    ):
        load_layout(write_layout(tmp_path, text))


def test_unknown_composition_type_teaches_the_vocabulary(tmp_path: Path) -> None:
    text = COMPOSITION_YAML.replace("type: row", "type: hero")
    with pytest.raises(LayoutError, match="unknown composition type 'hero'"):
        load_layout(write_layout(tmp_path, text))


def test_member_violations_inside_a_composition_name_the_node(tmp_path: Path) -> None:
    # A bad id inside a row's children: the dispatch folds the member
    # error and the outer path names the exact node — the deepest
    # teaching path the grammar has.
    text = COMPOSITION_YAML.replace("- id: example_bio.qc", "- id: qc")
    with pytest.raises(
        LayoutError,
        match=re.escape("tabs[0].components[0]: children.0: id")
        + ".*not a component id",
    ):
        load_layout(write_layout(tmp_path, text))
