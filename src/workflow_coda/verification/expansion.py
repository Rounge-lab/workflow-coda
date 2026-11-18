"""The spec's ``for_each`` expansion language: template, slug,
collision.

A spec block may declare one dimension — ``batch``, ``sample_id``
— and every string leaf in the block may then carry the
placeholder ``{dimension}``.  The language is tiny by design, and
its laws are the framework's own, restated small:

* **The placeholder grammar is exclusive.**  A ``{`` in a
  templated string must open exactly the block's own
  ``{dimension}``: a malformed placeholder, or one naming anything
  else, is a spec-authoring teaching.  A ``}`` alone is a literal
  — only ``{`` opens the language, so the disk's brace-bearing
  names stay legal.
* **Raw is the truth on the disk side; the slug is the address.**
  Raw values substitute into file templates and criteria leaves —
  the disk's names are the data.  Ids and types are addresses,
  never display names: ``sanitize: true`` (default off — silent
  lowercasing is the dishonest fix) substitutes the slug there
  instead, and a grammar-failing raw teaches per value with
  ``sanitize: true`` named as the fix.
* **Collisions collect.**  Two values of one family expanding to
  the same id or type refuse the spec load together, every raw
  named — the loader's collect-and-list law.

The module is pure: it knows templates and values, not sources.
The three value sources — ``values``, ``samplesheet``, ``glob`` —
are wired into
:func:`workflow_coda.verification.load_verify_spec`.  Every
teaching here raises
:class:`~workflow_coda.errors.SpecError` with the spec's path for
context, the family's shape, and the identity grammars are checked
through the manifest's own constrained types — one source of
truth, never a re-derived pattern that could drift from the real
one.

The language has a second consumer: the report side's ``states``
composition node expands its children's free strings once per
axis value through these same laws.  One grammar, one teaching
family, two call shapes — the spec passes its block's single
dimension, and the report builder passes the stack of states
dimensions in scope.
"""

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter, ValidationError

from ..errors import SpecError
from ..manifest import ArtifactId, ArtifactType, JsonValue
from ..text import DIMENSION_NAME_RE

_PLACEHOLDER = re.compile(r"\{(" + DIMENSION_NAME_RE.pattern + r")\}")
"""One well-formed placeholder: ``{name}`` in the dimension name
grammar — lowercase, the id grammar's own character class.
Derived from :data:`workflow_coda.text.DIMENSION_NAME_RE`, so the
placeholder language and the report side's ``states`` dimensions
are one grammar in one home and can never drift apart."""

_ID_CHECK: TypeAdapter[ArtifactId] = TypeAdapter(ArtifactId)
_TYPE_CHECK: TypeAdapter[ArtifactType] = TypeAdapter(ArtifactType)
"""The id and type grammars, checked through their one source of
truth: the manifest's constrained types themselves."""


def expand_template(
    text: str,
    *,
    dimension: str,
    raw: str,
    path: Path,
    scope: Sequence[str] | None = None,
) -> str:
    """Substitute *raw* — the disk's truth — for every
    ``{dimension}`` in *text*.

    *scope* is the dimensions bound at this point of the walk; the
    default ``(dimension,)`` is the spec block's single-dimension
    world, so every existing call keeps its behavior.  The report
    builder passes the stack of states dimensions in scope: a
    placeholder naming another bound dimension passes through
    untouched — its owning node's round substitutes it — and a
    placeholder naming nothing in scope teaches.

    A ``{`` that does not open exactly the block's own dimension
    is taught here: a malformed placeholder, or one naming another
    token.  A ``}`` alone rides as a literal: only ``{`` opens the
    language.
    """
    bound = tuple(scope) if scope is not None else (dimension,)
    out: list[str] = []
    i = 0
    while (j := text.find("{", i)) != -1:
        match = _PLACEHOLDER.match(text, j)
        if match is None:
            raise SpecError(
                f"{path}: the template {text!r} carries a malformed "
                "placeholder — '{' must open the block's own "
                f"'{{{dimension}}}', e.g. 'qc/{{{dimension}}}.json'"
            )
        name = match.group(1)
        if name != dimension:
            if name in bound:
                # another bound dimension's placeholder passes
                # through — its owning node's round substitutes it
                out.append(text[i:j])
                out.append(match.group(0))
                i = match.end()
                continue
            raise SpecError(
                f"{path}: the template {text!r} names the placeholder "
                f"{{{name}}}, but the block's dimension is {dimension!r} "
                "— a placeholder names its dimension (a typo, most "
                "likely), and only the dimension substitutes"
            )
        out.append(text[i:j])
        out.append(raw)
        i = match.end()
    out.append(text[i:])
    return "".join(out)


