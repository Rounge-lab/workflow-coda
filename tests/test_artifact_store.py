"""Tests for the artifact store: resolution, safety checks, and readers."""

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest
from factories import (
    ReportBundle,
    make_artifact_payload,
    make_manifest_payload,
    write_artifact_bundle,
    write_manifest_file,
    write_report_bundle,
)
from helpers import symlink_or_skip

from workflow_coda.artifact_store import ArtifactStore
from workflow_coda.errors import (
    ArtifactChecksumError,
    ArtifactReadError,
    ArtifactResolutionError,
    ArtifactStoreError,
    ArtifactUnavailableError,
    WorkflowCodaError,
)
from workflow_coda.manifest import load_manifest

METRICS_TYPE = "org.example.sample_metrics"


@pytest.fixture
def bundle(tmp_path: Path) -> ReportBundle:
    return write_report_bundle(tmp_path)


@pytest.fixture
def store(bundle: ReportBundle) -> ArtifactStore:
    return ArtifactStore.from_manifest_file(bundle.manifest_path)


# ---------------------------------------------------------------------------
# Construction and properties
# ---------------------------------------------------------------------------


def test_direct_construction_uses_explicit_root(tmp_path: Path) -> None:
    declaration = make_artifact_payload()
    artifact_bundle = write_artifact_bundle(
        tmp_path, declaration, "sample_id\tpassed\n"
    )
    manifest = load_manifest(artifact_bundle.manifest_path)
    direct_store = ArtifactStore(manifest, tmp_path)
    assert direct_store.root == tmp_path.resolve()
    assert direct_store.require(METRICS_TYPE).read_tsv() == []


def test_properties_expose_manifest_and_root(
    bundle: ReportBundle, tmp_path: Path
) -> None:
    artifact_store = ArtifactStore.from_manifest_file(bundle.manifest_path)
    assert artifact_store.root == tmp_path.resolve()
    assert artifact_store.manifest.schema_version == "0.2.0"


# ---------------------------------------------------------------------------
# Membership and inspection
# ---------------------------------------------------------------------------


def test_declared_types_lists_all_declared_types(store: ArtifactStore) -> None:
    assert store.declared_types == frozenset(
        {
            "org.example.sample_metrics",
            "org.example.qc_summary",
            "org.example.votu_catalog",
        }
    )


def test_contains_reports_declaration_only(store: ArtifactStore) -> None:
    assert "org.example.qc_summary" in store
    assert "org.example.absent" not in store


def test_declared_types_includes_incomplete_artifacts(tmp_path: Path) -> None:
    declaration = make_artifact_payload(status="failed")
    artifact_bundle = write_artifact_bundle(tmp_path, declaration, content=None)
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    assert METRICS_TYPE in artifact_store.declared_types
    assert METRICS_TYPE in artifact_store


def test_find_returns_declaration_for_declared_type(store: ArtifactStore) -> None:
    declaration = store.find("org.example.qc_summary")
    assert declaration is not None
    assert declaration.id == "qc_summary"


def test_find_returns_none_for_undeclared_type(store: ArtifactStore) -> None:
    assert store.find("org.example.absent") is None


def test_find_ignores_status_and_filesystem(tmp_path: Path) -> None:
    # A partially-declared artifact whose file does not exist is still
    # inspectable: find is declaration-only by contract.
    declaration = make_artifact_payload(status="partial")
    artifact_bundle = write_artifact_bundle(tmp_path, declaration, content=None)
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    found = artifact_store.find(METRICS_TYPE)
    assert found is not None
    assert found.id == "sample_metrics"


# require: success
def test_require_resolves_declared_complete_artifact(
    bundle: ReportBundle, store: ArtifactStore
) -> None:
    resolved = store.require(METRICS_TYPE)
    assert resolved.declaration.id == "sample_metrics"
    assert resolved.path == bundle.metrics_path.resolve()
    assert resolved.path.is_absolute()
    assert resolved.path.is_relative_to(store.root)


