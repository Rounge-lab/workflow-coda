"""The ``for_each`` value sources: how a dimension's values are
discovered.

Three doors, one order law each — the sketch's discriminated
union.  ``values`` are declared in the spec itself (order as
written); ``samplesheet`` discovers from the sheet the pipeline
read too — the single source of truth, first-appearance order,
the producer's order is the story; ``glob`` discovers from what
the step actually wrote (natural order — when only the disk
speaks, an order that varies by filesystem is an accident, not an
order).  Which source a block carries, and the ``file:`` rules
around it, is the spec loader's wiring; these resolvers take one
source's raw value and return its ordered raw values.

The samplesheet reads through the tabular grammar — the same
parse, header, and alignment shape laws ``core.table`` renders
under, imported from its module the way ``core.verifiers`` does:
the grammar is one, not mirrored.  Its data problems teach at
discovery, collect-and-list — a blank cell (a dimension value is
a name) and a value appearing twice (the sheet lists one sample
as two rows), every instance named before the spec loads.

The glob is the wildcard idiom: the braces are the capture, so
the pattern carries exactly one placeholder — the block's own
``{dimension}`` — and the rest of the pattern is the file's
literal shape; other wildcards would make the capture's extent
ambiguous, so they teach rather than guess.  Hidden files follow
glob's own law and stay undiscovered.

Every failure is a spec-authoring teaching raised as
:class:`~workflow_coda.errors.SpecError` — these fire at spec
load, before a single artifact is verified, and a source that
discovers no values is the availability family: there is no
artifact yet to record, so the ``--on-failure`` toggle never
reaches it.
"""

import glob
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from ..core.table import _parse_entries, _require_aligned, _require_header
from ..errors import ArtifactReadError, SpecError
from ..manifest import JsonValue
from ..text import natural_key
from .expansion import _PLACEHOLDER

_SAMPLESHEET_KEYS: Final[frozenset[str]] = frozenset({"file", "column", "sep"})
"""The samplesheet source's accepted keys — the closed vocabulary
the unknown-key teaching lists."""


def _no_values(dimension: str, detail: str, *, path: Path) -> SpecError:
    """The one zero-values teaching, shared by all three sources:
    an empty family declares no artifacts — there is nothing to
    record, so the failure is the spec's, not any artifact's."""
    return SpecError(
        f"{path}: the for_each dimension {dimension!r} discovered no "
        f"values — {detail}; an empty family declares no artifacts: "
        "remove the for_each block, or fix its source"
    )


def values_from_list(
    source: JsonValue, *, dimension: str, path: Path
) -> tuple[str, ...]:
    """The declared source: the values list, order as written.

    A list of non-empty strings — numbers and booleans are YAML
    traps here, taught with the quoting rule, and a blank value
    is a nameless name.  Duplicates are not this resolver's
    teaching: they expand to colliding ids and types, which the
    expansion's collision check refuses at spec load with both
    raws named.
    """
    if not isinstance(source, list):
        raise SpecError(
            f"{path}: the for_each source 'values' must be a list of "
            f"strings, got {source!r}"
        )
    values: list[str] = []
    for position, item in enumerate(source):
        if not isinstance(item, str):
            raise SpecError(
                f"{path}: the for_each values for dimension {dimension!r} "
                "must be strings — a dimension value is a name, so quote "
                f"numbers and booleans in YAML; item {position + 1} is "
                f"{item!r}"
            )
        if not item.strip():
            raise SpecError(
                f"{path}: the for_each values for dimension {dimension!r} "
                f"must be non-empty — item {position + 1} is blank"
            )
        values.append(item)
    if not values:
        raise _no_values(dimension, "the values list is empty", path=path)
    return tuple(values)


def _required_sheet_key(
    source: Mapping[str, JsonValue], key: str, *, what: str, path: Path
) -> str:
    """A required samplesheet field: present, a non-empty string.

    *what* carries the field's meaning into the missing-field
    teaching — the sheet to read, the column to scan — so the
    error tells the author what the key is for, not only that it
    is absent.
    """
    if key not in source:
        raise SpecError(f"{path}: the for_each samplesheet requires a {key!r} — {what}")
    value = source[key]
    if not isinstance(value, str) or not value:
        raise SpecError(
            f"{path}: the for_each samplesheet's {key!r} must be a "
            f"non-empty string, got {value!r}"
        )
    return value


