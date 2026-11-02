"""The report build's icons: plugin-owned files, sanitized at load,
merged into one namespaced library per build.

Icons are *data*: reviewed SVG files under the owning plugin's
``assets/icons/`` directory, one icon per file.  Filenames are
namespaced by owner — ``core-arrow-up.svg`` ships with the core
plugin, a third-party plugin prefixes its icons with its own id —
and the filename minus ``.svg`` is the icon's name: the author-facing
vocabulary, addressed by the layout's ``icon`` parameter.  The
prefix is law, enforced when the build's index is assembled, so icon
names never collide across packages.

Each plugin that ships icons declares its icon package
(``icons_package`` on the plugin metadata); the report builder turns
the schema-gated plugins' declarations into one
:class:`IconLibrary` on the render context — the merged
name-to-source index plus the per-build load cache.  The library
answers icon resolution by the three-family law: an unknown name is
the author's typo (``ValueError``, listing what ships); an
unreadable, unsanitizable, or mis-named shipped icon is a plugin
defect (:class:`~workflow_coda.errors.PluginAssetError`, the
broken-installation family).

:func:`validate_icon_markup` is the boundary between those files and
every rendered report, and is deliberately public: shipped icons and
user-provided icons sanitize through the same strict
deny-by-default allowlists — an icon copied from elsewhere fails at
load time with a message naming the offender, never shipping
silently into a report.  SMIL animation (``animate``,
``animateTransform``, ``set``) is allowed: SMIL cannot leave the SVG element sandbox.
The validator rewrites the root to embed-ready form — sized ``1em``,
decorative (``aria-hidden``), not focusable, classed ``coda-icon`` —
while the file's own ``currentColor`` fills and strokes ride through,
so an icon inherits the color of the text around it.
The logo's SVG sources pass the same door
(:func:`workflow_coda.assets.embed_inline_svg`): one boundary for
every svg that reaches a page, shipped or user-authored.
"""

import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from importlib import import_module, resources
from typing import Final

from .errors import PluginAssetError

_SVG_NAMESPACE: Final[str] = "http://www.w3.org/2000/svg"
ET.register_namespace("", _SVG_NAMESPACE)

_ALLOWED_ELEMENTS: Final[frozenset[str]] = frozenset(
    {
        "svg",
        "g",
        "path",
        "circle",
        "ellipse",
        "rect",
        "line",
        "polyline",
        "polygon",
        "animate",
        "animateTransform",
        "set",
    }
)
"""Every element an icon may use.  Anything else — ``script``,
``foreignObject``, ``image``, ``use``, ``text`` — is rejected."""

_ALLOWED_ATTRIBUTES: Final[frozenset[str]] = frozenset(
    {
        # Geometry and painting.
        "d",
        "cx",
        "cy",
        "r",
        "rx",
        "ry",
        "x",
        "y",
        "x1",
        "x2",
        "y1",
        "y2",
        "width",
        "height",
        "points",
        "transform",
        "opacity",
        "fill",
        "fill-rule",
        "fill-opacity",
        "stroke",
        "stroke-width",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-dasharray",
        "stroke-dashoffset",
        "stroke-opacity",
        # The root's own declarations.
        "viewBox",
        "xmlns",
        # SMIL animation.
        "attributeName",
        "attributeType",
        "begin",
        "dur",
        "end",
        "from",
        "to",
        "by",
        "values",
        "keyTimes",
        "keySplines",
        "calcMode",
        "repeatCount",
        "repeatDur",
        "additive",
        "accumulate",
        "restart",
        "type",
    }
)
"""Every attribute an icon may carry.  No ``on*`` handlers, no
``href``/``xlink:href`` references, no ``style`` or ``class`` — the
loader owns the embed attributes."""


@dataclass(frozen=True, slots=True)
class Icon:
    """One sanitized, embed-ready icon."""

    name: str
    """The icon's name, as passed to :meth:`IconLibrary.load`."""

    markup: str
    """The icon as an HTML-embeddable ``<svg>`` element: sized 1em,
    decorative, classed ``coda-icon``, colors inherited."""


def _local(tag: str) -> str:
    """A tag or attribute name with any XML namespace stripped."""
    return tag.rsplit("}", 1)[-1]


def validate_icon_markup(text: str, source: str) -> str:
    """Sanitize SVG *text* into embed-ready markup, or teach.

    *source* names where the text came from (a shipped asset path or a
    user file path) so the teaching errors point at the right file.
    Returns the markup with the embed attributes applied; raises
    ``ValueError`` on every allowlist violation.
    """
    lowered = text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise ValueError(
            f"{source}: icons must be plain SVG markup — a doctype or "
            "entity declaration is not allowed"
        )
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError(f"{source}: not valid SVG XML: {e}") from e
    if root.tag != f"{{{_SVG_NAMESPACE}}}svg":
        raise ValueError(
            f"{source}: the root element must be an SVG <svg>, got {root.tag!r}"
        )
    if "viewBox" not in root.attrib:
        raise ValueError(
            f"{source}: the <svg> root must declare a viewBox so the "
            'icon scales — add viewBox="0 0 24 24" or the icon\'s own box'
        )
    for element in root.iter():
        tag = _local(element.tag)
        if tag not in _ALLOWED_ELEMENTS:
            raise ValueError(
                f"{source}: element <{tag}> is not allowed in an icon — "
                "icons may contain only shapes, groups, and SMIL animation"
            )
        for attribute in element.attrib:
            if _local(attribute) not in _ALLOWED_ATTRIBUTES:
                raise ValueError(
                    f"{source}: attribute {attribute!r} on <{tag}> is "
                    "not allowed in an icon — the allowlist is shapes, "
                    "painting, and animation only"
                )
    root.set("width", "1em")
    root.set("height", "1em")
    root.set("aria-hidden", "true")
    root.set("focusable", "false")
    root.set("class", "coda-icon")
    return ET.tostring(root, encoding="unicode")


