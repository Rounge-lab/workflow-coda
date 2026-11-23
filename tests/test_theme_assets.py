"""Tests for framework-owned theme assets and their loading boundary."""

from importlib import resources
from pathlib import Path

import pytest
import yaml
from factories import make_theme_payload

from workflow_coda.errors import FrameworkAssetError
from workflow_coda.theme import (
    DEFAULT_THEME,
    bundled,
    bundled_theme_names,
    load_bundled_theme,
)
from workflow_coda.theme.bundled import _load_bundled_theme


def test_default_constant_matches_its_packaged_declaration() -> None:
    # Was a hardcoded model; now the YAML asset is authoritative.
    # Reading it again pins against stale or wrong-file wiring.
    assert _load_bundled_theme("default") == DEFAULT_THEME


def test_default_asset_has_disciplined_newlines() -> None:
    path = resources.files("workflow_coda.theme") / "assets" / "default.yaml"
    data = path.read_bytes()
    assert not data.startswith(b"\n")
    assert data.endswith(b"\n")
    assert not data.endswith(b"\n\n")
    assert b"\r" not in data


def _mock_asset_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    assets = tmp_path / "assets"
    assets.mkdir()

    def files(_package: str) -> Path:
        return tmp_path

    monkeypatch.setattr(bundled.resources, "files", files)
    return assets


def test_missing_bundled_asset_is_an_installation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_asset_root(tmp_path, monkeypatch)
    with pytest.raises(FrameworkAssetError) as exc_info:
        _load_bundled_theme("missing")

    assert "workflow_coda.theme/assets/missing.yaml" in str(exc_info.value)
    assert "reinstall it" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, OSError)


@pytest.mark.parametrize(
    "content",
    [
        b"name: one\nname: two\n",
        b"- a list\n",
        b"name: incomplete\n",
        b"name: [\n",
        b"\xff",
    ],
)
def test_invalid_bundled_asset_is_an_installation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: bytes,
) -> None:
    assets = _mock_asset_root(tmp_path, monkeypatch)
    (assets / "broken.yaml").write_bytes(content)

    with pytest.raises(FrameworkAssetError) as exc_info:
        _load_bundled_theme("broken")

    assert "workflow_coda.theme/assets/broken.yaml" in str(exc_info.value)
    assert "reinstall it" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_shipped_default_is_discovered() -> None:
    assert "default" in bundled_theme_names()


def test_every_shipped_theme_validates() -> None:
    names = bundled_theme_names()
    assert names
    for name in sorted(names):
        load_bundled_theme(name)


def test_discovery_uses_filenames_without_parsing_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assets = _mock_asset_root(tmp_path, monkeypatch)
    (assets / "example-dark.yaml").write_text("not a valid theme\n", encoding="utf-8")
    assert bundled_theme_names() == frozenset({"example-dark"})


def test_discovery_ignores_non_yaml_files_and_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assets = _mock_asset_root(tmp_path, monkeypatch)
    (assets / "README.txt").write_text("notes\n", encoding="utf-8")
    (assets / "nested.yaml").mkdir()
    assert bundled_theme_names() == frozenset()


def test_missing_asset_directory_is_an_installation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assets = _mock_asset_root(tmp_path, monkeypatch)
    assets.rmdir()

    with pytest.raises(FrameworkAssetError) as exc_info:
        bundled_theme_names()

    assert "workflow_coda.theme/assets" in str(exc_info.value)
    assert "reinstall it" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, OSError)


@pytest.mark.parametrize(
    "filename",
    ["Default.yaml", "example_dark.yaml", "-example.yaml", "1example.yaml"],
)
def test_invalid_shipped_filename_is_an_installation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
) -> None:
    assets = _mock_asset_root(tmp_path, monkeypatch)
    (assets / filename).write_text("name: example\n", encoding="utf-8")

    with pytest.raises(FrameworkAssetError) as exc_info:
        bundled_theme_names()

    assert filename in str(exc_info.value)
    assert "lowercase kebab-case" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_unknown_name_teaches_sorted_roster_and_custom_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assets = _mock_asset_root(tmp_path, monkeypatch)
    for name in ("zebra", "alpha"):
        (assets / f"{name}.yaml").write_text("", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        load_bundled_theme("missing")

    message = str(exc_info.value)
    assert "unknown bundled theme 'missing'" in message
    assert "available: alpha, zebra" in message
    assert "theme.yaml" in message
    assert "./my-theme" in message


def test_unknown_name_with_empty_roster_teaches_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_asset_root(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="available: none"):
        load_bundled_theme("missing")


def test_public_loading_reads_selected_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assets = _mock_asset_root(tmp_path, monkeypatch)
    payload = make_theme_payload(name="Human-readable display name")
    (assets / "example.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")

    theme = load_bundled_theme("example")
    assert theme.name == "Human-readable display name"
    assert theme.model_dump() == payload


def test_public_loading_returns_independent_theme_instances() -> None:
    first = load_bundled_theme("default")
    second = load_bundled_theme("default")

    assert first == second == DEFAULT_THEME
    assert first is not second
    assert first is not DEFAULT_THEME
    assert first.colors is not second.colors
    assert first.colors is not DEFAULT_THEME.colors


def test_public_loading_preserves_bundled_validation_error_family(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assets = _mock_asset_root(tmp_path, monkeypatch)
    (assets / "broken.yaml").write_text("name: incomplete\n", encoding="utf-8")

    with pytest.raises(FrameworkAssetError) as exc_info:
        load_bundled_theme("broken")

    assert "broken.yaml" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_public_loading_rejects_paths_as_unknown_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_asset_root(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="unknown bundled theme"):
        load_bundled_theme("../outside")