def _samplesheet_reader(source: JsonValue, *, path: Path) -> tuple[str, str, str]:
    """The samplesheet source's own mapping, validated: the sheet's
    file, the values column, the separator.

    The closed vocabulary — 'file', 'column', optional 'sep' — is
    checked here, before any bytes are read; the sheet itself is
    read one function down, and the two together are one source.
    """
    if not isinstance(source, dict):
        raise SpecError(
            f"{path}: the for_each source 'samplesheet' must be a mapping "
            f"of 'file', 'column', and optional 'sep', got {source!r}"
        )
    unknown = sorted(set(source) - _SAMPLESHEET_KEYS)
    if unknown:
        findings = ", ".join(f"unknown key {key!r}" for key in unknown)
        raise SpecError(
            f"{path}: the for_each samplesheet carries {findings} — the "
            "accepted keys are: 'column', 'file', 'sep'"
        )
    sheet_file = _required_sheet_key(
        source,
        "file",
        what="the sheet to read, relative to the spec's own directory",
        path=path,
    )
    column = _required_sheet_key(
        source,
        "column",
        what="the header column holding the dimension's values",
        path=path,
    )
    sep = source.get("sep", "\t")
    if not isinstance(sep, str) or len(sep) != 1:
        raise SpecError(
            f"{path}: the for_each samplesheet's 'sep' must be a single "
            f'character, got {sep!r} — quote a tab as "\\t" (the '
            "default is the tab)"
        )
    return sheet_file, column, sep


def _scan_column(
    data: list[tuple[int, tuple[str, ...]]],
    column_index: int,
    *,
    sheet_file: str,
    column: str,
    path: Path,
) -> list[str]:
    """The column's values, first appearance — the data scan.

    A blank cell teaches (a dimension value is a name); a value
    appearing twice teaches (the sheet lists one sample as two
    rows) — both collect-and-list, every instance named, before
    the spec loads.
    """
    values: list[str] = []
    first_line: dict[str, int] = {}
    problems: list[str] = []
    for line_num, row in data:
        cell = row[column_index]
        if not cell.strip():
            problems.append(
                f"  - line {line_num}: a blank cell — a dimension value is a name"
            )
        elif cell in first_line:
            problems.append(
                f"  - line {line_num}: {cell!r} already appeared on "
                f"line {first_line[cell]} — dimension values are unique"
            )
        else:
            first_line[cell] = line_num
            values.append(cell)
    if problems:
        lines = "\n".join(problems)
        raise SpecError(
            f"{path}: the samplesheet {sheet_file!r} has invalid values "
            f"in column {column!r}:\n{lines}"
        )
    return values


def _read_samplesheet(
    sheet_file: str,
    column: str,
    sep: str,
    *,
    dimension: str,
    spec_dir: Path,
    path: Path,
) -> tuple[str, ...]:
    """The sheet's values: read through the tabular grammar, the
    named column scanned — the reading half of the samplesheet
    source.

    The sheet is the pipeline's own record, so first appearance
    is the declaration order — the producer's order is the story.
    A header whose first cell is blank declares an index column,
    in-band, exactly as the component reads it.
    """
    sheet_path = spec_dir / sheet_file
    try:
        text = sheet_path.read_text(encoding="utf-8")
    except OSError as e:
        raise SpecError(
            f"could not read the samplesheet {sheet_file!r}: {e.strerror or e}"
        ) from e
    except UnicodeDecodeError as e:
        raise SpecError(
            f"the samplesheet {sheet_file!r} is not valid UTF-8: {e}"
        ) from e
    label = f"'{sheet_file}' (the for_each samplesheet)"
    try:
        entries = _parse_entries(text, sep, label)
        head, has_index = _require_header(entries, label)
        data = entries[1:]
        # The alignment check certifies the data; its return value drops
        # line numbers, so the scan below iterates the certified data.
        _require_aligned(data, len(head), sep, label)
    except ArtifactReadError as e:
        raise SpecError(f"{path}: {e}") from e
    named = head[1:] if has_index else head
    if column not in named:
        carried = ", ".join(repr(name) for name in named) or "no named columns"
        raise SpecError(
            f"{path}: the for_each samplesheet names column {column!r}, "
            f"but the sheet {sheet_file!r} carries {carried}"
        )
    if not data:
        raise _no_values(
            dimension,
            f"the samplesheet {sheet_file!r} carries no rows",
            path=path,
        )
    values = _scan_column(
        data, head.index(column), sheet_file=sheet_file, column=column, path=path
    )
    return tuple(values)


