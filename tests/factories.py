"""Payload factories shared by workflow-coda tests.

Factories return raw dictionaries, not pydantic models, so tests can
freely omit keys, inject invalid values, and exercise every failure mode
through ``model_validate``.
"""

VALID_SHA256 = "a" * 64
"""A syntactically valid lowercase hexadecimal SHA-256 digest."""


def make_artifact_payload(**overrides: object) -> dict[str, object]:
    """Return a fresh, valid artifact declaration payload."""
    payload: dict[str, object] = {
        "id": "sample_metrics",
        "type": "org.example.sample_metrics",
        "schema_version": "1.0",
        "path": "report_data/sample_metrics.tsv",
        "format": "tsv",
        "status": "complete",
    }
    payload.update(overrides)
    return payload


def make_producer_payload(**overrides: object) -> dict[str, object]:
    """Return a fresh, valid producer metadata payload."""
    payload: dict[str, object] = {"name": "Example workflow", "version": "2.4.0"}
    payload.update(overrides)
    return payload


def make_manifest_payload(**overrides: object) -> dict[str, object]:
    """Return a fresh, valid report manifest payload."""
    payload: dict[str, object] = {
        "schema_version": "0.1.0",
        "producer": make_producer_payload(),
        "artifacts": [make_artifact_payload()],
    }
    payload.update(overrides)
    return payload


def omit(payload: dict[str, object], *keys: str) -> dict[str, object]:
    """Return a copy of *payload* without *keys*."""
    return {key: value for key, value in payload.items() if key not in keys}
