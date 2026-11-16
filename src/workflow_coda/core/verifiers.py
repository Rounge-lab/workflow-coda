"""The core plugin's artifact verifiers: the contract behind
``workflow-coda verify``.

Four verifiers live here.  The framework's agnostic trio (``json``,
``txt``, ``bytes``) is implemented in the core package and wired
unconditionally by the registry — the agnostic formats are the
framework's own to verify — while ``core.tabular`` rides the core
plugin's declaration like a component, gated by the manifest version
like everything else the plugin offers.

The verifier contract: *bytes in, record out*.  The CLI owns file
IO and computes the sha256 over exactly these bytes; the verifier
checks what it can and returns its record — the account of what was
checked, under which reading, that rides the manifest as opaque
transport.  Criteria are transport all the way down: the verifier
owns its vocabulary, accepts both typed (spec) and string (flags)
shapes, teaches unknown keys with a suggestion, and the framework
never splits a comma outside this grammar.

The ``core.tabular`` verifier is the tabular grammar's second
consumer: the same parse, header, and alignment shape laws
``core.table`` renders under, reused from its module — so the
verifier's default reading *is* the component's default reading,
and a file that passes basic verification is a file the component
renders with no policy overrides.  Criteria adjust the reading
(``sep``, ``header``) and add the pipeline's promises (``columns``
present, ``min_rows``).
"""

import difflib
import json
from collections.abc import Mapping
from typing import Final

from ..artifact_store import JsonValue
from ..errors import ArtifactReadError, VerificationError
from ..plugins import ArtifactVerifier
from .table import _parse_entries, _require_aligned, _require_header

_JSON_CRITERIA: Final[frozenset[str]] = frozenset({"keys"})
"""The json verifier's accepted criteria vocabulary."""

_TABULAR_CRITERIA: Final[frozenset[str]] = frozenset(
    {"sep", "header", "columns", "min_rows"}
)
"""The core.tabular verifier's accepted criteria vocabulary."""


def _decode(data: bytes, label: str) -> str:
    """Strict UTF-8, the store's own read semantics."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise VerificationError(f"{label} is not valid UTF-8: {e}") from e


def _reject_unknown_criteria(
    verification_name: str,
    criteria: Mapping[str, JsonValue],
    accepted: frozenset[str],
) -> None:
    """Unknown criterion keys teach, with the closest match —
    ``reject_unknown_parameters``' law at the verifier boundary."""
    unknown = sorted(key for key in criteria if key not in accepted)
    if not unknown:
        return
    findings: list[str] = []
    for key in unknown:
        close = difflib.get_close_matches(key, accepted, n=1)
        hint = f" (did you mean {close[0]!r}?)" if close else ""
        findings.append(f"unknown criterion {key!r}{hint}")
    names = ", ".join(f"{key!r}" for key in sorted(accepted))
    raise VerificationError(
        f"{verification_name}: {', '.join(findings)} — the accepted "
        f"criteria are: {names}"
    )


def _criterion_names(
    value: JsonValue, verification_name: str, criterion: str
) -> list[JsonValue]:
    """A names criterion: a list (spec transport) or one
    comma-separated string (flags transport) — non-empty, unique,
    returned as JSON transport.

    The names validate as plain strings — a non-string item
    teaches — and cross into ``JsonValue`` element-wise at the
    end: ``str`` is a JSON value, but ``list[str]`` is not
    ``list[JsonValue]`` (list invariance), and ``extend`` is the
    sound crossing; a whole-list assignment or a cast is not.
    """
    names: list[str] = []
    if isinstance(value, str):
        for piece in value.split(","):
            names.append(piece.strip())
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, str):
                raise VerificationError(
                    f"{verification_name}: criterion {criterion!r} must be "
                    f"a list of names or a comma-separated string, got "
                    f"{value!r}"
                )
            names.append(item)
    else:
        raise VerificationError(
            f"{verification_name}: criterion {criterion!r} must be a list "
            f"of names or a comma-separated string, got {value!r}"
        )
    if not names or any(not name for name in names):
        raise VerificationError(
            f"{verification_name}: criterion {criterion!r} must name at "
            f"at least one entry, got {value!r}"
        )
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise VerificationError(
                f"{verification_name}: criterion {criterion!r} names "
                f"{name!r} twice — names are unique"
            )
        seen.add(name)
    items: list[JsonValue] = []
    items.extend(names)
    return items


