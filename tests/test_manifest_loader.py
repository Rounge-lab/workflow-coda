"""Tests for manifest loading from files."""

import json
from pathlib import Path

import pytest
from factories import make_manifest_payload, make_producer_payload, write_manifest_file
from pydantic import ValidationError

from workflow_coda.artifact_store import ArtifactStore
from workflow_coda.errors import ManifestError
from workflow_coda.manifest import (
    MANIFEST_SCHEMA_VERSION,
    ReportManifest,
    load_manifest,
)

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_loads_valid_manifest(tmp_path: Path) -> None:
    path = write_manifest_file(
        tmp_path,
        make_manifest_payload(
            producer=make_producer_payload(run_id="2026-10-01T103012Z")
        ),
    )
    manifest = load_manifest(path)
    assert isinstance(manifest, ReportManifest)
    assert manifest.schema_version == MANIFEST_SCHEMA_VERSION
    assert manifest.producer.run_id == "2026-10-01T103012Z"
    assert len(manifest.artifacts) == 1


def test_accepts_string_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_manifest_file(tmp_path, make_manifest_payload())
    monkeypatch.chdir(tmp_path)
    manifest = load_manifest("report_manifest.json")
    assert manifest.producer.name == "Example workflow"


def test_loading_does_not_require_artifact_files(tmp_path: Path) -> None:
    # The default artifact payload's file is never created; loading validates
    # the envelope only, and touching artifact files is the store's job.
    path = write_manifest_file(tmp_path, make_manifest_payload())
    manifest = load_manifest(path)
    assert len(manifest.artifacts) == 1


# ---------------------------------------------------------------------------
# Error wrapping
# ---------------------------------------------------------------------------


def test_missing_file_wraps_os_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(ManifestError) as exc_info:
        load_manifest(missing)
    message = str(exc_info.value)
    assert "could not read manifest" in message
    assert str(missing) in message
    assert isinstance(exc_info.value.__cause__, FileNotFoundError)


def test_directory_path_wraps_os_error(tmp_path: Path) -> None:
    # IsADirectoryError on POSIX, PermissionError on Windows: either way an
    # OSError that the loader must wrap rather than leak.
    with pytest.raises(ManifestError) as exc_info:
        load_manifest(tmp_path)
    assert "could not read manifest" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, OSError)


def test_invalid_utf8_is_wrapped(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(b'{"producer": "\xff\xfe"}')
    with pytest.raises(ManifestError) as exc_info:
        load_manifest(path)
    assert "not valid UTF-8" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, UnicodeDecodeError)


def test_invalid_json_is_wrapped(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text('{"schema_version": }', encoding="utf-8")
    with pytest.raises(ManifestError) as exc_info:
        load_manifest(path)
    message = str(exc_info.value)
    assert "not valid JSON" in message
    assert "line 1" in message
    assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)


def test_empty_file_is_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ManifestError, match=r"not valid JSON at line 1, column 1"):
        load_manifest(path)


def test_invalid_envelope_is_wrapped(tmp_path: Path) -> None:
    # An envelope violation beyond the version gate — the pre-check
    # owns version-only failures now, so the wrapping is exercised
    # through a nested field violation.
    path = write_manifest_file(
        tmp_path,
        make_manifest_payload(producer=make_producer_payload(name="")),
    )
    with pytest.raises(ManifestError) as exc_info:
        load_manifest(path)
    message = str(exc_info.value)
    assert "is invalid" in message
    assert "name" in message  # nested field path survives wrapping
    assert isinstance(exc_info.value.__cause__, ValidationError)


def test_unknown_schema_version_teaches(tmp_path: Path) -> None:
    # The version pre-check, lean by ruling — pre-release, no
    # migration prose: the message names the declared version and
    # the one this workflow-coda reads.
    path = write_manifest_file(tmp_path, make_manifest_payload(schema_version="0.1.0"))
    with pytest.raises(ManifestError) as exc_info:
        load_manifest(path)
    message = str(exc_info.value)
    assert f'must be "{MANIFEST_SCHEMA_VERSION}"' in message
    assert "'0.1.0'" in message


def test_old_manifest_version_teaches_regeneration(tmp_path: Path) -> None:
    """The clean break: the 0.2.0 envelope is not read, and the
    teaching names the way forward — regenerate with verify."""
    declared = make_manifest_payload(schema_version="0.2.0")
    path = write_manifest_file(tmp_path, declared)
    with pytest.raises(ManifestError) as excinfo:
        load_manifest(path)
    message = str(excinfo.value)
    assert f'must be "{MANIFEST_SCHEMA_VERSION}"' in message
    assert "declares '0.2.0'" in message
    assert "regenerate" in message


# ---------------------------------------------------------------------------
# BOM handling
# ---------------------------------------------------------------------------


def test_leading_bom_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(b"\xef\xbb\xbf{}")
    with pytest.raises(ManifestError, match="byte order mark"):
        load_manifest(path)


def test_bom_is_only_rejected_at_start(tmp_path: Path) -> None:
    # A U+FEFF inside a JSON string is legal content and must parse.
    payload = make_manifest_payload()
    payload["producer"] = make_producer_payload(name="Example\ufeffworkflow")
    path = write_manifest_file(tmp_path, payload)
    manifest = load_manifest(path)
    assert manifest.producer.name == "Example\ufeffworkflow"


# ---------------------------------------------------------------------------
# ArtifactStore.from_manifest_file
# ---------------------------------------------------------------------------


def test_from_manifest_file_roots_at_manifest_directory(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    manifest_path = write_manifest_file(results_dir, make_manifest_payload())
    store = ArtifactStore.from_manifest_file(manifest_path)
    assert store.root == results_dir.resolve()
    assert store.manifest.producer.name == "Example workflow"


def test_from_manifest_file_resolves_artifact_against_root(tmp_path: Path) -> None:
    # End-to-end wiring: file -> envelope -> store -> verified contents.
    artifact_dir = tmp_path / "report_data"
    artifact_dir.mkdir()
    (artifact_dir / "sample_metrics.tsv").write_text(
        "sample_id\tpassed\nS1\ttrue\n", encoding="utf-8", newline="\n"
    )
    manifest_path = write_manifest_file(tmp_path, make_manifest_payload())
    store = ArtifactStore.from_manifest_file(manifest_path)
    resolved = store.require("org.example.sample_metrics")
    assert resolved.declaration.id == "sample_metrics"
    assert resolved.read_text() == "sample_id\tpassed\nS1\ttrue\n"


def test_from_manifest_file_propagates_load_errors(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="could not read manifest"):
        ArtifactStore.from_manifest_file(tmp_path / "absent.json")


def test_from_manifest_file_symlink_root_is_real_parent(tmp_path: Path) -> None:
    # A symlinked manifest is rooted at its *real* location: the bundle its
    # relative artifact paths refer to lives around the actual file.
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    manifest_path = write_manifest_file(real_dir, make_manifest_payload())
    link_path = tmp_path / "link.json"
    try:
        link_path.symlink_to(manifest_path)
    except OSError:
        pytest.skip("symbolic link creation not permitted on this platform")
    store = ArtifactStore.from_manifest_file(link_path)
    assert store.root == real_dir.resolve()
