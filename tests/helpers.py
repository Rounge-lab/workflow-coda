"""Shared utilities for workflow-coda tests."""

from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError


def assert_frozen(model: BaseModel, field: str, value: object = "x") -> None:
    """Assert that mutating a frozen pydantic model raises at runtime.

    Mutation goes through ``setattr`` with a runtime attribute name, by
    necessity: direct assignment is a *static* error via the pydantic mypy
    plugin (frozen fields surface as read-only properties), while a
    constant-string ``setattr`` trips ruff's B010. A parameterized
    attribute name avoids both while exercising the same runtime guard.
    """
    with pytest.raises(ValidationError, match="frozen_instance"):
        setattr(model, field, value)


def invalid_fields(exc: ValidationError) -> set[str]:
    """Top-level field names reported by a validation error."""
    return {str(error["loc"][-1]) for error in exc.errors()}


def symlink_or_skip(target: Path, link: Path) -> None:
    """Create *link* pointing at *target*, skipping the test when the
    platform does not permit symbolic link creation (e.g. unprivileged
    Windows)."""
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symbolic link creation not permitted on this platform")
