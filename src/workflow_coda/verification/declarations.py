"""The manifest side of verification: build, place, write.

Every unit that touches the manifest's own shape lives here: the
atomic writer, the path arithmetic, the two declarations a
verification can produce — COMPLETE with the verifier's record and
the digest of exactly the checked bytes, FAILED with the teaching
and no checksum — the create-or-load door with its producer
requirement, the match-or-omit agreement check, and the placement
law: append, or update in place, position preserved, both
conflict teachings.

The engine verifies bytes; this module shapes the result into a
declaration the manifest can carry.  The frozen-model law runs
through it — placement is a copy with a new artifacts tuple,
never a mutation.
"""

import os
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter, ValidationError

from ..errors import ManifestError, VerifyError
from ..manifest import (
    MANIFEST_SCHEMA_VERSION,
    ArtifactDeclaration,
    ArtifactFormat,
    ArtifactId,
    ArtifactSchemaVersion,
    ArtifactStatus,
    ArtifactType,
    JsonValue,
    NamespacedArtifactFormat,
    NonEmptyStr,
    ProducerMetadata,
    ReportManifest,
    load_manifest,
)
from .engine import _failure_record, _format_key

_PRODUCER_CLAIM_CHECK: TypeAdapter[NonEmptyStr] = TypeAdapter(NonEmptyStr)


def _validate_producer_claims(
    name: str | None,
    version: str | None,
    run_id: str | None,
) -> None:
    """Validate supplied claims without requiring a complete identity.

    None is omission. Reuse the manifest's strict non-empty string
    grammar; no trimming or whitespace normalization is introduced.
    """
    problems: list[str] = []
    for flag, value in (
        ("--producer-name", name),
        ("--producer-version", version),
        ("--run-id", run_id),
    ):
        if value is None:
            continue
        try:
            _PRODUCER_CLAIM_CHECK.validate_python(value)
        except ValidationError:
            problems.append(f"  - {flag} must be a non-empty string")
    if problems:
        raise VerifyError("invalid producer/run declaration:\n" + "\n".join(problems))


def write_manifest_atomically(manifest: ReportManifest, path: Path) -> None:
    """Write *manifest* to *path* atomically, byte-disciplined.

    The text is serialized from the model — pydantic's own JSON,
    indent 2, field order preserved — plus exactly one trailing
    newline and no BOM: the manifest
    :func:`~workflow_coda.manifest.load_manifest` reads back is the
    manifest the writer meant.

    The write is atomic: the text lands in a hidden temporary file
    in the destination's own directory, then replaces the
    destination via :func:`os.replace` — a crash can leave a
    ``.manifest.json.….tmp`` behind, never a torn manifest.  An
    :class:`OSError` propagates for the caller to teach; the
    temporary file is unlinked first.
    """
    text = manifest.model_dump_json(indent=2) + "\n"
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temp, path)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def _manifest_relative_path(file: Path, manifest: Path) -> str:
    """The artifact's path as the manifest records it: relative to
    the manifest's own directory, POSIX-spelled, inside the tree.

    The declaration's path law (forward slashes, no ``..``
    segments) follows from the arithmetic.  What the arithmetic
    cannot do is record an artifact living outside the manifest's
    directory — the store resolves paths against the manifest's
    location, so such a path would declare what the report cannot
    read — and that failure is taught here and never recorded
    under write: it is the invocation's geometry, not the
    artifact's fact, the availability precedent.

    Drivers also call this arithmetic during preflight, before artifact
    verification. Declaration builders retain the check for direct
    callers. Containment is lexical; this helper does not resolve
    symlinks or require the artifact to exist.
    """
    try:
        relative = os.path.relpath(file, start=manifest.parent)
    except ValueError as e:
        raise ManifestError(
            f"the artifact '{file}' and the manifest '{manifest}' live "
            "on different drives — a manifest declares paths relative "
            "to its own location, so it cannot record this artifact"
        ) from e
    posix = relative.replace(os.sep, "/")
    if posix == ".." or posix.startswith("../"):
        raise ManifestError(
            f"the manifest '{manifest}' records artifact paths relative "
            f"to its own location, but '{file}' lives outside its "
            f"directory — write the manifest next to the pipeline's "
            "outputs, or verify a copy of the artifact from inside "
            "that directory"
        )
    return posix


