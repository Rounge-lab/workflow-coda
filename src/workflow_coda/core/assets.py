"""The core plugin's shipped page chrome: css and js read as real
files, at import.

The core components' stylesheets and scripts live under
``core/assets/`` — css and js where css and js belong, highlighted
by editors, editable without touching Python — and are read once at
import through ``importlib.resources``, the same door a third-party
plugin uses for its own package data.  The files carry exactly what
ships in the page: no banners (the channel stamps those), no extra
prose; the Python constants' docstrings carry the why.

A missing or unreadable asset is a broken installation, and is
taught as one — at import, where the constants read it, so a broken
install fails loudly the moment the registry loads the plugin.
"""

from importlib import resources

from ..errors import PluginAssetError

_ASSETS = resources.files("workflow_coda.core") / "assets"
"""The shipped asset directory, resolved at import — valid for
regular and editable installs alike."""


def read_core_asset(name: str) -> str:
    """One shipped asset's content: the css or js exactly as it ships
    in the page.

    Raises :class:`~workflow_coda.errors.PluginAssetError` when the
    file is missing or unreadable — a broken installation, named as
    one.
    """
    resource = _ASSETS / name
    try:
        return resource.read_text(encoding="utf-8")
    except OSError as e:
        raise PluginAssetError(
            f"the core plugin's asset {name!r} is missing or unreadable: "
            "the workflow-coda installation is broken; reinstall it "
            f"({e})"
        ) from e
