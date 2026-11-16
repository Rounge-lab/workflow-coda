"""The layout loader: YAML text in, a validated ``ReportLayout`` out.

The loader is the report author's first point of contact with
validation, so every failure is a teaching error: a
:class:`~workflow_coda.errors.LayoutError` naming the file, the
location inside it, the problem, and the fix.  Four failure families:

* **Reading and parsing**: an unreadable file, invalid YAML syntax, or
  a document that is not a mapping.
* **Duplicate keys**: plain YAML resolves duplicate mapping keys by
  silently keeping the *last* occurrence — a copy-paste accident would
  swallow half the author's sections without an error.  The loader
  rejects duplicates, naming the key and its line.
* **Shape**: layout model violations, reformatted from pydantic's
  error list into one line per problem with a path into the file
  (``sections[0].components[0].id``).
* **YAML 1.1 boolean traps**: bare ``true``/``false``/``yes``/``no``/
  ``on``/``off`` are *booleans* in YAML, so ``title: no`` arrives as
  the value ``False``, not the word "no".  When a boolean lands in a
  text or policy field, the loader explains the quoting rule instead of
  showing pydantic's opaque "Input should be a valid string".
* **Schema version**: a layout written against an older layout
  schema (``0.1.0``) fails with the migration spelled out — the file
  format is versioned, and old files are taught forward, not parsed.

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

from .errors import LayoutError
from .layout import LAYOUT_SCHEMA_VERSION, ReportLayout

_MISSING = object()
"""Sentinel for a location that does not resolve into the parsed document."""


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
        except TypeError, KeyError, IndexError:
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
            f"(title:, sections:, ...), but it contains {found}"
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
        raise LayoutError(
            f"{path}: the layout's schema_version must be "
            f'"{LAYOUT_SCHEMA_VERSION}", but '
            f"this file declares {declared_version!r}"
        )
    try:
        return ReportLayout.model_validate(parsed)
    except ValidationError as e:
        lines = "\n".join(
            f"  - {_describe_violation(parsed, error)}" for error in e.errors()
        )
        raise LayoutError(f"{path} is not a valid report layout:\n{lines}") from e
