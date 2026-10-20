"""Manifest-relative artifact resolution and typed loading.

The artifact store is the framework's only gateway to artifact contents.
Plugins do not touch the filesystem directly: they resolve declared
artifacts through :meth:`ArtifactStore.require` and read them through the
returned :class:`ResolvedArtifact` handle.

Resolution enforces the artifact contract's safety rules: artifact paths
are interpreted relative to the manifest root, and a resolved location must
remain inside it.  The manifest models already reject non-relative paths and
``..`` segments at parse time, so a containment failure here indicates a
symbolic link pointing outside the root.

Failures raise subclasses of :class:`WorkflowCodaError` from
``workflow_coda.errors``.
"""

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Self, cast

from .errors import (
    ArtifactChecksumError,
    ArtifactReadError,
    ArtifactResolutionError,
    ArtifactUnavailableError,
)
from .manifest import (
    ArtifactDeclaration,
    ArtifactStatus,
    ArtifactType,
    ReportManifest,
    load_manifest,
)

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)
"""A fully typed JSON value, as returned by :meth:`ResolvedArtifact.read_json`."""


@dataclass(frozen=True, slots=True)
class ResolvedArtifact:
    """A declared ``complete`` artifact whose location has been verified.

    ``path`` is absolute, contained within the manifest root, and referred
    to an existing regular file at resolution time.  A declared ``sha256``
    is verified over the exact bytes that a read method decodes and parses.
    """

    declaration: ArtifactDeclaration
    """The manifest declaration this artifact was resolved from."""

    path: Path
    """Absolute resolved location of the artifact file."""

    @property
    def _label(self) -> str:
        """Compact identifier for error messages, e.g. ``'qc' (org.x.qc)``."""
        return f"{self.declaration.id!r} ({self.declaration.type})"

    def _read_bytes(self) -> bytes:
        """Read the file, verifying a declared checksum over the raw bytes."""
        try:
            data = self.path.read_bytes()
        except OSError as e:
            raise ArtifactReadError(
                f"artifact {self._label} could not be read: {e}"
            ) from e
        expected = self.declaration.sha256
        if expected is not None:
            digest = hashlib.sha256(data).hexdigest()
            if digest != expected:
                raise ArtifactChecksumError(
                    f"artifact {self._label} failed its sha256 check "
                    f"(declared {expected}, actual {digest})"
                )
        return data

    def _read_text(self) -> str:
        """Read and decode the file as UTF-8."""
        try:
            return self._read_bytes().decode("utf-8")
        except UnicodeDecodeError as e:
            raise ArtifactReadError(f"artifact {self._label} is not valid UTF-8") from e

    def read_text(self) -> str:
        """Read the artifact as checksum-verified UTF-8 text.

        The escape hatch for consumers with their own parsers (e.g. polars,
        pandas, or a domain schema validator): it guarantees the same
        checksum, encoding, and containment checks as :meth:`read_tsv` and
        :meth:`read_json` while leaving interpretation entirely to the caller.
        """
        return self._read_text()

    def read_bytes(self) -> bytes:
        """Read the artifact as checksum-verified raw bytes.

        The binary door for plugin-defined formats: a plugin that
        parses its own artifact kind (a BAM index, an image) reads
        bytes through this method and gets the same checksum,
        containment, and existence guarantees as every other reader —
        no interpretation, and no format gate: readers are explicit,
        per the store's design.
        """
        return self._read_bytes()

    def read_tsv(self) -> list[dict[str, str]]:
        """Read the artifact as a TSV table.

        Returns one dictionary per data row, mapping column names to field
        values.  The first row must be a header of unique, non-empty column
        names, and every data row must match the header's field count.  A
        header with no data rows yields an empty list; blank lines are
        skipped.  Quoting follows the ``csv`` module's default dialect.
        """
        text = self._read_text()
        reader = csv.reader(io.StringIO(text, newline=""), delimiter="\t")
        try:
            header = next(reader, None)
        except csv.Error as e:
            raise ArtifactReadError(
                f"artifact {self._label} is not valid TSV: {e}"
            ) from e
        if header is None:
            raise ArtifactReadError(f"artifact {self._label} contains no header row")
        if not header:
            raise ArtifactReadError(f"artifact {self._label} has an empty header row")

        seen: set[str] = set()
        for column in header:
            if not column:
                raise ArtifactReadError(
                    f"artifact {self._label} has an empty header column name"
                )
            if column in seen:
                raise ArtifactReadError(
                    f"artifact {self._label} has duplicate header column {column!r}"
                )
            seen.add(column)

        width = len(header)
        records: list[dict[str, str]] = []
        try:
            for row in reader:
                if not row:  # Blank line.
                    continue
                if len(row) != width:
                    raise ArtifactReadError(
                        f"artifact {self._label}: row at line {reader.line_num} has "
                        f"{len(row)} fields, expected {width}"
                    )
                records.append(dict(zip(header, row, strict=True)))
        except csv.Error as e:
            raise ArtifactReadError(
                f"artifact {self._label} is not valid TSV: {e}"
            ) from e
        return records

    def read_json(self) -> JsonValue:
        """Read the artifact as a JSON document.

        Content schema validation is the consuming plugin's responsibility
        (the artifact contract separates structural loading from domain
        validation), so only syntax is checked here.
        """
        text = self._read_text()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            raise ArtifactReadError(
                f"artifact {self._label} is not valid JSON "
                f"at line {e.lineno}, column {e.colno}: {e.msg}"
            ) from e
        # json.loads with default hooks returns exactly the JsonValue value
        # space, but typeshed types it as Any; this cast marks the single
        # trusted boundary.  Validating here would duplicate work that the
        # artifact contract assigns to plugins.
        return cast(JsonValue, payload)


