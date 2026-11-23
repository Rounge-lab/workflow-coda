"""Tests for framework-owned theme assets and their loading boundary."""

from importlib import resources
from pathlib import Path

import pytest

from workflow_coda.errors import FrameworkAssetError
from workflow_coda.theme import DEFAULT_THEME, bundled
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
