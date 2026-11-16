"""The verification spec: the pipeline author's declaration.

The spec is a small YAML file declaring the run's producer and
one block per output file — identity, format, content schema
version, and the criteria the format's verifier reads.  The
loader shares the layout loader's YAML machinery and inherits the
hand-authored-file law: duplicate keys rejected with key and
line, YAML's boolean traps explained with the quoting rule, every
failure raised as :class:`~workflow_coda.errors.SpecError` whose
``str`` is the teaching.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from ..errors import (
    SpecError,
)
from ..layout_loader import (
    UniqueKeySafeLoader,
    _describe_violation,
    _DuplicateKeyError,
)
from ..manifest import (
    ArtifactFormat,
    ArtifactId,
    ArtifactSchemaVersion,
    ArtifactType,
    JsonValue,
    NamespacedArtifactFormat,
    NonEmptyStr,
)


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