# require: expected unavailability
def test_require_rejects_undeclared_type(store: ArtifactStore) -> None:
    with pytest.raises(ArtifactUnavailableError) as exc_info:
        store.require("org.example.absent")
    message = str(exc_info.value)
    assert "org.example.absent" in message
    assert (
        "(declared: org.example.qc_summary, "
        "org.example.sample_metrics, org.example.votu_catalog)" in message
    )


def test_require_on_empty_manifest_lists_no_types(tmp_path: Path) -> None:
    manifest_path = write_manifest_file(tmp_path, make_manifest_payload(artifacts=[]))
    artifact_store = ArtifactStore.from_manifest_file(manifest_path)
    with pytest.raises(ArtifactUnavailableError, match="declared: none"):
        artifact_store.require("org.example.anything")


@pytest.mark.parametrize("status", ["partial", "failed", "missing"])
def test_require_rejects_incomplete_statuses(tmp_path: Path, status: str) -> None:
    # The file exists: the status alone must block loading.
    declaration = make_artifact_payload(status=status)
    artifact_bundle = write_artifact_bundle(tmp_path, declaration, "a\tb\n")
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    with pytest.raises(ArtifactUnavailableError) as exc_info:
        artifact_store.require(METRICS_TYPE)
    message = str(exc_info.value)
    assert f"status '{status}'" in message
    assert "status 'complete'" in message


def test_require_rejects_missing_artifact_file(tmp_path: Path) -> None:
    declaration = make_artifact_payload()
    artifact_bundle = write_artifact_bundle(tmp_path, declaration, content=None)
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    with pytest.raises(ArtifactUnavailableError) as exc_info:
        artifact_store.require(METRICS_TYPE)
    assert "does not exist" in str(exc_info.value)


# require: resolution failures
def test_require_rejects_directory_at_artifact_path(tmp_path: Path) -> None:
    # A directory existing at the declared artifact path is an integrity
    # problem, not expected missing data: the path exists but is not a
    # regular file, so require must raise ArtifactResolutionError.
    declaration = make_artifact_payload(path="report_data")
    artifact_bundle = write_artifact_bundle(tmp_path, declaration, content=None)
    artifact_bundle.artifact_path.mkdir()
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    with pytest.raises(ArtifactResolutionError) as exc_info:
        artifact_store.require(METRICS_TYPE)
    assert "is not a regular file" in str(exc_info.value)


def test_require_rejects_symlink_escape(tmp_path: Path) -> None:
    bundle_root = tmp_path / "results"
    bundle_root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("s3cret\n", encoding="utf-8")
    declaration = make_artifact_payload(path="report_data/link.tsv")
    artifact_bundle = write_artifact_bundle(bundle_root, declaration, content=None)
    symlink_or_skip(secret, bundle_root / "report_data" / "link.tsv")
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    with pytest.raises(ArtifactResolutionError) as exc_info:
        artifact_store.require(METRICS_TYPE)
    assert "outside the manifest root" in str(exc_info.value)


def test_require_allows_symlink_inside_root(tmp_path: Path) -> None:
    # A symlink that stays within the bundle is legal: containment is about
    # location, not the presence of links.
    bundle_root = tmp_path / "results"
    bundle_root.mkdir()
    declaration = make_artifact_payload(
        id="alias", type="org.example.alias", path="report_data/alias.tsv"
    )
    artifact_bundle = write_artifact_bundle(bundle_root, declaration, content=None)
    target = bundle_root / "report_data" / "table.tsv"
    target.write_text("sample_id\tpassed\nS1\ttrue\n", encoding="utf-8", newline="\n")
    symlink_or_skip(target, artifact_bundle.artifact_path)
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    rows = artifact_store.require("org.example.alias").read_tsv()
    assert rows == [{"sample_id": "S1", "passed": "true"}]


# ---------------------------------------------------------------------------
# Checksum verification
# ---------------------------------------------------------------------------


