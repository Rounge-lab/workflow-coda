"""Shared YAML machinery for human-authored framework inputs.

Duplicate mapping keys are rejected rather than silently resolved
using YAML's last-wins behavior. Callers own model validation and
wrap parsing failures in their appropriate framework error family.
"""

from typing import Any

import yaml
from yaml.constructor import ConstructorError


class _DuplicateKeyError(yaml.YAMLError):
    """Internal: a duplicate mapping key, with its 1-based line number."""

    def __init__(self, key: object, line: int) -> None:
        super().__init__(f"duplicate key {key!r} on line {line}")
        self.key = key
        self.line = line


class UniqueKeySafeLoader(yaml.SafeLoader):
    """``SafeLoader`` that rejects duplicate mapping keys.

    YAML's silent last-wins resolution is a trap for a hand-authored
    file, so a duplicate becomes an error naming the key and line.
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
