"""Shared text rules for the framework's contracts.

A dependency-free leaf module: the rules here are used across the
package — by the component contracts' in-memory gates, by the layout
model's visible-text validator, by the theme's font rules, by the
verify sources' glob ordering, and by the layout's states dimension
names — so they live in a module that imports nothing from the
package and can be imported from anywhere without creating import
cycles.
"""

import re

_DIGIT_RUN = re.compile(r"(\d+)")
"""One maximal digit run — the capture in the natural key."""

DIMENSION_NAME_RE = re.compile(r"[a-z][a-z0-9_-]*")
"""The dimension-name grammar: a states node's dimension is its
children's placeholder name — lowercase snake_case starting with a
letter (``batch``, ``sample_id``), the same grammar the spec's
placeholder language captures."""


def has_visible_text(text: str) -> bool:
    """Whether *text* contains at least one non-whitespace character.

    The shared predicate of the authoring-time strict-text rule: a
    whitespace-only value is always an authoring mistake, whether it
    lands in a plugin contract constructed in Python, a layout file
    deserialized from YAML, or a theme's font tokens.  Each contract
    applies it with its own contextual message.
    """
    return bool(text.strip())


def natural_key(text: str) -> tuple[tuple[int, str | int], ...]:
    """The natural sort key: digit runs compare as numbers.

    ``s2`` sorts before ``s10`` — the digits split the text into
    alternating text and number parts, compared pairwise: text
    parts as codepoints (case-sensitive — determinism over
    locale-flavored niceness), digit parts as integers.  Each part
    is tagged — ``(0, text)`` sorts before ``(1, number)`` at the
    same position — so a text part never compares against a number.
    Distinct spellings such as "s1" and "s01" can have equal keys;
    callers needing deterministic tie ordering must also compare
    the original spelling. This is the framework's ordering law
    for values with no story of their own: a values list and a
    samplesheet carry the producer's order, and only the disk
    needs a key — deterministic, or it is an accident.
    """
    parts = _DIGIT_RUN.split(text)
    key: list[tuple[int, str | int]] = []
    for index, part in enumerate(parts):
        if index % 2:
            key.append((1, int(part)))
        elif part:
            key.append((0, part))
    return tuple(key)
