"""Shared parsing and validation for theme YAML declarations."""

import yaml
from pydantic import ValidationError

from ..yaml_loader import UniqueKeySafeLoader
from .model import Theme


def _validate_theme_yaml(text: str, source: str) -> Theme:
    """Parse and validate theme text, naming its source in failures.

    Callers wrap ValueError in the appropriate authoring or
    installation error family.
    """
    try:
        parsed = yaml.load(text, Loader=UniqueKeySafeLoader)
    except yaml.YAMLError as e:
        detail = " ".join(str(e).split())
        raise ValueError(
            f"{source} is not valid YAML: {detail}; correct the theme file"
        ) from e

    if not isinstance(parsed, dict):
        found = (
            "nothing (the file is empty)"
            if parsed is None
            else f"a single {type(parsed).__name__} value"
        )
        raise ValueError(
            f"{source} must be a mapping of theme tokens, but contains "
            f"{found}; declare name, colors, and series"
        )

    try:
        return Theme.model_validate(parsed)
    except ValidationError as e:
        detail = "; ".join(f"{error['loc']}: {error['msg']}" for error in e.errors())
        raise ValueError(
            f"{source} is not a valid theme: {detail}; correct the theme settings"
        ) from e
