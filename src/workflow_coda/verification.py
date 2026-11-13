"""The verify command's library: spec in, manifest out.

``workflow-coda verify`` is the pipeline hand's door: it turns real
output files into a verified report manifest — the stable interface
the report framework reads.  This module is the library behind the
subcommand; the CLI is a thin edge that validates its own invocation
and hands everything to code that already knows how to fail with
teaching messages.

The spec is the hand-authored half of that contract: a small YAML
file declaring the run's producer and one block per output file —
identity, format, content schema version, and the criteria the
format's verifier reads.  Its loader shares the layout loader's
YAML machinery — which that module advertises as the framework's
shared machinery for human-authored files — and inherits the
hand-authored-file law: duplicate keys rejected with key and line,
YAML's boolean traps explained with the quoting rule, every failure
raised as :class:`~workflow_coda.errors.SpecError` whose ``str`` is
the teaching.  The pins rule the design record's exception-
attribute shape out: the CLI prints the exception and exits 1, the
shape it already owns.
"""

import hashlib
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from .errors import (
    ComponentUnavailableError,
    ManifestError,
    SpecError,
    VerificationError,
    VerifyError,
)
from .layout_loader import (
    UniqueKeySafeLoader,
    _describe_violation,
    _DuplicateKeyError,
)
from .manifest import (
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
from .plugins import ArtifactVerifier
from .registry import PluginRegistry


class SpecProducer(BaseModel):
    """The spec's producer block: who produced the artifacts.

    The manifest's own ``name`` and ``version`` verbatim — the
    identity every manifest agrees on: one manifest, one producer.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: NonEmptyStr
    """The producing pipeline's human-readable name."""

    version: NonEmptyStr
    """The producing pipeline's version, e.g. a release number."""


class SpecArtifact(BaseModel):
    """One artifact block in the spec: what to verify and how.

    The pipeline author's declaration of intent: the file to read,
    the identity the manifest will record, and the criteria the
    format's verifier reads.  ``criteria`` is transport — the
    verifier owns its grammar and teaches on bad values at
    verification time.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    file: NonEmptyStr
    """The artifact file, relative to the spec's own directory."""

    id: ArtifactId
    """The artifact's unique id within the manifest-to-be."""

    type: ArtifactType
    """The namespaced artifact type, e.g. ``org.example.samples``."""

    format: ArtifactFormat | NamespacedArtifactFormat
    """The artifact's format: a core value or a namespaced plugin
    convention — the name the verifier dispatch keys on."""

    schema_version: ArtifactSchemaVersion
    """The artifact's content schema version, e.g. ``"1.0.0"``."""

    criteria: dict[str, JsonValue] | None = None
    """The verifier's criteria: keys and values the owning format's
    verifier reads and validates.  Absent means no criteria."""


class VerifySpec(BaseModel):
    """The whole verification spec: producer and artifact blocks.

    Constructed by :func:`load_verify_spec` from the spec file's
    parsed content; the structural teachings — a producer block, at
    least one artifact — fire in the loader, before validation,
    where the file's whole shape is in hand and the teaching is a
    full sentence.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    producer: SpecProducer
    """The run's producer — one manifest, one producer."""

    artifacts: tuple[SpecArtifact, ...]
    """The blocks to verify, in declaration order."""


def load_verify_spec(path: Path) -> VerifySpec:
    """Load and validate a verification spec file.

    Raises :class:`~workflow_coda.errors.SpecError` — with the file
    path for context — when the file is unreadable, not valid
    UTF-8, not valid YAML, not a mapping, or violating the spec
    contract: a missing producer block, no artifact blocks, or a
    shape violation taught field by field.  The teaching shapes are
    the layout loader's, whose machinery this loader shares.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise SpecError(
            f"could not read the spec file {path}: {e.strerror or e}"
        ) from e
    except UnicodeDecodeError as e:
        raise SpecError(f"the spec file {path} is not valid UTF-8: {e}") from e
    try:
        parsed = yaml.load(text, Loader=UniqueKeySafeLoader)
    except _DuplicateKeyError as e:
        raise SpecError(
            f"{path}: duplicate key {e.key!r} on line {e.line} — YAML "
            "normally keeps only the last occurrence without an error; "
            "merge the two blocks into one"
        ) from e
    except yaml.YAMLError as e:
        detail = " ".join(str(e).split())
        raise SpecError(f"{path}: not valid YAML: {detail}") from e
    if not isinstance(parsed, dict):
        if parsed is None:
            found = "nothing (the file is empty)"
        elif isinstance(parsed, list):
            found = "a list — did the first artifact line lose its 'file:' key?"
        else:
            found = f"a single {type(parsed).__name__} value"
        raise SpecError(
            f"{path}: the spec file must be a mapping (producer:, "
            f"artifacts:), but it contains {found}"
        )
    if "producer" not in parsed:
        raise SpecError(
            f"{path}: the spec requires a producer block — name and "
            "version, the manifest's own fields verbatim, e.g.\n"
            'producer:\n  name: my-pipeline\n  version: "1.0"'
        )
    if not parsed.get("artifacts"):
        raise SpecError(
            f"{path}: the spec must declare at least one artifact — a "
            "spec that verifies nothing is an authoring mistake"
        )
    try:
        return VerifySpec.model_validate(parsed)
    except ValidationError as e:
        lines = "\n".join(
            f"  - {_describe_violation(parsed, error)}" for error in e.errors()
        )
        raise SpecError(f"{path} is not a valid verification spec:\n{lines}") from e


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
    if not path.exists():
        if producer_name is None or producer_version is None:
            raise VerifyError(
                f"creating {path} requires a producer identity — pass "
                "--producer-name and --producer-version (one manifest "
                "identifies the pipeline that produced its artifacts)"
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


@dataclass(frozen=True, slots=True)
class VerifyOutcome:
    """A verify run's result: exit code, stdout summary, warnings.

    The drivers return; they never print.  The CLI is the only
    printer: *out* to stdout, each warning to stderr, then
    *exit_code* as the process exit.  The exit is 0 under
    ``--on-failure write`` even when failures were recorded — the
    recording is the command's success — and the warnings carry
    each recorded failure's teaching, one line apiece.
    """

    exit_code: int
    """The process exit code the CLI returns."""

    out: str
    """The stdout summary, newline-terminated."""

    warnings: tuple[str, ...] = ()
    """One line per recorded failure, printed to stderr."""


def parse_criteria(pairs: Sequence[str]) -> dict[str, JsonValue]:
    """Flag criteria pairs (``--criteria KEY=VALUE``) into the
    verifier's criteria mapping.

    Values ride verbatim as one string each — the string transport
    the verifiers accept: ``--criteria keys=depth,rate`` is the
    single value ``"depth,rate"``, and the format's verifier owns
    the comma grammar.  Two mistakes are taught here, at the
    invocation's edge: a pair without ``=``, and one key passed
    twice — silent last-wins is the trap the framework refuses
    everywhere.
    """
    criteria: dict[str, JsonValue] = {}
    for pair in pairs:
        if "=" not in pair:
            raise VerifyError(
                f"criterion {pair!r} must be KEY=VALUE — pass one "
                "criterion per --criteria flag, e.g. --criteria "
                "keys=depth"
            )
        key, _, value = pair.partition("=")
        key = key.strip()
        if not key:
            raise VerifyError(
                f"criterion {pair!r} must be KEY=VALUE — the key is "
                "empty; pass one criterion per --criteria flag, e.g. "
                "--criteria keys=depth"
            )
        if key in criteria:
            raise VerifyError(
                f"criterion {key!r} is passed twice — pass each key "
                "once; a list-shaped value is one comma-separated "
                "string (e.g. --criteria keys=depth,rate)"
            )
        criteria[key] = value
    return criteria


def _verifier_index() -> dict[str, ArtifactVerifier]:
    """The dispatch index for one invocation: every verifier usable
    when writing the manifest schema version — the framework's trio
    unconditionally, plus the claims of the plugins that understand
    the version, keyed by format spelling."""
    registry = PluginRegistry.load()
    return {
        verifier.format: verifier
        for verifier in registry.verifiers_supporting(MANIFEST_SCHEMA_VERSION)
    }


def run_flags_verify(
    *,
    file: Path,
    manifest_path: Path,
    id: str | None,
    type: str | None,
    fmt: str | None,
    schema_version: str | None,
    producer_name: str | None,
    producer_version: str | None,
    run_id: str | None,
    criteria_pairs: Sequence[str],
    on_failure: Literal["fail", "write"],
) -> VerifyOutcome:
    """Flags mode: verify one artifact, place its declaration, write.

    One invocation, one artifact: the FILE positional's bytes are
    verified under the declared identity, the declaration lands in
    the manifest — created, appended, or updated in place — and the
    manifest is written once, atomically, after the placement.

    The identity check fires first, before the manifest is touched:
    a spec file declares id, type, format, and schema_version per
    artifact, but flags mode has no spec, so the four flags are the
    declaration's identity — and their absence is the invocation's
    mistake, taught before the create path's producer requirement
    could claim it.

    A verification failure is the toggle's business: under ``fail``
    it aborts the run with the teaching and nothing is written;
    under ``write`` it is recorded — the failed declaration rides
    the manifest, the teaching rides stderr as a warning, and the
    exit is 0.  Every other failure — an artifact outside the
    manifest's tree, an unavailable verifier, a manifest conflict —
    aborts regardless of the toggle: those are the invocation's or
    the environment's facts, not the artifact's.
    """
    if id is None or type is None or fmt is None or schema_version is None:
        raise VerifyError(
            "flags mode requires the artifact's identity — pass --id, "
            "--type, --format, and --schema-version; a spec file declares "
            "these per artifact, but flags mode has no spec"
        )
    criteria = parse_criteria(criteria_pairs)
    try:
        fmt_value: ArtifactFormat | NamespacedArtifactFormat = ArtifactFormat(fmt)
    except ValueError:
        fmt_value = fmt
    verifiers = _verifier_index()
    _require_verifier(verifiers, _format_key(fmt_value))
    manifest, created = load_or_init_manifest(
        manifest_path,
        producer_name=producer_name,
        producer_version=producer_version,
        run_id=run_id,
    )
    check_producer_agreement(manifest, producer_name, producer_version, run_id)
    run_clause = (
        f", run {manifest.producer.run_id}"
        if manifest.producer.run_id is not None
        else ""
    )
    created_prefix = (
        f"created {manifest_path} (producer {manifest.producer.name} "
        f"{manifest.producer.version}{run_clause})"
    )
    try:
        record, sha256 = verify_artifact_file(verifiers, file, fmt_value, criteria)
    except VerificationError as e:
        if on_failure == "fail":
            raise
        declaration = build_failed_declaration(
            id=id,
            type=type,
            fmt=fmt_value,
            schema_version=schema_version,
            file=file,
            manifest=manifest_path,
            message=str(e),
        )
        manifest, _ = apply_artifact_declaration(manifest, declaration)
        write_manifest_atomically(manifest, manifest_path)
        if created:
            out = f"{created_prefix} — recorded artifact {id} as failed\n"
        else:
            out = f"recorded artifact {id} as failed in {manifest_path}\n"
        return VerifyOutcome(
            exit_code=0,
            out=out,
            warnings=(f"artifact {id} recorded as failed: {e}",),
        )
    declaration = build_verified_declaration(
        id=id,
        type=type,
        fmt=fmt_value,
        schema_version=schema_version,
        file=file,
        manifest=manifest_path,
        record=record,
        sha256=sha256,
    )
    manifest, placement = apply_artifact_declaration(manifest, declaration)
    write_manifest_atomically(manifest, manifest_path)
    if created:
        out = f"{created_prefix} — verified and appended artifact {id}\n"
    elif placement == "appended":
        out = f"verified {file} — appended artifact {id} to {manifest_path}\n"
    else:
        out = f"verified {file} — updated artifact {id} in {manifest_path}\n"
    return VerifyOutcome(exit_code=0, out=out)


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


def run_spec_verify(
    *,
    spec_path: Path,
    manifest_path: Path,
    on_failure: Literal["fail", "write"],
) -> VerifyOutcome:
    """Spec mode: verify every artifact the spec declares, place,
    write once.

    The spec's producer initializes a create and must match an
    existing manifest — one manifest, one producer; the spec has no
    run id, so the run check rides flags mode alone.  Each artifact
    file resolves against the spec's own directory, and declarations
    land in declaration order, in memory — the manifest is written
    once, atomically, after every artifact has been placed.

    Under ``fail``, every artifact is attempted even after a
    failure, and the failures are raised together — one line each,
    the loader's collect-and-list law — with nothing written: the
    manifest file stays byte-identical.  Under ``write``, a failure
    is recorded — the failed declaration placed, the teaching
    carried to stderr as a warning, the exit 0.  Availability and
    geometry abort in both modes: a missing verifier or an artifact
    outside the manifest's tree is not the artifact's fact, and the
    toggle does not reach it.
    """
    spec = load_verify_spec(spec_path)
    manifest, created = load_or_init_manifest(
        manifest_path,
        producer_name=spec.producer.name,
        producer_version=spec.producer.version,
        run_id=None,
    )
    check_producer_agreement(manifest, spec.producer.name, spec.producer.version, None)
    verifiers = _verifier_index()
    base = spec_path.parent
    successes = 0
    appended = 0
    updated = 0
    warnings: list[str] = []
    failures: list[tuple[str, str]] = []
    for block in spec.artifacts:
        file = base / block.file
        try:
            record, sha256 = verify_artifact_file(
                verifiers, file, block.format, block.criteria
            )
        except VerificationError as e:
            if on_failure == "fail":
                failures.append((block.id, str(e)))
                continue
            declaration = build_failed_declaration(
                id=block.id,
                type=block.type,
                fmt=block.format,
                schema_version=block.schema_version,
                file=file,
                manifest=manifest_path,
                message=str(e),
            )
            manifest, _ = apply_artifact_declaration(manifest, declaration)
            warnings.append(f"artifact {block.id} recorded as failed: {e}")
            continue
        declaration = build_verified_declaration(
            id=block.id,
            type=block.type,
            fmt=block.format,
            schema_version=block.schema_version,
            file=file,
            manifest=manifest_path,
            record=record,
            sha256=sha256,
        )
        manifest, placement = apply_artifact_declaration(manifest, declaration)
        if placement == "appended":
            appended += 1
        else:
            updated += 1
        successes += 1
    if failures:
        lines = "\n".join(
            f"  - artifact {artifact_id}: {message}"
            for artifact_id, message in failures
        )
        raise VerifyError(
            f"the spec verification failed for {len(failures)} of "
            f"{len(spec.artifacts)} declared artifacts, and nothing was "
            f"written to {manifest_path}:\n{lines}"
        )
    write_manifest_atomically(manifest, manifest_path)
    word = f"{successes} artifact" if successes == 1 else f"{successes} artifacts"
    core = f"verified {word} — appended {appended}, updated {updated}"
    recorded = len(warnings)
    if recorded:
        out = f"{core}, {recorded} recorded as failed in {manifest_path}\n"
    elif created:
        out = (
            f"created {manifest_path} (producer {manifest.producer.name} "
            f"{manifest.producer.version}) — {core}\n"
        )
    else:
        out = f"{core} in {manifest_path}\n"
    return VerifyOutcome(exit_code=0, out=out, warnings=tuple(warnings))


def run_verify(
    *,
    file: Path | None,
    spec_path: Path | None,
    manifest_path: Path,
    id: str | None,
    type: str | None,
    fmt: str | None,
    schema_version: str | None,
    producer_name: str | None,
    producer_version: str | None,
    run_id: str | None,
    criteria_pairs: Sequence[str],
    on_failure: Literal["fail", "write"],
) -> VerifyOutcome:
    """The verify command's library door: one invocation, one mode.

    FILE is flags mode — one artifact, identity from the four
    declaration flags; ``--spec`` is spec mode — every artifact the
    spec declares.  Both is a contradiction in terms; neither is no
    invocation at all.  Both are taught here, with the modes named,
    exit 1 through the handler ``main`` already owns — mode
    resolution belongs with the library's teachings, not argparse's.
    """
    if spec_path is not None:
        if file is not None:
            raise VerifyError(
                "pass either a FILE or --spec, not both — flags mode "
                "verifies the one FILE, spec mode verifies every "
                "artifact the spec declares"
            )
        return run_spec_verify(
            spec_path=spec_path, manifest_path=manifest_path, on_failure=on_failure
        )
    if file is None:
        raise VerifyError(
            "pass a FILE (flags mode verifies one artifact) or --spec "
            "(spec mode verifies every artifact the spec declares) — "
            "one mode per invocation"
        )
    return run_flags_verify(
        file=file,
        manifest_path=manifest_path,
        id=id,
        type=type,
        fmt=fmt,
        schema_version=schema_version,
        producer_name=producer_name,
        producer_version=producer_version,
        run_id=run_id,
        criteria_pairs=criteria_pairs,
        on_failure=on_failure,
    )
