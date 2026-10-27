"""Tests for the framework's icon library: plugin-owned assets,
sanitized at load.

The validator is the boundary between the reviewed files under the
owning plugin's ``assets/icons/`` directory and every rendered
report, so its invariants are pinned hard: the embed rewrite, and —
above all — the allowlist's rejections, each teaching with the
offending file named.  A file that slips past review carrying a
script, a handler, or a reference fails here, at load time, never
inside a report.  The library's defect teachings — an unimportable
declared package, a missing icon directory, the prefix and duplicate
laws — live in the loader's own suite."""

import pytest

from workflow_coda.icons import (
    Icon,
    IconLibrary,
    IconSource,
    validate_icon_markup,
)

_NS = "http://www.w3.org/2000/svg"

_CORE_LIBRARY = IconLibrary((IconSource.for_plugin("core", "workflow_coda.core"),))
"""The real core declaration, as the builder wires it: the roster and
load pins run against the shipped set itself."""


def _svg(body: str) -> str:
    """A minimal namespaced, viewBox-carrying SVG document around *body*."""
    return f'<svg xmlns="{_NS}" viewBox="0 0 24 24">{body}</svg>'


# ---------------------------------------------------------------------------
# The shipped roster and the load path
# ---------------------------------------------------------------------------


def test_shipped_icon_names() -> None:
    # The roster is our own surface: an exact pin, so adding an icon
    # is a conscious edit here — and an unshipped package-data folder
    # (an empty set) fails loudly rather than quietly emptying
    # every icon request.
    assert _CORE_LIBRARY.names() == {
        "core-arrow-up",
        "core-arrow-down",
        "core-check",
        "core-info",
        "core-warning",
    }


@pytest.mark.parametrize("name", sorted(_CORE_LIBRARY.names()))
def test_every_shipped_icon_loads(name: str) -> None:
    assert _CORE_LIBRARY.load(name).name == name


def test_load_returns_embed_ready_markup() -> None:
    # The loader's rewrite, as properties — ET's serialization order
    # is not ours to pin.
    markup = _CORE_LIBRARY.load("core-check").markup
    assert markup.startswith("<svg ")
    assert markup.endswith("</svg>")
    assert 'viewBox="0 0 24 24"' in markup  # the file's own box rides through
    assert 'stroke="currentColor"' in markup  # color inheritance rides through
    assert 'width="1em"' in markup  # the loader's dimensions
    assert 'height="1em"' in markup
    assert 'aria-hidden="true"' in markup  # decorative by contract
    assert 'focusable="false"' in markup
    assert 'class="coda-icon"' in markup
    assert isinstance(_CORE_LIBRARY.load("core-check"), Icon)


def test_load_is_cached_per_build() -> None:
    # Knowing shift: was the process-wide cache pin, now the
    # per-build one — the library owns the build's cache; the
    # package loader underneath remains process-cached, so the
    # identity pin holds through both layers.
    assert _CORE_LIBRARY.load("core-check") is _CORE_LIBRARY.load("core-check")


def test_unknown_icon_teaches_with_the_roster() -> None:
    with pytest.raises(ValueError, match="unknown icon 'core-nope'"):
        _CORE_LIBRARY.load("core-nope")


# ---------------------------------------------------------------------------
# The sanitizer: what rides through, what is rejected
# ---------------------------------------------------------------------------


def test_smil_animation_is_allowed() -> None:
    # Animated icons are a delight, and SMIL cannot leave the SVG
    # sandbox: animate round-trips with its timing attributes.
    text = _svg(
        '<circle cx="12" cy="12" r="10"/>'
        '<animate attributeName="r" from="10" to="4" dur="1s" '
        'repeatCount="indefinite"/>'
    )
    markup = validate_icon_markup(text, "test.svg")
    assert "<animate" in markup
    assert 'repeatCount="indefinite"' in markup


def test_embed_attributes_overwrite_source_dimensions() -> None:
    # A file may carry its own width/height (allowed geometry); the
    # loader's rewrite wins — 1em, always.
    text = (
        f'<svg xmlns="{_NS}" viewBox="0 0 24 24" width="64" height="64">'
        '<path d="M0 0h4"/></svg>'
    )
    markup = validate_icon_markup(text, "test.svg")
    assert 'width="1em"' in markup
    assert 'width="64"' not in markup


def test_doctypes_and_entities_are_rejected() -> None:
    text = f'<!DOCTYPE svg><svg xmlns="{_NS}" viewBox="0 0 24 24"></svg>'
    with pytest.raises(
        ValueError, match="doctype or entity declaration is not allowed"
    ):
        validate_icon_markup(text, "test.svg")


def test_non_svg_root_is_rejected() -> None:
    with pytest.raises(ValueError, match="the root element must be an SVG"):
        validate_icon_markup('<foo xmlns="http://example.com"></foo>', "test.svg")


def test_missing_viewbox_is_rejected() -> None:
    with pytest.raises(ValueError, match="must declare a viewBox"):
        validate_icon_markup(f'<svg xmlns="{_NS}"></svg>', "test.svg")


def test_invalid_xml_is_rejected() -> None:
    with pytest.raises(ValueError, match="not valid SVG XML"):
        validate_icon_markup("not markup at all", "test.svg")


@pytest.mark.parametrize("tag", ["script", "text", "image", "use", "foreignObject"])
def test_disallowed_elements_are_rejected(tag: str) -> None:
    # Deny-by-default, with the interesting rejections each named:
    # script (injection), text (font dependence), image and use
    # (external references), foreignObject (the escape hatch).
    with pytest.raises(ValueError, match=f"element <{tag}> is not allowed"):
        validate_icon_markup(_svg(f"<{tag}></{tag}>"), "test.svg")


@pytest.mark.parametrize(
    ("name", "attribute"),
    [
        ("onload", 'onload="alert(1)"'),
        ("href", 'href="evil.svg"'),
        ("style", 'style="fill: red"'),
        ("class", 'class="custom"'),
    ],
)
def test_disallowed_attributes_are_rejected(name: str, attribute: str) -> None:
    # No event handlers, no external references, no style or class —
    # the loader owns the embed attributes.
    text = f'<svg xmlns="{_NS}" viewBox="0 0 24 24" {attribute}></svg>'
    with pytest.raises(ValueError, match=f"attribute '{name}' on <svg> is not allowed"):
        validate_icon_markup(text, "test.svg")
