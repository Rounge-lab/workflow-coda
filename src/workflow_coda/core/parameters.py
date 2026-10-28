"""Shared parameter-grammar helpers for the core components.

The parse half of the honest-data law, factored out of the three
components: every core component parses its placement parameters
with the same shape vocabulary — required and optional text,
closed vocabularies, booleans, the tabular ``sep`` — and every
shape error is one teaching ``ValueError`` naming the component,
the parameter, and the fix, raised before any data is touched.

Theme-free by construction: this module imports nothing from the
theme, the store, or the icon library, so a component's parse half
stays pure by where it lives — the same seam every component
honors inside itself, held at module level here.  The component id
rides as the first argument, the
:func:`~workflow_coda.components.reject_unknown_parameters`
precedent: the id lives in every teaching, and the helpers carry
no state of their own.

Underscore-private to the core package today, shared the way
``table`` shares its tabular grammar with ``chart``.  Promotion
beside ``reject_unknown_parameters`` — public, documented, pinned
by contract tests, and available to third-party plugins — is a
deliberate future step, recorded in the skills files, not
smuggled: the grammar can still grow, and a private module grows
without breaking anyone.
"""

from ..components import ComponentParameters


def _required_text(
    component_id: str, parameters: ComponentParameters, name: str
) -> str:
    """A required string parameter, or a teaching ``ValueError``."""
    if name not in parameters:
        raise ValueError(f"{component_id}: parameter {name!r} is required")
    value = parameters[name]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{component_id}: parameter {name!r} must be a non-empty "
            f"string, got {value!r}"
        )
    return value


def _optional_text(
    component_id: str, parameters: ComponentParameters, name: str
) -> str | None:
    """An optional string parameter, absent by default."""
    if name not in parameters:
        return None
    value = parameters[name]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{component_id}: parameter {name!r}, when given, must be a "
            f"non-empty string, got {value!r}"
        )
    return value


def _required_one_of(
    component_id: str,
    parameters: ComponentParameters,
    name: str,
    allowed: frozenset[str],
) -> str:
    """A required closed-vocabulary string parameter — no default to
    guess wrong: the placement names its choice, and a value outside
    the vocabulary teaches with the whole vocabulary listed."""
    value = _required_text(component_id, parameters, name)
    if value not in allowed:
        choices = ", ".join(f"'{item}'" for item in sorted(allowed))
        raise ValueError(
            f"{component_id}: parameter {name!r} must be one of "
            f"{choices}; got {value!r}"
        )
    return value


def _optional_one_of(
    component_id: str,
    parameters: ComponentParameters,
    name: str,
    allowed: frozenset[str],
    *,
    default: str,
) -> str:
    """A closed-vocabulary string parameter with a default."""
    if name not in parameters:
        return default
    value = parameters[name]
    if not isinstance(value, str) or value not in allowed:
        choices = ", ".join(f"'{item}'" for item in sorted(allowed))
        raise ValueError(
            f"{component_id}: parameter {name!r}, when given, must be one "
            f"of {choices}; got {value!r}"
        )
    return value


def _optional_bool(
    component_id: str,
    parameters: ComponentParameters,
    name: str,
    *,
    default: bool,
) -> bool:
    """An optional boolean parameter; the caller states the default,
    so each component's grammar owns its own truth — ``header``'s
    true, ``log_x``'s false."""
    if name not in parameters:
        return default
    value = parameters[name]
    if not isinstance(value, bool):
        raise ValueError(
            f"{component_id}: parameter {name!r}, when given, must be a "
            f"boolean, got {value!r}"
        )
    return value


def _sep_from(component_id: str, parameters: ComponentParameters) -> str:
    """The tabular field delimiter: one character, default the tab."""
    if "sep" not in parameters:
        return "\t"
    value = parameters["sep"]
    if not isinstance(value, str) or len(value) != 1:
        raise ValueError(
            f"{component_id}: parameter 'sep', when given, must be a "
            f"single character, got {value!r}"
        )
    return value
