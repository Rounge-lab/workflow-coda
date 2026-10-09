"""Shared utilities for workflow-coda tests."""

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
