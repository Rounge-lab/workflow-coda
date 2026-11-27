"""The verification spec: the pipeline author's declaration.

The spec is a small YAML file declaring optional producer claims and
one block per output file — identity, format, content schema
version, and the criteria the format's verifier reads.  The
loader shares the layout loader's YAML machinery and inherits the
hand-authored-file law: duplicate keys rejected with key and
line, YAML's boolean traps explained with the quoting rule, every
failure raised as :class:`~workflow_coda.errors.SpecError` whose
``str`` is the teaching.

A block may carry a ``for_each``: one dimension — ``batch``,
``sample_id`` — and exactly one source key (``values``,
``samplesheet``, or ``glob``) discovering the dimension's values.
The loader expands each such block into its concrete blocks —
``file:`` templated with the raw values (the disk's names are
the truth), ``id:``/``type:`` through the identity grammar (the
slug under ``sanitize: true``, the grammar-failing raw otherwise),
criteria through the raw substitution — and validation then
never sees a template.  A plain block carrying a placeholder
teaches, rather than riding as a literal: the author almost
certainly meant a loop.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Final

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..errors import SpecError
from ..layout_loader import (
    _describe_violation,
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
from ..yaml_loader import UniqueKeySafeLoader, _DuplicateKeyError
from .expansion import (
    check_family_collisions,
    expand_template,
    identity_value,
    require_no_placeholders,
    substitute_raw,
)
from .sources import (
    values_from_glob,
    values_from_list,
    values_from_samplesheet,
)

_FOR_EACH_KEYS: Final[frozenset[str]] = frozenset(
    {"dimension", "glob", "samplesheet", "values"}
)
"""The ``for_each`` mapping's closed vocabulary: the dimension and
exactly one source key — zero or multiple sources teach."""


class SpecProducer(BaseModel):
    """Optional producer claims supplied by a verification spec.

    Claims reconcile field by field with CLI declarations. Creating a
    manifest requires a complete resolved identity; updating may omit
    claims and retain the resident producer.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: NonEmptyStr | None = None
    """Optional producing-pipeline name; null means no claim."""

    version: NonEmptyStr | None = None
    """Optional producing-pipeline version; null means no claim."""


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

    module_id: NonEmptyStr | None = None
    """Optional producing-module identifier.

    A CLI module declaration may supply this value, but must agree when
    both the CLI and spec declare it. Family expansion substitutes raw
    dimension values into module identifiers.
    """

    criteria: dict[str, JsonValue] | None = None
    """The verifier's criteria: keys and values the owning format's
    verifier reads and validates.  Absent means no criteria."""


class VerifySpec(BaseModel):
    """The whole verification spec: producer and artifact blocks.

    Constructed by load_verify_spec from parsed content. The loader
    requires at least one artifact; producer claims may be omitted or
    partial. Producer completeness belongs to manifest creation, not
    standalone spec loading.

    Once artifact fields validate, ids and types must each be unique
    across all concrete blocks. Repetition within one spec is an
    authoring error, not an instruction to update an earlier block.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    producer: SpecProducer = Field(default_factory=SpecProducer)
    """Optional producer claims — one manifest, one producer."""

    artifacts: tuple[SpecArtifact, ...]
    """The blocks to verify, in declaration order — ``for_each``
    blocks expanded into their concrete blocks, in value order."""

    @field_validator("artifacts")
    @classmethod
    def _validate_unique_artifact_keys(
        cls, value: tuple[SpecArtifact, ...]
    ) -> tuple[SpecArtifact, ...]:
        """Refuse repeated identities across the entire concrete spec.

        Positions are one-based positions after family expansion, not
        YAML line numbers or original template-block positions. IDs and
        types are checked independently; module attribution does not
        partition either identity namespace.
        """
        problems: list[str] = []
        for kind in ("id", "type"):
            groups: dict[str, list[int]] = {}
            for position, artifact in enumerate(value, start=1):
                identity = artifact.id if kind == "id" else artifact.type
                groups.setdefault(identity, []).append(position)
            for identity, positions in groups.items():
                if len(positions) > 1:
                    locations = ", ".join(str(position) for position in positions)
                    problems.append(
                        f"duplicate artifact {kind} {identity!r} "
                        f"in expanded blocks {locations}"
                    )
        if problems:
            raise ValueError(
                "artifact ids and types must each be unique across the "
                "whole spec after family expansion — repeated declarations "
                "are not updates within one invocation:\n"
                + "\n".join(f"  - {problem}" for problem in problems)
            )
        return value


def _require_dimension(source: Mapping[str, JsonValue], *, path: Path) -> str:
    """The ``for_each`` mapping's dimension: present, a non-empty
    string — the loop variable the block's placeholders name."""
    if "dimension" not in source:
        raise SpecError(
            f"{path}: the for_each block requires a 'dimension' — the "
            "loop variable the block's placeholders name"
        )
    dimension = source["dimension"]
    if not isinstance(dimension, str) or not dimension.strip():
        raise SpecError(
            f"{path}: the for_each block's 'dimension' must be a "
            f"non-empty string, got {dimension!r}"
        )
    return dimension


