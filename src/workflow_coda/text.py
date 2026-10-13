"""Shared text rules for the framework's contracts.

A dependency-free leaf module: the rules here are used across the
package — by the component contracts' in-memory gates, by the layout
model's visible-text validator, and by the theme's font rules — so
they live in a module that imports nothing from the package and can
be imported from anywhere without creating import cycles.
"""


def has_visible_text(text: str) -> bool:
    """Whether *text* contains at least one non-whitespace character.

    The shared predicate of the authoring-time strict-text rule: a
    whitespace-only value is always an authoring mistake, whether it
    lands in a plugin contract constructed in Python, a layout file
    deserialized from YAML, or a theme's font tokens.  Each contract
    applies it with its own contextual message.
    """
    return bool(text.strip())