def build_verified_declaration(
    *,
    id: ArtifactId,
    type: ArtifactType,
    fmt: ArtifactFormat | NamespacedArtifactFormat,
    schema_version: ArtifactSchemaVersion,
    file: Path,
    manifest: Path,
    record: dict[str, JsonValue],
    sha256: str,
    module_id: NonEmptyStr | None = None,
) -> ArtifactDeclaration:
    """The successful verification's declaration: COMPLETE, the
    verifier's record riding verbatim, the digest of exactly the
    bytes that were verified — the caller-owns-IO law's last step:
    the checksum the manifest vouches with is the checksum of the
    bytes the verifier checked."""
    return ArtifactDeclaration(
        id=id,
        type=type,
        schema_version=schema_version,
        path=_manifest_relative_path(file, manifest),
        format=fmt,
        status=ArtifactStatus.COMPLETE,
        sha256=sha256,
        verification=record,
        module_id=module_id,
    )


def build_failed_declaration(
    *,
    id: ArtifactId,
    type: ArtifactType,
    fmt: ArtifactFormat | NamespacedArtifactFormat,
    schema_version: ArtifactSchemaVersion,
    file: Path,
    manifest: Path,
    message: str,
    module_id: NonEmptyStr | None = None,
) -> ArtifactDeclaration:
    """The failed verification's declaration: FAILED, the failure
    record — the format's own spelling, the failed status, the
    teaching that failed it — and no checksum.

    No checksum is a ruling, not an omission: a failed artifact is
    recorded, not vouched for, and the manifest's sha256 is a
    promise — the record is the run's honest account, and it does
    not promise bytes the verification refused.  The path still
    resolves by arithmetic alone, so a missing output's absence is
    recordable: that is exactly what ``--on-failure write`` is for.
    """
    return ArtifactDeclaration(
        id=id,
        type=type,
        schema_version=schema_version,
        path=_manifest_relative_path(file, manifest),
        format=fmt,
        status=ArtifactStatus.FAILED,
        verification=_failure_record(_format_key(fmt), message),
        module_id=module_id,
    )


def load_or_init_manifest(
    path: Path,
    *,
    producer_name: str | None,
    producer_version: str | None,
    run_id: str | None,
) -> tuple[ReportManifest, bool]:
    """The manifest at *path*, loaded or initialized: (manifest, created).

    A missing manifest is the create path: the invocation's producer
    identity initializes the envelope, and the file itself is written
    once, atomically, after every declaration has landed — a run
    that refuses midway never leaves a torn manifest behind.  An
    existing manifest is loaded through
    :func:`~workflow_coda.manifest.load_manifest`, and every
    envelope-side teaching is the loader's own, unchanged: corrupt
    JSON, a stale schema version with regeneration named, an
    unreadable file.

    Creating requires the producer identity: an append may omit the
    flags — omission is agreement with the record — but a create
    has no record to agree with, so the missing identity is taught,
    not guessed.  Flags mode reaches this unit only after its
    identity check; the mode drivers own that order.
    """
    _validate_producer_claims(producer_name, producer_version, run_id)
    if not path.exists():
        if producer_name is None or producer_version is None:
            raise VerifyError(
                f"creating {path} requires a producer identity — supply "
                "both name and version through --producer-name and "
                "--producer-version, the spec's producer mapping, or "
                "a combination of both (one manifest identifies the "
                "pipeline that produced its artifacts)"
            )
        return (
            ReportManifest(
                schema_version=MANIFEST_SCHEMA_VERSION,
                producer=ProducerMetadata(
                    name=producer_name,
                    version=producer_version,
                    run_id=run_id,
                ),
                artifacts=(),
            ),
            True,
        )
    return load_manifest(path), False


