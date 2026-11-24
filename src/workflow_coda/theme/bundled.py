"""Discovery and loading of framework-owned bundled themes.

Filename stems form the author-facing selection vocabulary. Discovery
indexes filenames only; each theme's contents are read and validated
when requested. Shipped-asset defects are installation failures,
whereas unknown selection names are authoring errors.
"""

import re
from importlib import resources
from typing import Final

from ..errors import FrameworkAssetError
from .loader import _validate_theme_yaml
from .model import Theme

_THEME_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9-]*$")
_ASSET_SOURCE: Final[str] = "workflow_coda.theme/assets"


def bundled_theme_names() -> frozenset[str]:
    """Discover bundled selection names without validating file contents.

    Names are lowercase kebab-case YAML filename stems. Invalid shipped
    filenames and missing or unreadable directories indicate a broken
    framework installation.
    """
    try:
        directory = resources.files("workflow_coda.theme") / "assets"
        names: set[str] = set()
        for entry in directory.iterdir():
            if not entry.name.endswith(".yaml") or not entry.is_file():
                continue
            name = entry.name.removesuffix(".yaml")
            if _THEME_NAME_PATTERN.fullmatch(name) is None:
                raise ValueError(
                    f"invalid bundled theme filename {entry.name!r}; "
                    "use lowercase kebab-case names such as "
                    "'default-dark.yaml'"
                )
            names.add(name)
        return frozenset(names)
    except (OSError, ValueError) as e:
        raise FrameworkAssetError(
            f"the framework theme directory {_ASSET_SOURCE} is missing, "
            "unreadable, or contains an invalid filename: the "
            f"workflow-coda installation is broken; reinstall it ({e})"
        ) from e


def load_bundled_theme(name: str) -> Theme:
    """Discover and load one bundled theme by selection name.

    An unknown name raises ValueError, naming the available selections
    and the custom-file alternative. Shipped read and validation defects
    raise FrameworkAssetError. Each call returns a freshly loaded theme.
    """
    names = bundled_theme_names()
    if name not in names:
        available = ", ".join(sorted(names)) or "none"
        raise ValueError(
            f"unknown bundled theme {name!r} "
            f"(available: {available}); choose a bundled name, "
            "or use a custom theme path such as 'theme.yaml' "
            "or './my-theme'"
        )
    return _load_bundled_theme(name)


def _load_bundled_theme(name: str) -> Theme:
    """Read a trusted bundled theme name.

    The caller supplies either a framework-controlled name or a name
    checked against discovery, never an unchecked author-supplied path.
    """
    source = f"{_ASSET_SOURCE}/{name}.yaml"
    try:
        path = resources.files("workflow_coda.theme") / "assets" / f"{name}.yaml"
        text = path.read_text(encoding="utf-8")
        return _validate_theme_yaml(text, source)
    except (OSError, ValueError) as e:
        raise FrameworkAssetError(
            f"the framework theme asset {source} is unreadable or invalid: "
            f"the workflow-coda installation is broken; reinstall it ({e})"
        ) from e
