"""Tests for the artifact declaration model.

The constrained type aliases in ``workflow_coda.manifest.types`` have no
behavior of their own; they are exercised through the declaration fields
tested here.
"""

import pytest
from helpers import assert_frozen
from pydantic import ValidationError

from workflow_coda.manifest import (
    ArtifactDeclaration,
    ArtifactFormat,
    ArtifactStatus,
)

BASE_DECLARATION: dict[str, str] = {
    "id": "sample_metrics",
    "type": "org.example.sample_metrics",
    "schema_version": "1.0",
    "path": "report_data/sample_metrics.tsv",
    "format": "tsv",
    "status": "complete",
}
"""Minimal valid artifact declaration payload."""

VALID_SHA256 = "a" * 64
"""A syntactically valid lowercase hexadecimal SHA-256 digest."""


def make(**overrides: object) -> dict[str, object]:
    """Return a fresh valid declaration payload with fields overridden."""
    return {**BASE_DECLARATION, **overrides}


def invalid_fields(exc: ValidationError) -> set[str]:
    """Top-level field names reported by a validation error."""
    return {str(error["loc"][-1]) for error in exc.errors()}


def test_valid_declaration_parses() -> None:
    declaration = ArtifactDeclaration.model_validate(make())
    assert declaration.id == "sample_metrics"
    assert declaration.type == "org.example.sample_metrics"
    assert declaration.schema_version == "1.0"
    assert declaration.path == "report_data/sample_metrics.tsv"
    assert declaration.format is ArtifactFormat.TSV
    assert declaration.status is ArtifactStatus.COMPLETE
    assert declaration.sha256 is None


def test_required_fields_are_enforced() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ArtifactDeclaration.model_validate({})
    assert invalid_fields(exc_info.value) == {
        "id",
        "type",
        "schema_version",
        "path",
        "format",
        "status",
    }


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ArtifactDeclaration.model_validate(make(formt="tsv"))
    assert invalid_fields(exc_info.value) == {"formt"}


@pytest.mark.parametrize("id_", ["sample_metrics", "qc-1", "a"])
def test_accepts_valid_ids(id_: str) -> None:
    assert ArtifactDeclaration.model_validate(make(id=id_)).id == id_


@pytest.mark.parametrize(
    "id_", ["Sample", "1sample", "sample metrics", "", "-sample", "sample."]
)
def test_rejects_invalid_ids(id_: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ArtifactDeclaration.model_validate(make(id=id_))
    assert "id" in invalid_fields(exc_info.value)


@pytest.mark.parametrize(
    "type_",
    [
        "org.example.sample_metrics",
        "io.github.projectx.variant_summary",
        "org.example-v2.sub_type",
        "a.b.c.d",
    ],
)
def test_accepts_namespaced_types(type_: str) -> None:
    assert ArtifactDeclaration.model_validate(make(type=type_)).type == type_


@pytest.mark.parametrize(
    "type_", ["summary", "org.Example", ".org", "org.", "org..x", "org example", ""]
)
def test_rejects_unnamespaced_types(type_: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ArtifactDeclaration.model_validate(make(type=type_))
    assert "type" in invalid_fields(exc_info.value)


@pytest.mark.parametrize("version", ["1.0", "2", "2026-10"])
def test_accepts_any_nonempty_schema_version(version: str) -> None:
    declaration = ArtifactDeclaration.model_validate(make(schema_version=version))
    assert declaration.schema_version == version


@pytest.mark.parametrize("version", ["", 1, None, ["1.0"]])
def test_rejects_invalid_schema_versions(version: object) -> None:
    with pytest.raises(ValidationError):
        ArtifactDeclaration.model_validate(make(schema_version=version))


@pytest.mark.parametrize(
    "path",
    ["report_data/x.tsv", "x.tsv", "a/b/c.json", "./x.tsv", "a//b.tsv"],
)
def test_accepts_relative_posix_paths(path: str) -> None:
    assert ArtifactDeclaration.model_validate(make(path=path)).path == path


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "../secrets.json",
        "..",
        "a/../b.json",
        "report_data\\x.tsv",
        "C:\\data\\x.tsv",
    ],
)
def test_rejects_unsafe_or_absolute_paths(path: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ArtifactDeclaration.model_validate(make(path=path))
    assert "path" in invalid_fields(exc_info.value)


def test_traversal_error_names_the_offense() -> None:
    with pytest.raises(ValidationError, match=r"'\.\.' segments"):
        ArtifactDeclaration.model_validate(make(path="../secrets.json"))


def test_rejects_unsupported_format() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ArtifactDeclaration.model_validate(make(format="csv"))
    assert "format" in invalid_fields(exc_info.value)


@pytest.mark.parametrize(
    ("raw", "status"),
    [
        ("complete", ArtifactStatus.COMPLETE),
        ("partial", ArtifactStatus.PARTIAL),
        ("failed", ArtifactStatus.FAILED),
        ("missing", ArtifactStatus.MISSING),
    ],
)
def test_status_parses_from_string(raw: str, status: ArtifactStatus) -> None:
    assert ArtifactDeclaration.model_validate(make(status=raw)).status is status


@pytest.mark.parametrize("raw", ["COMPLETE", "Complete", "pending", "done", ""])
def test_rejects_unknown_status(raw: str) -> None:
    with pytest.raises(ValidationError):
        ArtifactDeclaration.model_validate(make(status=raw))


def test_accepts_lowercase_hex_sha256() -> None:
    declaration = ArtifactDeclaration.model_validate(make(sha256=VALID_SHA256))
    assert declaration.sha256 == VALID_SHA256


@pytest.mark.parametrize("digest", ["A" * 64, "a" * 63, "a" * 65, "z" * 64, 123])
def test_rejects_invalid_sha256(digest: object) -> None:
    with pytest.raises(ValidationError):
        ArtifactDeclaration.model_validate(make(sha256=digest))


def test_model_dump_round_trips() -> None:
    original = ArtifactDeclaration.model_validate(make(sha256=VALID_SHA256))
    rebuilt = ArtifactDeclaration.model_validate(original.model_dump())
    assert rebuilt == original


def test_frozen_instance_rejects_mutation() -> None:
    declaration = ArtifactDeclaration.model_validate(make())
    assert_frozen(declaration, "id", "renamed")


def test_hashable_and_equal_by_value() -> None:
    first = ArtifactDeclaration.model_validate(make())
    second = ArtifactDeclaration.model_validate(make())
    assert first == second
    assert hash(first) == hash(second)
    assert len({first, second}) == 1
