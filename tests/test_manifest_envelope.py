"""Tests for the report manifest envelope model."""

import re

import pytest
from factories import (
    make_artifact_payload,
    make_manifest_payload,
    make_producer_payload,
    omit,
)
from helpers import assert_frozen, invalid_fields
from pydantic import ValidationError

from workflow_coda.manifest import (
    MANIFEST_SCHEMA_VERSION,
    ProducerMetadata,
    ReportManifest,
)

# ---------------------------------------------------------------------------
# ProducerMetadata
# ---------------------------------------------------------------------------


def test_valid_producer_parses() -> None:
    producer = ProducerMetadata.model_validate(make_producer_payload())
    assert producer.name == "Example workflow"
    assert producer.version == "2.4.0"
    assert producer.run_id is None


def test_producer_accepts_run_id() -> None:
    producer = ProducerMetadata.model_validate(
        make_producer_payload(run_id="2026-10-01T103012Z")
    )
    assert producer.run_id == "2026-10-01T103012Z"


def test_producer_accepts_explicit_null_run_id() -> None:
    producer = ProducerMetadata.model_validate(make_producer_payload(run_id=None))
    assert producer.run_id is None


@pytest.mark.parametrize("field", ["name", "version"])
def test_producer_required_fields(field: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProducerMetadata.model_validate(omit(make_producer_payload(), field))
    assert invalid_fields(exc_info.value) == {field}


def test_producer_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProducerMetadata.model_validate(make_producer_payload(contact="someone"))
    assert invalid_fields(exc_info.value) == {"contact"}


def test_producer_rejects_empty_name() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProducerMetadata.model_validate(make_producer_payload(name=""))
    assert "name" in invalid_fields(exc_info.value)


@pytest.mark.parametrize("value", [123, None, ["workflow"]])
def test_producer_rejects_non_string_fields(value: object) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ProducerMetadata.model_validate(make_producer_payload(name=value))
    assert "name" in invalid_fields(exc_info.value)


def test_producer_is_frozen() -> None:
    producer = ProducerMetadata.model_validate(make_producer_payload())
    assert_frozen(producer, "name", "renamed")


# ---------------------------------------------------------------------------
# ReportManifest
# ---------------------------------------------------------------------------


def test_valid_manifest_parses() -> None:
    manifest = ReportManifest.model_validate(make_manifest_payload())
    assert manifest.schema_version == MANIFEST_SCHEMA_VERSION
    assert manifest.producer.name == "Example workflow"
    assert isinstance(manifest.artifacts, tuple)
    assert len(manifest.artifacts) == 1


def test_manifest_requires_all_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ReportManifest.model_validate({})
    assert invalid_fields(exc_info.value) == {"schema_version", "producer", "artifacts"}


def test_manifest_forbids_extra_fields() -> None:
    # Run provenance lives in the reserved provenance artifact, not in the
    # envelope (a deliberate design decision); envelope keys stay closed.
    with pytest.raises(ValidationError) as exc_info:
        ReportManifest.model_validate(
            make_manifest_payload(pipeline={"name": "VirMake"})
        )
    assert invalid_fields(exc_info.value) == {"pipeline"}


def test_empty_artifacts_must_be_explicit() -> None:
    manifest = ReportManifest.model_validate(make_manifest_payload(artifacts=[]))
    assert manifest.artifacts == ()


def test_missing_artifacts_key_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ReportManifest.model_validate(omit(make_manifest_payload(), "artifacts"))
    assert invalid_fields(exc_info.value) == {"artifacts"}


@pytest.mark.parametrize("value", [5, "metrics", {}])
def test_artifacts_must_be_a_list(value: object) -> None:
    with pytest.raises(ValidationError):
        ReportManifest.model_validate(make_manifest_payload(artifacts=value))


@pytest.mark.parametrize(
    "version",
    [
        "0.1.0",  # the pre-widening envelope, superseded by the clean break
        "1.0",
        "0.1",
        "0.1.00",
        "0.2.1",
        "0.2.0-beta",
        "v0.2.0",
        "",
        " 0.2.0",
    ],
)
def test_version_gate_is_exact(version: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ReportManifest.model_validate(make_manifest_payload(schema_version=version))
    assert "schema_version" in invalid_fields(exc_info.value)


@pytest.mark.parametrize("version", [0.1, 1, True, None])
def test_version_must_be_a_string(version: object) -> None:
    with pytest.raises(ValidationError):
        ReportManifest.model_validate(make_manifest_payload(schema_version=version))


# ---------------------------------------------------------------------------
# Artifact uniqueness
# ---------------------------------------------------------------------------


def test_rejects_duplicate_ids() -> None:
    payload = make_manifest_payload(
        artifacts=[
            make_artifact_payload(),
            make_artifact_payload(type="org.example.other", path="report_data/o.tsv"),
        ]
    )
    message = "duplicate artifact ids in manifest: 'sample_metrics' x2"
    with pytest.raises(ValidationError, match=re.escape(message)):
        ReportManifest.model_validate(payload)


def test_rejects_duplicate_types() -> None:
    payload = make_manifest_payload(
        artifacts=[
            make_artifact_payload(),
            make_artifact_payload(id="other", path="report_data/o.tsv"),
        ]
    )
    message = "duplicate artifact types in manifest: 'org.example.sample_metrics' x2"
    with pytest.raises(ValidationError, match=re.escape(message)):
        ReportManifest.model_validate(payload)


def test_duplicate_report_is_aggregated_sorted_and_counted() -> None:
    payload = make_manifest_payload(
        artifacts=[
            make_artifact_payload(id="b", type="org.x.t1"),
            make_artifact_payload(id="b", type="org.x.t2", path="report_data/t2.tsv"),
            make_artifact_payload(id="b", type="org.x.t3", path="report_data/t3.tsv"),
            make_artifact_payload(id="a", type="org.x.t4", path="report_data/t4.tsv"),
            make_artifact_payload(id="a", type="org.x.t5", path="report_data/t5.tsv"),
        ]
    )
    message = "duplicate artifact ids in manifest: 'a' x2, 'b' x3"
    with pytest.raises(ValidationError, match=re.escape(message)):
        ReportManifest.model_validate(payload)


def test_duplicate_ids_and_types_are_reported_together() -> None:
    # Pins the merged-validator fix: pydantic stops a field's validator
    # chain at the first failure, so separate validators on ``artifacts``
    # would only ever report one of the two problems.
    payload = make_manifest_payload(
        artifacts=[
            make_artifact_payload(id="b", type="org.x.t1"),
            make_artifact_payload(id="b", type="org.x.t2", path="report_data/t2.tsv"),
            make_artifact_payload(id="a", type="org.x.t2", path="report_data/t3.tsv"),
        ]
    )
    message = (
        "duplicate artifact ids in manifest: 'b' x2; "
        "duplicate artifact types in manifest: 'org.x.t2' x2"
    )
    with pytest.raises(ValidationError, match=re.escape(message)):
        ReportManifest.model_validate(payload)


# ---------------------------------------------------------------------------
# Value semantics
# ---------------------------------------------------------------------------


def test_artifact_order_is_preserved() -> None:
    payload = make_manifest_payload(
        artifacts=[
            make_artifact_payload(id="z", type="org.x.z", path="report_data/z.tsv"),
            make_artifact_payload(id="a", type="org.x.a", path="report_data/a.tsv"),
        ]
    )
    manifest = ReportManifest.model_validate(payload)
    assert [artifact.id for artifact in manifest.artifacts] == ["z", "a"]


def test_manifest_is_hashable_and_equal_by_value() -> None:
    first = ReportManifest.model_validate(make_manifest_payload())
    second = ReportManifest.model_validate(make_manifest_payload())
    assert first == second
    assert hash(first) == hash(second)
    assert len({first, second}) == 1


def test_manifest_is_frozen() -> None:
    manifest = ReportManifest.model_validate(make_manifest_payload())
    assert_frozen(manifest, "schema_version", "9.9.9")


def test_nested_errors_carry_their_field_path() -> None:
    payload = make_manifest_payload(producer={"name": "", "version": "2.4.0"})
    with pytest.raises(ValidationError) as exc_info:
        ReportManifest.model_validate(payload)
    assert exc_info.value.errors()[0]["loc"] == ("producer", "name")


def test_verification_round_trips_as_opaque_transport() -> None:
    """0.3.0's one addition: the optional verification record, opaque
    transport — a declared record round-trips exactly as written, and
    an absent record stays absent."""
    baseline = ReportManifest.model_validate(make_manifest_payload())
    assert baseline.artifacts[0].verification is None

    record: dict[str, object] = {
        "format": "json",
        "status": "ok",
        "keys_checked": ["depth", "rate"],
    }
    declared = make_manifest_payload(
        artifacts=[make_artifact_payload(verification=record)]
    )
    manifest = ReportManifest.model_validate(declared)
    assert manifest.artifacts[0].verification == record

    again = ReportManifest.model_validate_json(manifest.model_dump_json())
    assert again.artifacts[0].verification == record


def test_verification_must_be_a_json_object() -> None:
    """The record is transport, but transport has shape: a non-object
    verification value fails envelope validation, named by field."""
    declared = make_manifest_payload(
        artifacts=[make_artifact_payload(verification="checked by hand")]
    )
    with pytest.raises(ValidationError) as excinfo:
        ReportManifest.model_validate(declared)
    assert "verification" in str(excinfo.value)