def _criterion_bool(value: JsonValue, verification_name: str, criterion: str) -> bool:
    """A boolean criterion: a bool (spec transport) or its string
    spelling (flags transport)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise VerificationError(
        f"{verification_name}: criterion {criterion!r} must be a boolean, got {value!r}"
    )


def _criterion_int(value: JsonValue, verification_name: str, criterion: str) -> int:
    """A non-negative integer criterion: an int (spec transport) or
    its string spelling (flags transport).  Booleans are refused
    explicitly — YAML's bare true/false are words about data, and a
    boolean count is an accident."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise VerificationError(
            f"{verification_name}: criterion {criterion!r} must be an "
            f"integer, got {value!r}"
        )
    try:
        number = int(value)
    except ValueError as e:
        raise VerificationError(
            f"{verification_name}: criterion {criterion!r} must be an "
            f"integer, got {value!r}"
        ) from e
    if number < 0:
        raise VerificationError(
            f"{verification_name}: criterion {criterion!r} must be 0 or "
            f"greater, got {value!r}"
        )
    return number


def _verify_json(
    data: bytes, criteria: Mapping[str, JsonValue]
) -> dict[str, JsonValue]:
    """The json verifier: strict UTF-8 and parses, plus the optional
    ``keys`` promise — a subset check on the top-level object, the
    exact surface core.kpi's dotted paths and core.markdown's
    variables resolve against."""
    _reject_unknown_criteria("json verification", criteria, _JSON_CRITERIA)
    text = _decode(data, "the json artifact")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        raise VerificationError(
            f"the json artifact does not parse as JSON at line "
            f"{e.lineno}, column {e.colno}: {e.msg}"
        ) from e
    record: dict[str, JsonValue] = {"format": "json", "status": "ok"}
    if "keys" not in criteria:
        return record
    keys = _criterion_names(criteria["keys"], "json verification", "keys")
    if not isinstance(payload, dict):
        raise VerificationError(
            "json verification: criterion 'keys' requires a top-level "
            f"object, but the artifact's top-level value is a "
            f"{type(payload).__name__}"
        )
    missing = [key for key in keys if key not in payload]
    if missing:
        named = ", ".join(repr(key) for key in missing)
        raise VerificationError(
            f"json verification: the criteria names {named}, but the "
            f"artifact's top-level object does not carry "
            f"{'it' if len(missing) == 1 else 'them'}"
        )
    record["keys_checked"] = keys
    return record


