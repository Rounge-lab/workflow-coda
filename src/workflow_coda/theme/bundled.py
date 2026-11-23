"""Loading framework-owned theme assets through package resources."""

from importlib import resources

from ..errors import FrameworkAssetError
from .loader import _validate_theme_yaml
from .model import Theme


def _load_bundled_theme(name: str) -> Theme:
    """Read a trusted bundled theme name.

    The caller supplies a framework-controlled name. Author-facing
    name lookup will pass through discovery before reaching this helper.
    """
    source = f"workflow_coda.theme/assets/{name}.yaml"
    try:
        path = resources.files("workflow_coda.theme") / "assets" / f"{name}.yaml"
        text = path.read_text(encoding="utf-8")
        return _validate_theme_yaml(text, source)
    except (OSError, ValueError) as e:
        raise FrameworkAssetError(
            f"the framework theme asset {source} is unreadable or invalid: "
            f"the workflow-coda installation is broken; reinstall it ({e})"
        ) from e