def test_read_verifies_matching_checksum(store: ArtifactStore) -> None:
    rows = store.require("org.example.votu_catalog").read_tsv()
    assert rows == [{"votu_id": "vOTU_001", "quality": "medium"}]


def test_require_defers_checksum_verification_to_reads(
    bundle: ReportBundle,
) -> None:
    # require is cheap: existence, regular file, containment.  The checksum
    # is verified over the exact bytes a read parses.
    bundle.catalog_path.write_text("tampered\n", encoding="utf-8", newline="\n")
    artifact_store = ArtifactStore.from_manifest_file(bundle.manifest_path)
    resolved = artifact_store.require("org.example.votu_catalog")
    with pytest.raises(ArtifactChecksumError):
        resolved.read_tsv()


@pytest.mark.parametrize("method", ["read_tsv", "read_json", "read_text", "read_bytes"])
def test_checksum_verification_precedes_parsing(
    bundle: ReportBundle, method: str
) -> None:
    # The checksummed artifact is TSV-shaped; a read_json on it would fail
    # at parsing — unless verification runs first, as it must.
    bundle.catalog_path.write_text("tampered\n", encoding="utf-8", newline="\n")
    artifact_store = ArtifactStore.from_manifest_file(bundle.manifest_path)
    resolved = artifact_store.require("org.example.votu_catalog")
    reader: Callable[[], object] = getattr(resolved, method)
    with pytest.raises(ArtifactChecksumError):
        reader()


def test_checksum_error_names_both_digests(bundle: ReportBundle) -> None:
    bundle.catalog_path.write_text("tampered\n", encoding="utf-8", newline="\n")
    artifact_store = ArtifactStore.from_manifest_file(bundle.manifest_path)
    declaration = artifact_store.find("org.example.votu_catalog")
    assert declaration is not None
    assert declaration.sha256 is not None
    actual = hashlib.sha256(b"tampered\n").hexdigest()
    with pytest.raises(ArtifactChecksumError) as exc_info:
        artifact_store.require("org.example.votu_catalog").read_tsv()
    message = str(exc_info.value)
    assert "failed its sha256 check" in message
    assert declaration.sha256 in message
    assert actual in message


def test_artifact_without_checksum_is_not_verified(
    bundle: ReportBundle, store: ArtifactStore
) -> None:
    bundle.metrics_path.write_text(
        "sample_id\tpassed\nS3\ttrue\n", encoding="utf-8", newline="\n"
    )
    rows = store.require(METRICS_TYPE).read_tsv()
    assert rows == [{"sample_id": "S3", "passed": "true"}]


# ---------------------------------------------------------------------------
# read_tsv contract
# ---------------------------------------------------------------------------


def test_read_tsv_returns_rows_as_dicts(store: ArtifactStore) -> None:
    rows = store.require(METRICS_TYPE).read_tsv()
    assert rows == [
        {"sample_id": "S1", "passed": "true"},
        {"sample_id": "S2", "passed": "false"},
    ]


def test_read_tsv_accepts_header_only_table(tmp_path: Path) -> None:
    declaration = make_artifact_payload()
    artifact_bundle = write_artifact_bundle(tmp_path, declaration, "a\tb\n")
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    assert artifact_store.require(METRICS_TYPE).read_tsv() == []


def test_read_tsv_skips_blank_lines(tmp_path: Path) -> None:
    declaration = make_artifact_payload()
    artifact_bundle = write_artifact_bundle(tmp_path, declaration, "a\tb\n\nS1\tx\n\n")
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    assert artifact_store.require(METRICS_TYPE).read_tsv() == [{"a": "S1", "b": "x"}]