def _verify_txt(data: bytes, criteria: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """The txt verifier: strict UTF-8, and nothing to promise — the
    format claims text, so criteria are refused, not guessed."""
    if criteria:
        keys = ", ".join(repr(key) for key in sorted(criteria))
        raise VerificationError(
            f"txt verification takes no criteria — the format claims "
            f"UTF-8 text and nothing more; got {keys}"
        )
    _decode(data, "the txt artifact")
    return {"format": "txt", "status": "ok"}


def _verify_bytes(
    data: bytes, criteria: Mapping[str, JsonValue]
) -> dict[str, JsonValue]:
    """The bytes verifier: existence is the caller's check, and the
    format claims nothing beyond it — any criteria are refused."""
    if criteria:
        keys = ", ".join(repr(key) for key in sorted(criteria))
        raise VerificationError(
            f"bytes verification takes no criteria — the format claims "
            f"nothing to check beyond existence; got {keys}"
        )
    return {"format": "bytes", "status": "ok"}


def _verify_tabular(
    data: bytes, criteria: Mapping[str, JsonValue]
) -> dict[str, JsonValue]:
    """The core.tabular verifier: the component's shape laws under
    the declared reading, plus the pipeline's promises.

    The shape laws come from ``core.table``'s own helpers — parse,
    header, alignment — wrapped as verification teachings; the
    default reading is the component's (tab, header present), and
    the criteria adjust it: ``sep``, ``header``, and the promises
    ``columns`` (a presence check — order and selection are
    presentation, the component's business) and ``min_rows`` (data
    rows, the header excluded).
    """
    _reject_unknown_criteria("core.tabular verification", criteria, _TABULAR_CRITERIA)
    sep = criteria.get("sep", "\t")
    if not isinstance(sep, str) or len(sep) != 1:
        raise VerificationError(
            f"core.tabular verification: criterion 'sep' must be a single "
            f"character delimiter, got {sep!r}"
        )
    header = _criterion_bool(
        criteria.get("header", True), "core.tabular verification", "header"
    )
    columns = (
        _criterion_names(criteria["columns"], "core.tabular verification", "columns")
        if "columns" in criteria
        else None
    )
    min_rows = (
        _criterion_int(criteria["min_rows"], "core.tabular verification", "min_rows")
        if "min_rows" in criteria
        else None
    )
    if columns is not None and not header:
        raise VerificationError(
            "core.tabular verification: criterion 'columns' selects "
            "columns by their header names, but this verification "
            "declares header: false — a headerless table has no column "
            "names to promise"
        )
    text = _decode(data, "the tabular artifact")
    try:
        entries = _parse_entries(text, sep, "the artifact")
        if header:
            head, has_index = _require_header(entries, "the artifact")
            width = len(head)
            data_rows = entries[1:]
        else:
            if not entries:
                raise VerificationError(
                    "the artifact has no rows, so its column count is "
                    "unknown — a headerless verification needs at least "
                    "one row"
                )
            head = ()
            has_index = False
            width = len(entries[0][1])
            data_rows = entries
        rows = _require_aligned(data_rows, width, sep, "the artifact")
    except ArtifactReadError as e:
        raise VerificationError(
            f"the artifact does not verify as core.tabular: {e}"
        ) from e
    if columns is not None:
        named = head[1:] if has_index else head
        missing = [name for name in columns if name not in named]
        if missing:
            listed = ", ".join(repr(name) for name in named) or "no named columns"
            raise VerificationError(
                f"core.tabular verification: the criteria names "
                f"{', '.join(repr(name) for name in missing)}, but the "
                f"artifact's header does not carry "
                f"{'it' if len(missing) == 1 else 'them'} (carries: "
                f"{listed})"
            )
    if min_rows is not None and len(rows) < min_rows:
        raise VerificationError(
            f"core.tabular verification: the criteria requires at least "
            f"{min_rows} data rows, but the artifact carries "
            f"{len(rows)}"
        )
    record: dict[str, JsonValue] = {
        "format": "core.tabular",
        "status": "ok",
        "sep": sep,
        "header": header,
        "rows": len(rows),
    }
    if columns is not None:
        record["columns_checked"] = columns
    if min_rows is not None:
        record["min_rows"] = min_rows
    return record


JSON_VERIFIER: Final[ArtifactVerifier] = ArtifactVerifier(
    format="json", verify=_verify_json
)
TXT_VERIFIER: Final[ArtifactVerifier] = ArtifactVerifier(
    format="txt", verify=_verify_txt
)
BYTES_VERIFIER: Final[ArtifactVerifier] = ArtifactVerifier(
    format="bytes", verify=_verify_bytes
)
FRAMEWORK_VERIFIERS: Final[tuple[ArtifactVerifier, ...]] = (
    JSON_VERIFIER,
    TXT_VERIFIER,
    BYTES_VERIFIER,
)
"""The framework's own trio, assembled into every registry — the
agnostic formats are the framework's to verify, unconditionally."""

TABULAR_VERIFIER: Final[ArtifactVerifier] = ArtifactVerifier(
    format="core.tabular", verify=_verify_tabular
)
"""The core plugin's tabular verifier, declared on the roster like a
component and gated by the manifest version like everything the
plugin offers."""
