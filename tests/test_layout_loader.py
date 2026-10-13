"""Tests for the layout loader: YAML text to a validated layout."""

import re
from pathlib import Path

import pytest

from workflow_coda.errors import LayoutError
from workflow_coda.layout import MissingPolicy, ReportLayout
from workflow_coda.layout_loader import load_layout


def write_layout(tmp_path: Path, text: str) -> Path:
    """Write *text* to a layout file and return its path."""
    path = tmp_path / "report_layout.yaml"
    path.write_text(text, encoding="utf-8")
    return path


MINIMAL_YAML = """\
schema_version: "0.1.0"
title: Metagenomic analysis
sections:
  - title: Quality control
    components:
      - id: example_bio.qc
        parameters:
          min_depth: 10
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
    (section,) = layout.sections
    assert section.title == "Quality control"
    (placement,) = section.components
    assert placement.id == "example_bio.qc"
    assert placement.parameters == {"min_depth": 10}
    assert isinstance(placement.parameters["min_depth"], int)


def test_optional_fields_and_policy_round_trip_through_file(
    tmp_path: Path,
) -> None:
    text = """\
schema_version: "0.1.0"
title: Metagenomic analysis
subtitle: Optional one-liner
theme: themes/ntnu.yaml
logo: assets/logo.png
favicon: assets/favicon.ico
on_missing: notice
sections:
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
    parameters = layout.sections[0].components[0].parameters
    assert parameters["show_legend"] is True
    assert parameters["min_abundance"] == 0.01


# ---------------------------------------------------------------------------
# Reading and parsing failures
# ---------------------------------------------------------------------------


def test_missing_file_raises_layout_error(tmp_path: Path) -> None:
    with pytest.raises(LayoutError, match="cannot read the layout file"):
        load_layout(tmp_path / "does_not_exist.yaml")


def test_invalid_yaml_raises_layout_error(tmp_path: Path) -> None:
    text = "sections:\n  - [unclosed\n"
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
            "contains a list — did the first section line lose its 'title:' key?",
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
        'schema_version: "0.1.0"', 'schema_version: "0.1.0"\non_missing: no'
    )
    # The union field produces the explanation per branch; the valid
    # values ride along in pydantic's parenthetical message.
    with pytest.raises(LayoutError, match="YAML parsed this as the boolean False"):
        load_layout(write_layout(tmp_path, text))


def test_model_violation_names_the_path_into_the_file(tmp_path: Path) -> None:
    text = MINIMAL_YAML.replace("- id: example_bio.qc", "- id: qc")
    with pytest.raises(
        LayoutError,
        match=re.escape("sections[0].components[0].id") + ".*not a component id",
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
    text = MINIMAL_YAML.replace("min_depth: 10", "when: 2026-10-12")
    with pytest.raises(
        LayoutError,
        match=re.escape("sections[0].components[0].parameters.when"),
    ):
        load_layout(write_layout(tmp_path, text))


def test_unknown_top_level_key_rejected_through_file(tmp_path: Path) -> None:
    text = MINIMAL_YAML + "author: me\n"
    with pytest.raises(
        LayoutError,
        match=re.escape("author: Extra inputs are not permitted"),
    ):
        load_layout(write_layout(tmp_path, text))