def test_read_tsv_accepts_crlf_line_endings(tmp_path: Path) -> None:
    # Producers on Windows may write CRLF; the reader tolerates it and no
    # '\r' leaks into field values.  (Fixtures elsewhere pin LF; this test
    # deliberately does not.)
    declaration = make_artifact_payload()
    artifact_bundle = write_artifact_bundle(
        tmp_path, declaration, "a\tb\nS1\tx\n", newline="\r\n"
    )
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    assert artifact_store.require(METRICS_TYPE).read_tsv() == [{"a": "S1", "b": "x"}]


def test_read_tsv_rejects_empty_file(tmp_path: Path) -> None:
    declaration = make_artifact_payload()
    artifact_bundle = write_artifact_bundle(tmp_path, declaration, "")
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    with pytest.raises(ArtifactReadError) as exc_info:
        artifact_store.require(METRICS_TYPE).read_tsv()
    assert "contains no header row" in str(exc_info.value)


def test_read_tsv_rejects_empty_header_row(tmp_path: Path) -> None:
    declaration = make_artifact_payload()
    artifact_bundle = write_artifact_bundle(tmp_path, declaration, "\n\n")
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    with pytest.raises(ArtifactReadError) as exc_info:
        artifact_store.require(METRICS_TYPE).read_tsv()
    assert "has an empty header row" in str(exc_info.value)


def test_read_tsv_rejects_empty_column_name(tmp_path: Path) -> None:
    declaration = make_artifact_payload()
    artifact_bundle = write_artifact_bundle(tmp_path, declaration, "\tpassed\nS1\tx\n")
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    with pytest.raises(ArtifactReadError) as exc_info:
        artifact_store.require(METRICS_TYPE).read_tsv()
    assert "has an empty header column name" in str(exc_info.value)


def test_read_tsv_rejects_duplicate_column_names(tmp_path: Path) -> None:
    declaration = make_artifact_payload()
    artifact_bundle = write_artifact_bundle(
        tmp_path, declaration, "sample_id\tsample_id\nS1\ttrue\n"
    )
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    with pytest.raises(ArtifactReadError) as exc_info:
        artifact_store.require(METRICS_TYPE).read_tsv()
    assert "duplicate header column 'sample_id'" in str(exc_info.value)


def test_read_tsv_rejects_ragged_rows(tmp_path: Path) -> None:
    declaration = make_artifact_payload()
    artifact_bundle = write_artifact_bundle(tmp_path, declaration, "a\tb\nS1\tx\nS2\n")
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    with pytest.raises(ArtifactReadError) as exc_info:
        artifact_store.require(METRICS_TYPE).read_tsv()
    message = str(exc_info.value)
    assert "row at line 3" in message
    assert "expected 2" in message


def test_read_tsv_supports_default_csv_quoting(tmp_path: Path) -> None:
    declaration = make_artifact_payload()
    artifact_bundle = write_artifact_bundle(
        tmp_path, declaration, 'a\tnote\nS1\t"a\tb"\n'
    )
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    rows = artifact_store.require(METRICS_TYPE).read_tsv()
    assert rows == [{"a": "S1", "note": "a\tb"}]


def test_read_tsv_decodes_utf8(tmp_path: Path) -> None:
    declaration = make_artifact_payload()
    artifact_bundle = write_artifact_bundle(
        tmp_path, declaration, "sample_id\tname\nS1\tSæ1\n"
    )
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    rows = artifact_store.require(METRICS_TYPE).read_tsv()
    assert rows == [{"sample_id": "S1", "name": "Sæ1"}]


def test_read_tsv_rejects_invalid_utf8(tmp_path: Path) -> None:
    declaration = make_artifact_payload()
    artifact_bundle = write_artifact_bundle(tmp_path, declaration, b"a\t\xff\n")
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    with pytest.raises(ArtifactReadError) as exc_info:
        artifact_store.require(METRICS_TYPE).read_tsv()
    assert "is not valid UTF-8" in str(exc_info.value)