def values_from_samplesheet(
    source: JsonValue,
    *,
    dimension: str,
    spec_dir: Path,
    path: Path,
) -> tuple[str, ...]:
    """The sheet source: the samplesheet the pipeline read too —
    the single source of truth, first-appearance order, duplicates
    and blanks refused."""
    sheet_file, column, sep = _samplesheet_reader(source, path=path)
    return _read_samplesheet(
        sheet_file,
        column,
        sep,
        dimension=dimension,
        spec_dir=spec_dir,
        path=path,
    )


def _require_glob_placeholder(pattern: str, *, dimension: str, path: Path) -> None:
    """The glob pattern's capture grammar: exactly one placeholder,
    and it names the block's own dimension.

    The braces are the capture — the sketch's law — so a malformed
    placeholder, a second one, or one naming another dimension is
    a spec-authoring teaching here, before the disk is scanned.
    """
    names: list[str] = []
    scan = 0
    while True:
        brace = pattern.find("{", scan)
        if brace == -1:
            break
        found = _PLACEHOLDER.match(pattern, brace)
        if found is None:
            raise SpecError(
                f"{path}: the glob {pattern!r} carries a malformed "
                "placeholder — '{' must open the block's own "
                f"'{{{dimension}}}'"
            )
        names.append(found.group(1))
        scan = found.end()
    if len(names) != 1:
        carried = ", ".join(f"{{{name}}}" for name in names) or "none"
        raise SpecError(
            f"{path}: the glob {pattern!r} must carry exactly one "
            f"placeholder, the block's own '{{{dimension}}}', but it "
            f"carries {len(names)} ({carried})"
        )
    if names[0] != dimension:
        raise SpecError(
            f"{path}: the glob {pattern!r} names the placeholder "
            f"{{{names[0]}}}, but the block's dimension is "
            f"{dimension!r} — a placeholder names its dimension (a "
            "typo, most likely), and only the dimension substitutes"
        )


def values_from_glob(
    source: JsonValue,
    *,
    dimension: str,
    spec_dir: Path,
    path: Path,
) -> tuple[str, ...]:
    """The wildcard source: what the step actually wrote — the
    braces are the capture, the disk provides the paths.

    The pattern resolves against the spec's own directory like
    every spec path, and may vary only at its capture: the rest
    is the file's literal shape.  Matches are natural-ordered —
    a glob has no producer's story to carry, so the order is
    keyed, not inherited from the filesystem.
    """
    if not isinstance(source, str) or not source:
        raise SpecError(
            f"{path}: the for_each source 'glob' must be a non-empty "
            f"pattern string, got {source!r}"
        )
    pattern = source
    _require_glob_placeholder(pattern, dimension=dimension, path=path)
    if Path(pattern).is_absolute():
        raise SpecError(
            f"{path}: the glob {pattern!r} must be relative — it "
            "resolves against the spec's own directory, like every "
            "spec path"
        )
    capture = f"{{{dimension}}}"
    prefix, _, suffix = pattern.partition(capture)
    if any(mark in prefix or mark in suffix for mark in "*?["):
        raise SpecError(
            f"{path}: the glob {pattern!r} may vary only at its "
            f"capture '{{{dimension}}}' — the rest of the pattern is "
            "the file's literal shape; other wildcards would make "
            "the capture ambiguous"
        )
    try:
        matches = glob.glob(f"{prefix}*{suffix}", root_dir=str(spec_dir))
    except (OSError, ValueError) as e:
        raise SpecError(f"{path}: the glob {pattern!r} does not scan: {e}") from e
    raws: list[str] = []
    problems: list[str] = []
    prefix_len = len(prefix)
    suffix_len = len(suffix)
    for matched in sorted(matches):
        if not (spec_dir / matched).is_file():
            continue
        relative = matched.replace(os.sep, "/")
        raw = relative[prefix_len : len(relative) - suffix_len]
        if not raw.strip():
            problems.append(
                f"  - {relative!r}: a blank capture — "
                "a dimension value must be a non-blank name"
            )
        else:
            raws.append(raw)
    if problems:
        raise SpecError(
            f"{path}: the glob {pattern!r} has invalid captures "
            f"for dimension {dimension!r}:\n" + "\n".join(problems)
        )
    if not raws:
        raise _no_values(
            dimension,
            f"the glob {pattern!r} matches no files beside the spec",
            path=path,
        )
    raws.sort(key=lambda raw: (natural_key(raw), raw))
    return tuple(raws)
