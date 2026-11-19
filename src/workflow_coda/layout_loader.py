"""The layout loader: YAML text in, a validated ``ReportLayout`` out.

The loader is the report author's first point of contact with
validation, so every failure is a teaching error: a
:class:`~workflow_coda.errors.LayoutError` naming the file, the
location inside it, the problem, and the fix.  Failure families:

* **Reading and parsing**: an unreadable file, invalid YAML syntax, or
  a document that is not a mapping.
* **Duplicate keys**: plain YAML resolves duplicate mapping keys by
  silently keeping the *last* occurrence — a copy-paste accident would
  swallow half the author's tabs without an error.  The loader
  rejects duplicates, naming the key and its line.
* **Shape**: layout model violations, reformatted from pydantic's
  error list into one line per problem with a path into the file
  (``tabs[0].components[0].id``).
* **YAML 1.1 boolean traps**: bare ``true``/``false``/``yes``/``no``/
  ``on``/``off`` are *booleans* in YAML, so ``title: no`` arrives as
  the value ``False``, not the word "no".  When a boolean lands in a
  text or policy field, the loader explains the quoting rule instead of
  showing pydantic's opaque "Input should be a valid string".
* **Orphan placeholders**: a ``{`` in a string no ``type: states``
  node can bind.  The states placeholder language substitutes only
  inside a states subtree, so an orphaned brace is an authoring
  mistake taught at load.  Valid ``{{ variable }}`` expressions in
  ``core.markdown``'s ``text`` parameter belong to that component's
  artifact-backed language, not to states.
* **Schema version**: a layout written against an older layout
  schema (``0.1.0``, ``0.2.0``) fails with the migration spelled out —
  the file format is versioned, and old files are taught forward, not
  parsed.

YAML semantics are otherwise standard and unmodified: booleans in
``parameters`` (``show_legend: true``) are correct YAML and pass
through as booleans.  The loader never silently reinterprets what the
author wrote — it fails loudly with an explanation.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from pydantic_core import ErrorDetails
from yaml.constructor import ConstructorError

from .artifact_store import JsonValue
from .core.markdown_variables import MARKDOWN_VARIABLE_RE
from .errors import LayoutError
from .layout import (
    LAYOUT_SCHEMA_VERSION,
    CardNode,
    ComponentPlacement,
    DiagnosticsNode,
    LayoutNode,
    ReportLayout,
    StatesNode,
)

_MISSING = object()
"""Sentinel for a location that does not resolve into the parsed document."""

_MARKDOWN_VARIABLE = MARKDOWN_VARIABLE_RE
"""core.markdown's variable syntax, recognized only to exclude it from
the states orphan check.  The component owns resolution and validation;
the loader never substitutes or changes the parameter text."""


class _DuplicateKeyError(yaml.YAMLError):
    """Internal: a duplicate mapping key, with its 1-based line number."""

    def __init__(self, key: object, line: int) -> None:
        super().__init__(f"duplicate key {key!r} on line {line}")
        self.key = key
        self.line = line


class UniqueKeySafeLoader(yaml.SafeLoader):
    """``SafeLoader`` that rejects duplicate mapping keys.

    The shared YAML machinery for the framework's human-authored files:
    the layout file and the theme files it declares.  YAML's silent
    last-wins resolution is a trap for a hand-authored file, so a
    duplicate becomes an error naming the key and line.
    """

    def construct_mapping(
        self, node: yaml.MappingNode, deep: bool = False
    ) -> dict[Any, Any]:
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                hash(key)
            except TypeError:
                raise ConstructorError(
                    None,
                    None,
                    "mapping keys must be simple values like text or "
                    "numbers; this key is a complex value",
                    key_node.start_mark,
                ) from None
            if key in seen:
                raise _DuplicateKeyError(key, key_node.start_mark.line + 1)
            seen.add(key)
        return super().construct_mapping(node, deep)


def _format_location(location: tuple[int | str, ...]) -> str:
    """A pydantic location tuple as a path into the layout file."""
    parts: list[str] = []
    for key in location:
        if isinstance(key, int):
            parts.append(f"[{key}]")
        elif parts:
            parts.append(f".{key}")
        else:
            parts.append(str(key))
    return "".join(parts)


def _value_at(parsed: object, location: tuple[int | str, ...]) -> object:
    """Resolve *location* into the parsed document.

    Returns :data:`_MISSING` when the path does not resolve, so callers
    can distinguish absence from ``None``.
    """
    value: object = parsed
    for key in location:
        try:
            value = value[key]  # type: ignore[index]
        except (TypeError, KeyError, IndexError):
            return _MISSING
    return value


def _example_key(parsed: object, location: tuple[int | str, ...]) -> str | None:
    """The field name to show in a quoting example, or ``None``.

    Walks the location backwards and returns the outermost location
    element that is genuinely a key of the mapping it sits in — the
    actual field the author wrote.  (For union-typed fields pydantic
    appends a branch tag like ``enum`` to the location; that tag is
    never a real key, so the walk skips past it.)
    """
    for index in range(len(location) - 1, -1, -1):
        key = location[index]
        if not isinstance(key, str):
            continue
        parent = _value_at(parsed, location[:index])
        if isinstance(parent, dict) and key in parent:
            return key
    return None


def _describe_violation(parsed: object, error: ErrorDetails) -> str:
    """One validation problem as a single teaching line."""
    message = error["msg"]
    if message.startswith("Value error, "):
        message = message.removeprefix("Value error, ")
    if isinstance(error["input"], bool):
        example_key = _example_key(parsed, error["loc"])
        example = f', e.g. {example_key}: "yes"' if example_key is not None else ""
        return (
            f"{_format_location(error['loc'])}: YAML parsed this as the "
            f"boolean {error['input']} — bare true/false/yes/no/on/off "
            "are booleans in YAML, not words. Quote the word to make it "
            f"text{example}. ({message})"
        )
    return f"{_format_location(error['loc'])}: {message}"


_COMPOSITION_FIX = (
    "placeholders substitute only inside a 'type: states' node; add "
    "one whose dimension it names, or remove the brace"
)
"""The orphan teaching's fix for composition strings: a states node
could wrap them, so the fix can name one."""

_UNBINDABLE_FIX = (
    "this string sits above the composition, so no states node can "
    "ever bind it; write the literal text"
)
"""The orphan teaching's fix for walk-external strings — report
identity and tab titles — where wrapping is impossible by shape."""


def _reject_brace(
    value: str,
    where: str,
    path: Path,
    *,
    fix: str = _COMPOSITION_FIX,
    allow_markdown_variables: bool = False,
) -> None:
    """The orphan teaching: a ``{`` no states node can bind.

    Composition strings carry the composable fix by default; strings
    above the walk pass ``fix`` explicitly, because "add a states
    node" is impossible advice for a string no states node can ever
    reach.  core.markdown's text may contain its own valid variables:
    exclude those from inspection without changing the original text
    or the value quoted in a teaching.
    """
    inspected = _MARKDOWN_VARIABLE.sub("", value) if allow_markdown_variables else value
    if "{" in inspected:
        raise LayoutError(f"{path}: {where} carries a placeholder ({value!r}) — {fix}")


def _reject_id_brace(placement: ComponentPlacement, where: str, path: Path) -> None:
    """A placement id refuses ``{`` anywhere: an id addresses a
    component, and plugins declare no per-state components."""
    if "{" in placement.id:
        raise LayoutError(
            f"{path}: {where} places id {placement.id!r} carrying a "
            "placeholder — a placement id addresses a component, never "
            "a state; the placeholder belongs in the placement's "
            "parameters or title"
        )


def _reject_brace_json(node: JsonValue, where: str, path: Path) -> None:
    """Every string in a parameters tree refuses ``{`` outside
    states — keys and values alike, recursively.  The placement walk
    handles core.markdown's text separately to recognize its variables."""
    if isinstance(node, str):
        _reject_brace(node, where, path)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _reject_brace_json(item, f"{where}[{index}]", path)
    elif isinstance(node, dict):
        for key, value in node.items():
            _reject_brace(key, f"{where}'s key {key!r}", path)
            _reject_brace_json(value, f"{where}[{key!r}]", path)


def _walk_orphan(node: LayoutNode, where: str, path: Path) -> None:
    """Outside states: rendered strings and ids refuse orphan ``{``.

    Valid variables in core.markdown's text belong to the component,
    not states.  A states subtree switches to the scoped walk: there
    the free strings are the template's own territory (the engine
    teaches scope at build); only ids stay checked.
    """
    if isinstance(node, ComponentPlacement):
        _reject_id_brace(node, where, path)
        if node.title is not None:
            _reject_brace(node.title, f"{where}'s title", path)
        for key, value in node.parameters.items():
            _reject_brace(key, f"{where}'s parameter key {key!r}", path)
            parameter_where = f"{where}'s parameter {key!r}"
            if node.id == "core.markdown" and key == "text" and isinstance(value, str):
                _reject_brace(
                    value, parameter_where, path, allow_markdown_variables=True
                )
            else:
                _reject_brace_json(value, parameter_where, path)
        return
    if isinstance(node, StatesNode):
        for index, child in enumerate(node.children):
            _walk_scoped(child, f"{where}.children[{index}]", path)
        return
    if isinstance(node, DiagnosticsNode):
        return
    if isinstance(node, CardNode) and node.title is not None:
        _reject_brace(node.title, f"{where}'s title", path)
    for index, child in enumerate(node.children):
        _walk_orphan(child, f"{where}.children[{index}]", path)


def _walk_scoped(node: LayoutNode, where: str, path: Path) -> None:
    """Inside a states subtree, only ids refuse ``{``.

    Free strings are the template's territory — the engine teaches
    scope at build — and a nested states node owns its own subtree's
    scope, so the walk recurses through every composition but never
    checks a free string again.
    """
    if isinstance(node, ComponentPlacement):
        _reject_id_brace(node, where, path)
        return
    if isinstance(node, DiagnosticsNode):
        return
    for index, child in enumerate(node.children):
        _walk_scoped(child, f"{where}.children[{index}]", path)


def _reject_orphan_placeholders(layout: ReportLayout, path: Path) -> None:
    """Refuse a states placeholder where no states node can bind it.

    Only ``{`` opens the states placeholder language, and it substitutes
    exclusively inside a ``type: states`` subtree.  core.markdown's
    valid double-brace variables in its text parameter are a separate,
    component-owned language and are left untouched.  Two scopes:
    strings above the walk (report identity, tab titles) can never
    be bound and teach with the literal-text fix; composition strings
    (placement titles and parameters, card titles) teach with the
    states node named as the fix.  Declared file paths (theme, logo,
    favicon) are resolution, not rendering: a brace-bearing path
    fails its own not-found teaching at build.
    """
    _reject_brace(layout.title, "the report's title", path, fix=_UNBINDABLE_FIX)
    if layout.subtitle is not None:
        _reject_brace(
            layout.subtitle, "the report's subtitle", path, fix=_UNBINDABLE_FIX
        )
    if layout.author is not None:
        _reject_brace(layout.author, "the report's author", path, fix=_UNBINDABLE_FIX)
    if layout.version is not None:
        _reject_brace(layout.version, "the report's version", path, fix=_UNBINDABLE_FIX)
    for tab_index, tab in enumerate(layout.tabs):
        _reject_brace(
            tab.title, f"the title of tab {tab.title!r}", path, fix=_UNBINDABLE_FIX
        )
        for node_index, node in enumerate(tab.components):
            _walk_orphan(node, f"tabs[{tab_index}].components[{node_index}]", path)


def load_layout(path: Path) -> ReportLayout:
    """Load and validate the report layout at *path*.

    Raises :class:`~workflow_coda.errors.LayoutError` with a teaching
    message for every failure; see the module docstring for the
    failure families.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise LayoutError(
            f"cannot read the layout file {path}: {e.strerror or e}"
        ) from e
    try:
        parsed = yaml.load(text, Loader=UniqueKeySafeLoader)
    except _DuplicateKeyError as e:
        raise LayoutError(
            f"{path}: duplicate key {e.key!r} on line {e.line} — YAML "
            "normally keeps only the last occurrence without an error; "
            "merge the two blocks into one"
        ) from e
    except yaml.YAMLError as e:
        detail = " ".join(str(e).split())
        raise LayoutError(f"{path}: not valid YAML: {detail}") from e
    if not isinstance(parsed, dict):
        if parsed is None:
            found = "nothing (the file is empty)"
        elif isinstance(parsed, list):
            found = "a list — did the first tab line lose its 'title:' key?"
        else:
            found = f"a single {type(parsed).__name__} value"
        raise LayoutError(
            f"{path}: the layout file must be a mapping of settings "
            f"(title:, tabs:, ...), but it contains {found}"
        )
    declared_version = parsed.get("schema_version")
    if isinstance(declared_version, str) and declared_version != LAYOUT_SCHEMA_VERSION:
        if declared_version == "0.1.0":
            raise LayoutError(
                f"{path}: this layout declares schema_version 0.1.0, but "
                "this workflow-coda reads layout schema "
                f"{LAYOUT_SCHEMA_VERSION} — migrate "
                "the file: rename 'sections:' to 'tabs:', remove the "
                "'toc:' key (tabs are the navigation), and set "
                f'schema_version: "{LAYOUT_SCHEMA_VERSION}"'
            )
        if declared_version == "0.2.0":
            raise LayoutError(
                f"{path}: this layout declares schema_version 0.2.0, but "
                "this workflow-coda reads layout schema "
                f"{LAYOUT_SCHEMA_VERSION} — version 0.3.0 adds the 'type: "
                "states' composition node and changes nothing else: set "
                f'schema_version: "{LAYOUT_SCHEMA_VERSION}" and the file '
                "loads as-is"
            )
        raise LayoutError(
            f"{path}: the layout's schema_version must be "
            f'"{LAYOUT_SCHEMA_VERSION}", but '
            f"this file declares {declared_version!r}"
        )
    try:
        layout = ReportLayout.model_validate(parsed)
    except ValidationError as e:
        lines = "\n".join(
            f"  - {_describe_violation(parsed, error)}" for error in e.errors()
        )
        raise LayoutError(f"{path} is not a valid report layout:\n{lines}") from e
    _reject_orphan_placeholders(layout, path)
    return layout
