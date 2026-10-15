"""The framework's shipped icon assets, sanitized once at load.


Icons are *data*: reviewed SVG files under ``assets/icons/``, one
icon per file.  Filenames are namespaced by owner — ``core-arrow-up.svg``
ships with the framework's own components, and an extension adding
icons prefixes them with its own id, so icon names never collide
across packages.  The filename minus ``.svg`` is the icon's name;
components ask for icons by that full name and never hand-write SVG
markup.

The loader is the boundary between those files and every rendered
report, so it is a strict invariant checker even though the files are
our own: deny-by-default element and attribute allowlists mean an icon
copied from elsewhere — carrying ``<script>``, an ``onload`` handler,
an external reference, a doctype with entity expansion — fails at
load time with a message naming the offender, instead of shipping
silently into every report.  SMIL animation (``animate``,
``animateTransform``, ``set``) is allowed: animated icons are a
delight, and SMIL cannot leave the SVG element sandbox.

The loader rewrites the root to embed-ready form — sized ``1em``,
decorative (``aria-hidden``), not focusable, classed ``coda-icon`` —
while the file's own ``currentColor`` fills and strokes ride through,
so an icon inherits the color of the text around it.

:func:`validate_icon_markup` is deliberately public: user-provided
icons (a later context service reading SVG files next to the layout)
will sanitize through this same function, one validator for both
sources.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Final

_ICON_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9-]*$")
"""Shipped icon names: lowercase kebab-case, matching their filenames."""

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
    """The icon's kebab-case name, as passed to :func:`load_icon`."""

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


def icon_names() -> frozenset[str]:
    """The names of every shipped icon."""
    directory = resources.files("workflow_coda") / "assets" / "icons"
    return frozenset(
        entry.name[: -len(".svg")]
        for entry in directory.iterdir()
        if entry.name.endswith(".svg")
    )


@cache
def load_icon(name: str) -> Icon:
    """Load the shipped icon *name*, sanitized and embed-ready.

    Icons are read-only package data, so results are cached per
    process.  An unknown name is a teaching error listing the shipped
    icons.
    """
    if _ICON_NAME_PATTERN.fullmatch(name) is None:
        raise ValueError(
            f"icon names are lowercase kebab-case (e.g. 'core-arrow-up'), got {name!r}"
        )
    names = icon_names()
    if name not in names:
        available = ", ".join(sorted(names))
        raise ValueError(f"unknown icon {name!r} (shipped: {available})")
    path = resources.files("workflow_coda") / "assets" / "icons" / f"{name}.svg"
    text = path.read_text(encoding="utf-8")
    return Icon(
        name=name,
        markup=validate_icon_markup(text, source=f"assets/icons/{name}.svg"),
    )