def _require_one_source(
    source: Mapping[str, JsonValue], *, dimension: str, path: Path
) -> str:
    """Exactly one source key — the sketch's law: zero or multiple
    sources teach, the modes named.

    The same fault shape as FILE and ``--spec`` together: a
    contradiction in terms, refused with both readings named so
    the author sees which door they half-opened.
    """
    sources = sorted(key for key in ("values", "samplesheet", "glob") if key in source)
    if not sources:
        raise SpecError(
            f"{path}: the for_each block for dimension {dimension!r} "
            "carries no source — pass exactly one of 'values', "
            f"'samplesheet', or 'glob' (e.g. glob: \"tables/{{"
            f'{dimension}}}.tsv")'
        )
    if len(sources) > 1:
        raise SpecError(
            f"{path}: the for_each block for dimension {dimension!r} "
            f"carries multiple sources ({', '.join(sources)}) — pass "
            "exactly one of 'values', 'samplesheet', or 'glob'; one "
            "block, one source"
        )
    return sources[0]


def _concrete_block(
    block: Mapping[str, JsonValue],
    *,
    raw: str,
    dimension: str,
    sanitize: bool,
    path: Path,
) -> dict[str, JsonValue]:
    """One raw value applied to one block's template: the concrete
    block the models will validate.

    ``for_each`` and ``sanitize`` drop out — they are the loop's
    grammar, not the artifact's identity.  ``id:`` and ``type:``
    expand through their declared templates and then pass through
    the identity grammar; ``criteria`` through the raw
    substitution; every other string leaf through the template —
    one law for every string, no field whitelist.  Non-string
    leaves ride verbatim and the models teach them field by field.
    """
    concrete: dict[str, JsonValue] = {}
    for key, value in block.items():
        if key in ("for_each", "sanitize"):
            continue
        if key == "criteria":
            if not isinstance(value, Mapping):
                raise SpecError(
                    f"{path}: the for_each block's 'criteria' must be a "
                    f"mapping, got {value!r}"
                )
            concrete["criteria"] = substitute_raw(
                dict(value), dimension=dimension, raw=raw, path=path
            )
        elif key == "id":
            if not isinstance(value, str):
                raise SpecError(
                    f"{path}: the for_each block's 'id' must be a string "
                    f"template, got {value!r}"
                )
            concrete["id"] = identity_value(
                value,
                raw=raw,
                kind="id",
                sanitize=sanitize,
                dimension=dimension,
                path=path,
            )
        elif key == "type":
            if not isinstance(value, str):
                raise SpecError(
                    f"{path}: the for_each block's 'type' must be a string "
                    f"template, got {value!r}"
                )
            concrete["type"] = identity_value(
                value,
                raw=raw,
                kind="type",
                sanitize=sanitize,
                dimension=dimension,
                path=path,
            )
        elif isinstance(value, str):
            concrete[key] = expand_template(
                value, dimension=dimension, raw=raw, path=path
            )
        else:
            concrete[key] = value
    return concrete


