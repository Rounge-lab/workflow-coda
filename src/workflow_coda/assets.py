"""Report asset embedding: declared, then strict.

The layout may declare a ``logo`` and a ``favicon`` — paths, relative
to the layout file, of images to embed into the single-page report as
data URIs.  Both follow the declared-then-strict rule: omitted, the
report renders without the asset and the builder records an
informational diagnostic; declared, the file must exist next to the
layout file, carry a supported image extension, and actually contain
the image type its extension claims — anything else fails the build
with a :class:`~workflow_coda.errors.LayoutError` naming the asset and
the fix.

Embedding (rather than linking) is what keeps the report one
self-contained HTML file: the report reader's machine never has to
resolve a path that only the build machine knew.
"""

import base64
from collections.abc import Callable
from pathlib import Path

from .errors import LayoutError
from .report import EmbeddedAsset


def _is_png(data: bytes) -> bool:
    return data.startswith(b"\x89PNG\r\n\x1a\n")


def _is_jpeg(data: bytes) -> bool:
    return data.startswith(b"\xff\xd8\xff")


def _is_gif(data: bytes) -> bool:
    return data[:6] in (b"GIF87a", b"GIF89a")


def _is_ico(data: bytes) -> bool:
    return data[:4] == b"\x00\x00\x01\x00"


def _is_webp(data: bytes) -> bool:
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def _is_svg(data: bytes) -> bool:
    head = data[:512].lstrip()
    return head.startswith(b"<") and b"svg" in head.lower()


_MEDIA_CHECKS: dict[str, tuple[str, Callable[[bytes], bool]]] = {
    ".png": ("image/png", _is_png),
    ".jpg": ("image/jpeg", _is_jpeg),
    ".jpeg": ("image/jpeg", _is_jpeg),
    ".gif": ("image/gif", _is_gif),
    ".svg": ("image/svg+xml", _is_svg),
    ".ico": ("image/x-icon", _is_ico),
    ".webp": ("image/webp", _is_webp),
}
"""Extension → (media type, signature check).  The check is the
"actually is that image type" half of declared-then-strict."""

SUPPORTED_ASSET_EXTENSIONS: tuple[str, ...] = tuple(sorted(_MEDIA_CHECKS))
"""The image extensions the builder will embed."""


def embed_asset(layout_path: Path, declared: str, role: str) -> EmbeddedAsset:
    """Read and embed the asset declared in the layout.

    *role* is the layout field name (``"logo"`` / ``"favicon"``), used
    in teaching errors.  Raises
    :class:`~workflow_coda.errors.LayoutError` when the file cannot be
    read, has an unsupported extension, or fails its image signature
    check.
    """
    path = layout_path.parent / declared
    try:
        data = path.read_bytes()
    except OSError as e:
        raise LayoutError(
            f"cannot read the declared {role} {declared!r} at {path}: "
            f"{e.strerror or e} — place the file next to the layout "
            f"({layout_path.name!r}) or correct the path"
        ) from e
    entry = _MEDIA_CHECKS.get(path.suffix.lower())
    if entry is None:
        raise LayoutError(
            f"the declared {role} {declared!r} has the extension "
            f"{path.suffix.lower()!r}, which is not a supported image "
            f"type — supported: {', '.join(SUPPORTED_ASSET_EXTENSIONS)}"
        )
    media_type, check = entry
    if not check(data):
        raise LayoutError(
            f"the declared {role} {declared!r} does not look like a valid "
            f"{media_type} file — check that the image matches its "
            f"extension"
        )
    data_uri = f"data:{media_type};base64," + base64.b64encode(data).decode("ascii")
    return EmbeddedAsset(path=declared, media_type=media_type, data_uri=data_uri)