@dataclass(frozen=True, slots=True)
class IconSource:
    """One contributor's icons, as reachable package data.

    A plugin's shipped icons live under ``<package>/assets/icons/``,
    one SVG per file; the file's name minus ``.svg`` is the icon's
    author-facing name.  ``source_label`` names this root in teaching
    messages, so a defect points at the right contributor.
    """

    package: str
    prefix: str
    source_label: str

    @classmethod
    def for_plugin(cls, plugin_id: str, icons_package: str) -> IconSource:
        """Build a source for a plugin's declared icon package.

        The prefix law derives from the plugin's id: every icon file
        in the package must be named ``<plugin_id>-<name>.svg``.  The
        package must be importable — an unimportable declaration is a
        broken installation, taught with the fix.  Package *names*
        are not checked against the plugin id: the two namespaces are
        unrelated (core's id is ``core``, its package
        ``workflow_coda.core``), and ownership is enforced by the
        prefix law, where it is checkable — on the icon files.
        """
        try:
            import_module(icons_package)
        except ModuleNotFoundError as e:
            raise PluginAssetError(
                f"plugin {plugin_id!r} declares icons_package "
                f"{icons_package!r}, but the package is not "
                "importable: the plugin installation is broken; "
                "reinstall the plugin"
            ) from e
        return cls(
            package=icons_package,
            prefix=f"{plugin_id}-",
            source_label=f"{icons_package}/assets/icons",
        )


@cache
def _load_from_package(package: str, name: str, source_label: str) -> Icon:
    """Read and sanitize one shipped icon from *package*.

    The broken-installation family for icons lives here: an
    unreadable file and an allowlist violation both wrap as
    :class:`~workflow_coda.errors.PluginAssetError`, cause chained —
    a shipped icon that fails its own validator is a plugin defect,
    not an authoring error.
    """
    try:
        path = resources.files(package) / "assets" / "icons" / f"{name}.svg"
        text = path.read_text(encoding="utf-8")
        markup = validate_icon_markup(text, source=f"{source_label}/{name}.svg")
    except (ValueError, OSError) as e:
        raise PluginAssetError(
            f"the plugin asset {source_label}/{name}.svg is unreadable "
            "or fails icon validation: the plugin installation is "
            f"broken; reinstall it ({e})"
        ) from e
    return Icon(name=name, markup=markup)


class IconLibrary:
    """The report build's merged icon namespace: every schema-gated
    plugin's declared icons, indexed once per build, sanitized and
    cached at first use.

    The family split, extended to icons: an unknown name is the
    author's typo (``ValueError``, the layout family); a shipped icon
    that is unreadable, unsanitizable, or mis-named is a plugin
    defect (:class:`~workflow_coda.errors.PluginAssetError`, the
    broken-installation family).
    """

    def __init__(self, sources: Iterable[IconSource]) -> None:
        """Build the merged name-to-source index, enforcing the two
        index-time laws: every icon carries its plugin's prefix, and
        no two plugins declare one name."""
        self._sources: dict[str, IconSource] = {}
        for source in sources:
            directory = resources.files(source.package) / "assets" / "icons"
            try:
                entries = list(directory.iterdir())
            except OSError as e:
                raise PluginAssetError(
                    f"the plugin icon directory {source.source_label} is "
                    "missing or unreadable: the plugin installation is "
                    f"broken; reinstall the plugin ({e})"
                ) from e
            for entry in entries:
                if not entry.name.endswith(".svg"):
                    continue
                name = entry.name[: -len(".svg")]
                if not name.startswith(source.prefix):
                    raise PluginAssetError(
                        f"icon {name!r} in {source.source_label} does not "
                        f"carry its plugin's prefix ({source.prefix!r}) — "
                        "icon names are <plugin_id>-<name>, one global "
                        "namespace shared by every installed plugin"
                    )
                if name in self._sources:
                    first = self._sources[name]
                    raise PluginAssetError(
                        f"two plugins declare the icon {name!r}: "
                        f"{first.source_label} and {source.source_label} — "
                        "icon names are one global namespace; prefix "
                        "every icon with its plugin's id"
                    )
                self._sources[name] = source
        self._cache: dict[str, Icon] = {}

    def names(self) -> frozenset[str]:
        """Every icon every contributing plugin ships, by name."""
        return frozenset(self._sources)

    def load(self, name: str) -> Icon:
        """One icon, sanitized at first use, cached for the build.

        An unknown name teaches as the author's typo, listing what
        the installed plugins ship; read and sanitization failures
        teach as the broken-installation family, from the package
        loader.
        """
        cached = self._cache.get(name)
        if cached is not None:
            return cached
        source = self._sources.get(name)
        if source is None:
            if self._sources:
                available = ", ".join(sorted(self._sources))
                detail = f"installed plugins ship: {available}"
            else:
                detail = "no installed plugin ships icons"
            raise ValueError(f"unknown icon {name!r} ({detail})")
        icon = _load_from_package(source.package, name, source.source_label)
        self._cache[name] = icon
        return icon
