"""The verify drivers: one invocation, one mode, one outcome.

Flags mode (:func:`run_flags_verify`) verifies the single FILE,
identity from the four declaration flags; spec mode
(:func:`run_spec_verify`) verifies every artifact the spec
declares.  :func:`run_verify` is the command's one door — it
resolves the mode from the invocation and routes to the driver.
The drivers return a :class:`VerifyOutcome`; they never print and
never touch the process — the CLI is the only printer: *out* to
stdout, warnings to stderr, *exit_code* last.

Each driver composes the package's layers, and the composition
order is the teachings' order: identity and verifier availability
are checked before the manifest is touched, so an invocation's
own mistake is never blamed on the manifest.  The
``--on-failure`` toggle owns only the artifact's own verification
failures — availability and geometry abort regardless of it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..errors import VerificationError, VerifyError
from ..manifest import (
    MANIFEST_SCHEMA_VERSION,
    ArtifactFormat,
    JsonValue,
    NamespacedArtifactFormat,
)
from ..plugins import ArtifactVerifier
from ..registry import PluginRegistry
from .declarations import (
    apply_artifact_declaration,
    build_failed_declaration,
    build_verified_declaration,
    check_producer_agreement,
    load_or_init_manifest,
    write_manifest_atomically,
)
from .engine import _format_key, _require_verifier, verify_artifact_file
from .spec import load_verify_spec


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