def check_producer_agreement(
    manifest: ReportManifest,
    name: str | None,
    version: str | None,
    run_id: str | None,
) -> None:
    """Match-or-omit for the producer identity on an existing manifest.

    ``None`` means the invocation omitted the value, and omission is
    agreement: the manifest's recorded producer stands, exactly as
    an append needs no producer flags at all.  A declared value must
    match the record — one manifest, one producer, one run — and a
    mismatch is taught with both sides named: the manifest's record
    and this verification's claim.
    """
    _validate_producer_claims(name, version, run_id)
    if name is not None and name != manifest.producer.name:
        raise ManifestError(
            f"one manifest, one producer: the manifest already records "
            f"producer {manifest.producer.name!r} "
            f"{manifest.producer.version!r}, but this verification "
            f"declares {name!r} — rebuild the manifest, or verify with "
            "the recorded producer"
        )
    if version is not None and version != manifest.producer.version:
        raise ManifestError(
            f"one manifest, one producer: the manifest already records "
            f"producer {manifest.producer.name!r} "
            f"{manifest.producer.version!r}, but this verification "
            f"declares version {version!r} — rebuild the manifest, or "
            "verify with the recorded producer"
        )
    if run_id is not None and run_id != manifest.producer.run_id:
        raise ManifestError(
            f"one manifest, one run: the manifest already records run "
            f"{manifest.producer.run_id!r}, but this verification "
            f"declares {run_id!r} — one manifest describes one run; "
            "rebuild the manifest for a new run"
        )


def apply_artifact_declaration(
    manifest: ReportManifest, declaration: ArtifactDeclaration
) -> tuple[ReportManifest, Literal["appended", "updated"]]:
    """Place one verified declaration: append, or update in place.

    Update keeps the declaration's position in the list — a rerun
    replaces its own artifact; it does not reorder the report.  Two
    authoring mistakes refuse the run: reusing a resident id with a
    different type, and introducing a new id for a type another
    artifact already carries — the report framework resolves
    artifacts by type, and either mistake leaves that resolution
    ambiguous.  The models are frozen, so placement is a copy with
    a new artifacts tuple, never a mutation.

    Module attribution is preserved when omitted on a rerun. A supplied
    module may annotate an unattributed artifact, but cannot silently
    replace an existing module attribution.
    """
    resident = next((a for a in manifest.artifacts if a.id == declaration.id), None)
    if resident is not None:
        if resident.type != declaration.type:
            raise ManifestError(
                f"the id {declaration.id!r} is already declared in the "
                f"manifest as type {resident.type!r}, but this "
                f"verification declares it as {declaration.type!r} — an "
                "update repeats the same type; use a new id for a new "
                "artifact type"
            )
        if (
            declaration.module_id is not None
            and resident.module_id is not None
            and declaration.module_id != resident.module_id
        ):
            raise ManifestError(
                f"artifact {declaration.id!r} already records module "
                f"{resident.module_id!r}, but this verification declares "
                f"{declaration.module_id!r} — a rerun must preserve module "
                "attribution; rebuild the manifest to reassign ownership"
            )
        if declaration.module_id is None and resident.module_id is not None:
            declaration = declaration.model_copy(
                update={"module_id": resident.module_id}
            )
        artifacts = tuple(
            declaration if a.id == declaration.id else a for a in manifest.artifacts
        )
        return manifest.model_copy(update={"artifacts": artifacts}), "updated"
    collision = next(
        (a for a in manifest.artifacts if a.type == declaration.type), None
    )
    if collision is not None:
        raise ManifestError(
            f"the report framework resolves artifacts by type, and the "
            f"manifest already declares type {declaration.type!r} as "
            f"artifact {collision.id!r} — a second id for one type is "
            f"ambiguous; give {declaration.id!r} a different type"
        )
    return (
        manifest.model_copy(update={"artifacts": manifest.artifacts + (declaration,)}),
        "appended",
    )
