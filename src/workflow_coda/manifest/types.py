"""Reusable constrained types shared by manifest models.

These PEP 695 type aliases are part of the public API: plugin authors are
expected to reuse them when defining artifact schemas or when validating
values outside pydantic models. The string aliases are strict — pydantic
will not coerce other types into these strings; :data:`JsonValue` is the
structural union a JSON document parses into, the transport type behind
component parameters, layout parameters, and verification records.
"""

from typing import Annotated

from pydantic import StringConstraints

# Machine-readable identifier, unique within a manifest (e.g. "sample_metrics").
type ArtifactId = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_-]*$"),
]

# Dotted, lowercase, namespaced name shared by artifact types and plugin
# artifact formats: at least two dot-separated segments (namespace, then
# name; further segments allowed), lowercase snake_case within each.
_DOTTED_NAME_PATTERN = r"^[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)+$"

# Namespaced artifact type (e.g. "org.example.sample_metrics"). Requires
# at least two dot-separated segments, per the artifact contract.
type ArtifactType = Annotated[
    str,
    StringConstraints(strict=True, pattern=_DOTTED_NAME_PATTERN),
]

# A plugin-defined artifact format: a namespaced convention, dotted like
# an artifact type (e.g. "core.table", "bio.newick").  The prefix is the
# owning plugin's id, by convention: the format's grammar lives in the
# plugin, which reads its artifacts through the store's byte- and
# text-level readers — the framework never dispatches on the name.
type NamespacedArtifactFormat = Annotated[
    str,
    StringConstraints(strict=True, pattern=_DOTTED_NAME_PATTERN),
]

# Version string of a manifest or artifact content schema, e.g. "1.0".
type ArtifactSchemaVersion = Annotated[
    str, StringConstraints(strict=True, min_length=1)
]

# Path of an artifact relative to the manifest that declares it.
type ManifestRelativePath = Annotated[
    str,
    StringConstraints(strict=True, min_length=1),
]

# Any non-empty, strict string: human-readable names, versions, labels, titles.
type NonEmptyStr = Annotated[str, StringConstraints(strict=True, min_length=1)]

# Lowercase hexadecimal SHA-256 digest, e.g. hashlib's hexdigest() output.
type Sha256Hex = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$"),
]

# A fully typed JSON value: the structural union json.loads returns and
# json.dumps accepts.  The transport type behind component parameters,
# layout parameters, and the artifact verification record, it lives in
# this leaf module so the manifest package can use it without importing
# the artifact store (that direction is a cycle); the store keeps the
# name importable from its own module, its historical home.
type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)