def _expand_block(
    block: Mapping[str, JsonValue],
    *,
    dimension: str,
    values: tuple[str, ...],
    path: Path,
) -> list[dict[str, JsonValue]]:
    """One ``for_each`` block into its concrete blocks, in value
    order, with the family's collisions refused.

    Two values expanding to one id or one type leave the address
    ambiguous, so the collision check runs over the family per
    identity field, both raws named — before any artifact is
    verified, the loader's collect-and-list law.
    """
    sanitize = block.get("sanitize", False)
    if not isinstance(sanitize, bool):
        raise SpecError(
            f"{path}: the for_each block's 'sanitize' must be a boolean, "
            f"got {sanitize!r}"
        )
    expanded = [
        _concrete_block(
            block, raw=raw, dimension=dimension, sanitize=sanitize, path=path
        )
        for raw in values
    ]
    check_family_collisions(
        [
            (raw, str(concrete["id"]))
            for raw, concrete in zip(values, expanded, strict=True)
            if "id" in concrete
        ],
        kind="id",
        dimension=dimension,
        path=path,
    )
    check_family_collisions(
        [
            (raw, str(concrete["type"]))
            for raw, concrete in zip(values, expanded, strict=True)
            if "type" in concrete
        ],
        kind="type",
        dimension=dimension,
        path=path,
    )
    return expanded


def _walk_strings(node: JsonValue, path: Path) -> None:
    """Every string leaf in a criteria tree: a placeholder with no
    dimension in scope teaches, rather than riding as a literal."""
    if isinstance(node, str):
        require_no_placeholders(node, path=path)
    elif isinstance(node, list):
        for item in node:
            _walk_strings(item, path)
    elif isinstance(node, Mapping):
        for key, value in node.items():
            if isinstance(key, str):
                require_no_placeholders(key, path=path)
            _walk_strings(value, path)


def _check_plain_block(
    block: dict[str, JsonValue], *, path: Path
) -> dict[str, JsonValue]:
    """A plain block's placeholders: none may ride — outside a
    ``for_each`` the placeholder cannot mean anything, so it
    teaches rather than passing through as a literal."""
    for key in ("file", "id", "type", "format", "schema_version", "module_id"):
        value = block.get(key)
        if isinstance(value, str):
            require_no_placeholders(value, path=path)
    criteria = block.get("criteria")
    if criteria is not None:
        _walk_strings(criteria, path)
    return block