def require_no_placeholders(text: str, *, path: Path) -> None:
    """Refuse a placeholder with no dimension in scope.

    Outside a ``for_each`` block the placeholder cannot mean
    anything, so it teaches rather than riding as a literal — the
    author almost certainly meant a loop.  The fix is named either
    way: declare the ``for_each``, or write the literal name.
    """
    j = text.find("{")
    if j == -1:
        return
    match = _PLACEHOLDER.match(text, j)
    if match is None:
        raise SpecError(
            f"{path}: the string {text!r} carries a malformed "
            "placeholder — '{' opens '{{<dimension>}}' only inside a "
            "for_each block; write the literal name instead"
        )
    raise SpecError(
        f"{path}: the string {text!r} carries the placeholder "
        f"{{{match.group(1)}}}, but this block declares no for_each — "
        "a placeholder needs its dimension in scope; declare the "
        "for_each, or write the literal name"
    )


def slugify(raw: str, *, dimension: str, path: Path) -> str:
    """The address-safe form of one raw value.

    Lowercase; every run of characters outside ``[a-z0-9_-]``
    becomes one ``-``; edge hyphens strip; a result not starting
    with a lowercase letter gains the ``s-`` prefix — a digit
    start, an underscore start, one rule and not two special
    cases; and a value that slugs to nothing has no address at
    all, which teaches: no coercion can invent an address, so the
    fix is the data's, not the option's.
    """
    folded = re.sub(r"[^a-z0-9_-]+", "-", raw.lower()).strip("-")
    if not folded:
        raise SpecError(
            f"{path}: the value {raw!r} for dimension {dimension!r} "
            "has no address-safe form — every character maps away in "
            "the slug; ids and types are addresses, never display "
            "names, so rename the value in its source (the values "
            "list or the samplesheet)"
        )
    if not ("a" <= folded[0] <= "z"):
        folded = f"s-{folded}"
    return folded


def substitute_raw(
    value: JsonValue, *, dimension: str, raw: str, path: Path
) -> JsonValue:
    """The raw substitution over one criteria value, any JSON
    shape.

    Strings substitute through :func:`expand_template`; lists and
    mappings recurse in order, mapping keys included — one law for
    every string leaf, no field whitelist — and the other leaves
    (numbers, booleans, null) ride untouched.
    """
    if isinstance(value, str):
        return expand_template(value, dimension=dimension, raw=raw, path=path)
    if isinstance(value, list):
        return [
            substitute_raw(item, dimension=dimension, raw=raw, path=path)
            for item in value
        ]
    if isinstance(value, dict):
        return {
            expand_template(key, dimension=dimension, raw=raw, path=path): (
                substitute_raw(item, dimension=dimension, raw=raw, path=path)
            )
            for key, item in value.items()
        }
    return value


def identity_value(
    raw: str,
    *,
    kind: Literal["id", "type"],
    sanitize: bool,
    dimension: str,
    path: Path,
) -> str:
    """The value an ``id:`` or ``type:`` template takes for one
    raw.

    With ``sanitize: false`` the raw itself must fit the field's
    grammar; a misfit teaches per value with ``sanitize: true``
    named as the fix, the computed slug shown so the offer is
    concrete.  With ``sanitize: true`` the slug substitutes — and
    by construction it always fits the id grammar; the one thing it
    cannot supply a type is the namespace dot, so a dotless type
    after substitution teaches with the leaf-only pattern shown.
    """
    candidate = slugify(raw, dimension=dimension, path=path) if sanitize else raw
    check = _ID_CHECK if kind == "id" else _TYPE_CHECK
    try:
        check.validate_python(candidate)
    except ValidationError:
        if sanitize:
            raise SpecError(
                f"{path}: the slug {candidate!r} of the value {raw!r} "
                f"for dimension {dimension!r} does not fit the type "
                "grammar — a type is namespaced, at least two "
                "dot-separated segments (e.g. org.example.samples); "
                f"template only the type's leaf, e.g. 'org.example.qc-{{{dimension}}}'"
            ) from None
        slug = slugify(raw, dimension=dimension, path=path)
        raise SpecError(
            f"{path}: the value {raw!r} for dimension {dimension!r} "
            f"does not fit the artifact {kind} grammar — ids and types "
            "are addresses, never display names; pass 'sanitize: true' "
            f"to use its slug ({slug!r}), or fix the value in its source"
        ) from None
    return candidate


def check_family_collisions(
    identities: Sequence[tuple[str, str]],
    *,
    kind: Literal["id", "type"],
    dimension: str,
    path: Path,
) -> None:
    """Refuse a family whose values expand to one address twice.

    Two raws — two spellings, or one value appearing twice — that
    produce the same id or type leave the address ambiguous, and
    ambiguity is refused at spec load, before a single artifact is
    verified: every collision is listed, every raw named — the
    loader's collect-and-list law.  The check is within-family,
    one ``for_each`` block's own values; across blocks, the
    placement's teachings stand exactly as today.
    """
    groups: dict[str, list[str]] = {}
    for raw, identity in identities:
        groups.setdefault(identity, []).append(raw)
    problems = [
        f"  - the {kind} {identity!r}: the values "
        + ", ".join(repr(value) for value in raws)
        for identity, raws in groups.items()
        if len(raws) > 1
    ]
    if problems:
        lines = "\n".join(problems)
        raise SpecError(
            f"{path}: the for_each dimension {dimension!r} expands to "
            f"colliding artifact {kind}s — one address cannot serve "
            f"two values:\n{lines}"
        )
