"""Tests for custom theme files and their authoring-error boundary."""

from pathlib import Path

import pytest
import yaml
from factories import make_theme_payload

from workflow_coda.errors import LayoutError
from workflow_coda.theme import Theme, load_theme


def test_custom_theme_loads_from_path_or_string(tmp_path: Path) -> None:
    payload = make_theme_payload(name="Custom theme")
    path = tmp_path / "theme.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    expected = Theme.model_validate(payload)
    assert load_theme(path) == expected
    assert load_theme(str(path)) == expected


def test_missing_custom_theme_chains_read_failure(tmp_path: Path) -> None:
    path = tmp_path / "missing.yaml"

    with pytest.raises(LayoutError) as exc_info:
        load_theme(path)

    assert str(path) in str(exc_info.value)
    assert "cannot read the theme file" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, OSError)


def test_custom_theme_requires_utf8(tmp_path: Path) -> None:
    path = tmp_path / "theme.yaml"
    path.write_bytes(b"\xff")

    with pytest.raises(LayoutError) as exc_info:
        load_theme(path)

    assert str(path) in str(exc_info.value)
    assert "not valid UTF-8" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, UnicodeDecodeError)


@pytest.mark.parametrize(
    ("text", "teaching"),
    [
        ("", "must be a mapping of theme tokens"),
        ("- a list\n", "must be a mapping of theme tokens"),
        ("name: [\n", "not valid YAML"),
        (
            "name: one\nname: two\n",
            "not valid YAML: duplicate key 'name' on line 2",
        ),
        ("name: incomplete\n", "is not a valid theme"),
    ],
)
def test_invalid_custom_theme_names_file_and_chains_failure(
    tmp_path: Path, text: str, teaching: str
) -> None:
    path = tmp_path / "theme.yaml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(LayoutError) as exc_info:
        load_theme(path)

    assert str(path) in str(exc_info.value)
    assert teaching in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, ValueError)