def _expand_for_each(
    block: dict[str, JsonValue], *, path: Path
) -> list[dict[str, JsonValue]]:
    """One raw ``for_each`` block into its concrete blocks: the
    grammar checked, the values discovered, the block expanded.

    The grammar fires before the disk is touched — a source
    contradiction or a missing ``file:`` template is the author's
    mistake, named before any file is read.  The ``file:``/``glob:``
    matrix is the sketch's law transposed: the glob is its own
    path provider, so ``file:`` is forbidden with it and required
    without it.
    """
    source = block["for_each"]
    if not isinstance(source, Mapping):
        raise SpecError(
            f"{path}: the for_each block must be a mapping of 'dimension' "
            "and exactly one source key ('values', 'samplesheet', or "
            f"'glob'), got {source!r}"
        )
    unknown = sorted(set(source) - _FOR_EACH_KEYS)
    if unknown:
        findings = ", ".join(f"unknown key {key!r}" for key in unknown)
        raise SpecError(
            f"{path}: the for_each block carries {findings} — the accepted "
            "keys are: 'dimension', 'glob', 'samplesheet', 'values'"
        )
    dimension = _require_dimension(source, path=path)
    source_key = _require_one_source(source, dimension=dimension, path=path)
    if source_key == "glob":
        if "file" in block:
            raise SpecError(
                f"{path}: the for_each block carries both 'file:' and "
                f"'glob:' — the glob is its own path provider (glob: "
                f"\"tables/{{{dimension}}}.tsv\"); remove the 'file:' key"
            )
        values = values_from_glob(
            source["glob"], dimension=dimension, spec_dir=path.parent, path=path
        )
        expanded = _expand_block(block, dimension=dimension, values=values, path=path)
        glob_template = source["glob"]
        if not isinstance(glob_template, str):
            raise SpecError(
                f"{path}: the for_each block's 'glob' must be a pattern string, "
                f"got {glob_template!r}"
            )
        for raw, concrete in zip(values, expanded, strict=True):
            concrete["file"] = expand_template(
                glob_template, dimension=dimension, raw=raw, path=path
            )
        return expanded
    if "file" not in block:
        raise SpecError(
            f"{path}: the for_each block requires a 'file' template — "
            f'pass file: "output/{{{dimension}}}.json" (a glob '
            "carries no file: it is its own path provider)"
        )
    if source_key == "samplesheet":
        values = values_from_samplesheet(
            source["samplesheet"],
            dimension=dimension,
            spec_dir=path.parent,
            path=path,
        )
    else:
        values = values_from_list(source["values"], dimension=dimension, path=path)
    return _expand_block(block, dimension=dimension, values=values, path=path)


def _expand_artifacts(blocks: JsonValue, *, path: Path) -> list[dict[str, JsonValue]]:
    """The spec's artifact blocks, every ``for_each`` expanded —
    the stage between parse and validation, so the models never
    see a template."""
    if not isinstance(blocks, list):
        raise SpecError(
            f"{path}: the spec's 'artifacts' must be a list of blocks — "
            f"one per artifact to verify, got {blocks!r}"
        )
    expanded: list[dict[str, JsonValue]] = []
    for position, block in enumerate(blocks):
        if not isinstance(block, dict):
            raise SpecError(
                f"{path}: artifact block {position + 1} must be a mapping "
                f"— one block per artifact to verify, got {block!r}"
            )
        if "for_each" in block:
            expanded.extend(_expand_for_each(block, path=path))
        else:
            expanded.append(_check_plain_block(block, path=path))
    return expanded


def load_verify_spec(path: Path) -> VerifySpec:
    """Load and validate a verification spec file.

    Raises :class:`~workflow_coda.errors.SpecError` — with the file
    path for context — when the file is unreadable, not valid
    UTF-8, not valid YAML, not a mapping, or violating the spec
    contract: no artifact blocks or a
    shape violation taught field by field.  The teaching shapes are
    the layout loader's, whose machinery this loader shares.

    The expansion stage sits between parse and validation: each
    ``for_each`` block becomes its concrete blocks — values
    discovered through its one source, templates substituted,
    family collisions refused — before ``VerifySpec`` validates
    the result.  A plain block carrying a placeholder teaches:
    the author almost certainly meant a loop.

    Validation also refuses duplicate ids and types across the whole
    concrete spec, collecting collisions with their one-based expanded
    block positions before any artifact is verified.
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
    if not parsed.get("artifacts"):
        raise SpecError(
            f"{path}: the spec must declare at least one artifact — a "
            "spec that verifies nothing is an authoring mistake"
        )
    expanded = _expand_artifacts(parsed["artifacts"], path=path)
    document = {**parsed, "artifacts": expanded}
    try:
        return VerifySpec.model_validate(document)
    except ValidationError as e:
        lines = "\n".join(
            f"  - {_describe_violation(document, error)}" for error in e.errors()
        )
        raise SpecError(f"{path} is not a valid verification spec:\n{lines}") from e