class ArtifactStore:
    """Resolves manifest-declared artifacts relative to the manifest root.

    Construction takes the parsed manifest and the filesystem location that
    its relative artifact paths resolve against (the directory containing
    the manifest file).  Loading a manifest *file* is a separate concern,
    owned by the manifest loader.
    """

    def __init__(self, manifest: ReportManifest, root: Path) -> None:
        self._manifest = manifest
        self._root = root.resolve()
        # Envelope validation guarantees unique types, so this is unambiguous.
        self._by_type: dict[str, ArtifactDeclaration] = {
            artifact.type: artifact for artifact in manifest.artifacts
        }

    @classmethod
    def from_manifest_file(cls, path: Path | str) -> Self:
        """Build a store rooted at a manifest file's directory.

        Loads and validates the manifest via :func:`load_manifest`, then
        roots the store at the manifest's directory.  Symbolic links in
        ``path`` are resolved first, so a symlinked manifest is addressed
        relative to its *real* location — the bundle its relative artifact
        paths refer to lives around the actual file, not around the link.
        """
        manifest = load_manifest(path)
        root = Path(path).resolve().parent
        return cls(manifest, root)

    @property
    def manifest(self) -> ReportManifest:
        """The manifest this store resolves against."""
        return self._manifest

    @property
    def root(self) -> Path:
        """Absolute directory that artifact paths resolve against."""
        return self._root

    @property
    def declared_types(self) -> frozenset[str]:
        """All artifact types declared in the manifest, regardless of status."""
        return frozenset(self._by_type)

    def __contains__(self, artifact_type: object) -> bool:
        """Whether the manifest declares ``artifact_type``, in any status."""
        return artifact_type in self._by_type

    def find(self, artifact_type: ArtifactType) -> ArtifactDeclaration | None:
        """Return the declaration for ``artifact_type``, or ``None``.

        Inspection only: no filesystem access, and status is not checked.
        Availability is :meth:`require`'s concern.
        """
        return self._by_type.get(artifact_type)

    def require(self, artifact_type: ArtifactType) -> ResolvedArtifact:
        """Resolve a declared ``complete`` artifact for reading.

        Raises :class:`ArtifactUnavailableError` when the type is not
        declared, is declared with a status other than ``complete``, or the
        file is missing — the expected conditions of a partial run.  Raises
        :class:`ArtifactResolutionError` on containment violations.
        """
        declaration = self._by_type.get(artifact_type)
        if declaration is None:
            available = ", ".join(sorted(self._by_type)) or "none"
            raise ArtifactUnavailableError(
                f"manifest declares no artifact of type {artifact_type!r} "
                f"(declared: {available})"
            )
        if declaration.status is not ArtifactStatus.COMPLETE:
            raise ArtifactUnavailableError(
                f"artifact {declaration.id!r} of type {artifact_type!r} is declared "
                f"with status {declaration.status.value!r}; only artifacts with "
                f"status 'complete' can be loaded"
            )
        path = self._resolve(declaration)
        if not path.exists():
            raise ArtifactUnavailableError(
                f"artifact {declaration.id!r} of type {artifact_type!r} "
                f"does not exist at {path}"
            )
        if not path.is_file():
            raise ArtifactResolutionError(
                f"artifact {declaration.id!r} of type {artifact_type!r} "
                f"is not a regular file: {path}"
            )
        return ResolvedArtifact(declaration=declaration, path=path)

    def _resolve(self, declaration: ArtifactDeclaration) -> Path:
        """Resolve a declaration's path, enforcing manifest-root containment."""
        resolved = (self._root / declaration.path).resolve()
        if not resolved.is_relative_to(self._root):
            raise ArtifactResolutionError(
                f"artifact {declaration.id!r} resolves outside the manifest root: "
                f"{resolved} (symbolic link outside the root?)"
            )
        return resolved