def test_readers_are_explicit_not_format_dispatched(tmp_path: Path) -> None:
    # Deliberate design pin: the read method is the plugin's explicit
    # command; the declared format is metadata, not a gate.  This test
    # exists so a future "fix" that adds format dispatch is a conscious
    # decision, not a silent behavior change.
    declaration = make_artifact_payload(format="json")
    artifact_bundle = write_artifact_bundle(tmp_path, declaration, "a\tb\nS1\tx\n")
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    assert artifact_store.require(METRICS_TYPE).read_tsv() == [{"a": "S1", "b": "x"}]


# ---------------------------------------------------------------------------
# read_json contract
# ---------------------------------------------------------------------------


def test_read_json_returns_parsed_document(store: ArtifactStore) -> None:
    payload = store.require("org.example.qc_summary").read_json()
    assert payload == {"passed": 1, "total_samples": 2}


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("[1, 2]", [1, 2]),
        ('"hello"', "hello"),
        ("3.5", 3.5),
        ("null", None),
        ("true", True),
    ],
)
def test_read_json_returns_any_json_document(
    tmp_path: Path, content: str, expected: object
) -> None:
    # Transport only: content schema validation belongs to plugins, so
    # non-object documents pass through unexamined.
    declaration = make_artifact_payload(
        id="summary",
        type="org.example.summary",
        path="report_data/summary.json",
        format="json",
    )
    artifact_bundle = write_artifact_bundle(tmp_path, declaration, content)
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    assert artifact_store.require("org.example.summary").read_json() == expected


def test_read_json_rejects_invalid_json(tmp_path: Path) -> None:
    declaration = make_artifact_payload(
        id="summary",
        type="org.example.summary",
        path="report_data/summary.json",
        format="json",
    )
    artifact_bundle = write_artifact_bundle(tmp_path, declaration, "{")
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    with pytest.raises(ArtifactReadError) as exc_info:
        artifact_store.require("org.example.summary").read_json()
    message = str(exc_info.value)
    assert "not valid JSON" in message
    assert "line 1" in message


# ---------------------------------------------------------------------------
# read_text
# ---------------------------------------------------------------------------


def test_read_text_returns_decoded_contents(store: ArtifactStore) -> None:
    artifact = store.require(METRICS_TYPE)
    assert artifact.read_text() == "sample_id\tpassed\nS1\ttrue\nS2\tfalse\n"


# ---------------------------------------------------------------------------
# read_bytes
# ---------------------------------------------------------------------------


def test_read_bytes_returns_raw_contents(store: ArtifactStore) -> None:
    artifact = store.require(METRICS_TYPE)
    assert artifact.read_bytes() == b"sample_id\tpassed\nS1\ttrue\nS2\tfalse\n"


def test_read_bytes_is_the_binary_door(tmp_path: Path) -> None:
    # Bytes no UTF-8 reader can decode pass through read_bytes
    # uninterpreted — the door a plugin-defined format (a BAM, an
    # image) reads its artifacts through: checksum-verified like
    # every other reader, gated by nothing.  The declared format is
    # namespaced — a convention this framework does not interpret —
    # and the read is the plugin's explicit command.
    declaration = make_artifact_payload(format="bio.newick")
    png_magic = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    artifact_bundle = write_artifact_bundle(tmp_path, declaration, png_magic)
    artifact_store = ArtifactStore.from_manifest_file(artifact_bundle.manifest_path)
    assert artifact_store.require(METRICS_TYPE).read_bytes() == png_magic


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------


def test_store_errors_share_the_framework_root() -> None:
    for error_type in (
        ArtifactUnavailableError,
        ArtifactResolutionError,
        ArtifactChecksumError,
        ArtifactReadError,
    ):
        assert issubclass(error_type, ArtifactStoreError)
        assert issubclass(error_type, WorkflowCodaError)


def test_framework_error_boundary_catches_store_errors(store: ArtifactStore) -> None:
    # The report builder's recovery boundary: every store failure is
    # catchable as a single framework error type.
    with pytest.raises(WorkflowCodaError):
        store.require("org.example.absent")
