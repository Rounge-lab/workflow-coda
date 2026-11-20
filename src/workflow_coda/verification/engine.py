"""The verification engine: bytes in, record and digest out.

One unit sits at the center of every verification —
:func:`verify_artifact_file` — with its helpers around it:
the availability teaching, the honest missing-file fact, the
failed record's shape, and the format's own dispatch spelling.

The engine enacts the caller-owns-IO law of the verifier
contract: the bytes are read exactly once, and the same bytes the
verifier checks are the bytes the sha256 digests.  Criteria ride
verbatim — the owning verifier's grammar.  Routing a failure —
refuse or record — is the drivers' law, never the engine's.
"""

import hashlib
from collections.abc import Mapping
from pathlib import Path

from ..errors import ComponentUnavailableError, VerificationError
from ..manifest import ArtifactFormat, JsonValue, NamespacedArtifactFormat
from ..plugins import ArtifactVerifier


def _require_verifier(
    verifiers: Mapping[str, ArtifactVerifier], fmt_key: str
) -> ArtifactVerifier:
    """The verifier *fmt_key* dispatches to, or the availability
    teaching — :meth:`PluginRegistry.require_component`'s law at the
    verifier boundary: name what was asked for, name what is
    available."""
    verifier = verifiers.get(fmt_key)
    if verifier is None:
        available = ", ".join(sorted(verifiers)) or "none"
        raise ComponentUnavailableError(
            f"no loaded plugin offers a verifier for format {fmt_key!r} "
            f"(available: {available})"
        )
    return verifier


def _read_artifact_bytes(file: Path) -> bytes:
    """The artifact's bytes, read exactly once.

    A missing file is the run's honest fact, taught as a
    verification failure: under ``--on-failure write`` it is the
    artifact's failed record, under ``fail`` the run's refusal.
    Flags mode never reaches this branch — its FILE positional is
    existence-checked at the invocation (exit 2); the asymmetry is
    the design.
    """
    if not file.is_file():
        raise VerificationError(
            f"the artifact file '{file}' does not exist — the pipeline "
            "did not produce it; check the spec's file path and the "
            "pipeline's outputs"
        )
    try:
        return file.read_bytes()
    except OSError as e:
        raise VerificationError(
            f"could not read the artifact file '{file}': {e.strerror or e}"
        ) from e


def _failure_record(fmt_key: str, message: str) -> dict[str, JsonValue]:
    """The failure record: the success record's honest mirror — the
    format verification was attempted under, the failed status, and
    the teaching that failed it, riding the manifest verbatim."""
    return {"format": fmt_key, "status": "failed", "message": message}


def verify_artifact_file(
    verifiers: Mapping[str, ArtifactVerifier],
    file: Path,
    fmt: ArtifactFormat | NamespacedArtifactFormat,
    criteria: Mapping[str, JsonValue] | None,
) -> tuple[dict[str, JsonValue], str]:
    """Verify one artifact file: bytes in, record and digest out.

    The dispatch key is the format's own spelling — the enum's
    value, the namespaced name as written.  A format no verifier
    claims is the availability teaching, never a recorded failure:
    the artifact's bytes may be fine, what is missing is a service,
    and a service mismatch is not the artifact's status.

    The bytes are read exactly once, and the same bytes the
    verifier checks are the bytes the sha256 digests — the
    caller-owns-IO law of the verifier contract, enacted here.
    Criteria ride verbatim, typed from a spec or comma-strings from
    flags: the format's verifier owns the grammar.  Raises
    :class:`~workflow_coda.errors.VerificationError` with the
    teaching when the artifact fails its verification; routing that
    failure — refuse or record — is the mode drivers' law.
    """
    fmt_key = _format_key(fmt)
    verifier = _require_verifier(verifiers, fmt_key)
    data = _read_artifact_bytes(file)
    record = verifier.verify(data, criteria if criteria is not None else {})
    return record, hashlib.sha256(data).hexdigest()


def _format_key(fmt: ArtifactFormat | NamespacedArtifactFormat) -> str:
    """The format's own spelling — the enum's value, the namespaced
    name as written: the key dispatch keys on and records carry."""
    return fmt.value if isinstance(fmt, ArtifactFormat) else fmt
