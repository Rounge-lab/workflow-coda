"""Loading custom theme files and shared theme YAML validation.

Custom-file failures belong to the layout authoring family. Bundled
asset loading reuses the same validation boundary but wraps failures
as framework installation defects.
"""

from pathlib import Path

import yaml
from pydantic import ValidationError

from ..errors import LayoutError
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


def load_theme(path: Path | str) -> Theme:
    """Read and validate a user-provided UTF-8 theme file.

    Custom themes are human-authored layout inputs. Read, parse, and
    validation failures therefore raise LayoutError, with the file
    named and the underlying exception chained.
    """
    theme_path = Path(path)
    try:
        text = theme_path.read_text(encoding="utf-8")
    except OSError as e:
        raise LayoutError(
            f"cannot read the theme file {theme_path}: {e}; "
            "provide a readable theme file"
        ) from e
    except UnicodeDecodeError as e:
        raise LayoutError(
            f"the theme file {theme_path} is not valid UTF-8: {e}; "
            "save the theme file as UTF-8"
        ) from e

    try:
        return _validate_theme_yaml(text, source=str(theme_path))
    except ValueError as e:
        raise LayoutError(str(e)) from e
