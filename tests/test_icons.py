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

from collections.abc import Mapping
from pathlib import Path

import pytest

from workflow_coda.errors import PluginAssetError
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
        "core-arrow-down",
        "core-arrow-up",
        "core-ascending",
        "core-check",
        "core-coda",
        "core-copy",
        "core-descending",
        "core-dropdown",
        "core-filter",
        "core-info",
        "core-table",
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
    assert 'fill="currentColor"' in markup  # color inheritance rides through
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


def _icon_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    package: str,
    files: Mapping[str, str | None],
) -> None:
    """A real, importable fixture package shipping icons, so every
    fixture exercises the import probe and the directory listing —
    not a hand-built source.  *files* maps icon filename to SVG
    content; ``None`` writes an empty file, for the index-time laws,
    which read names only.  Unique package names per test keep
    ``sys.modules`` clean; monkeypatch removes the path after."""
    icons = tmp_path / package / "assets" / "icons"
    icons.mkdir(parents=True)
    (tmp_path / package / "__init__.py").write_text("", encoding="utf-8")
    for name, content in files.items():
        if content is None:
            (icons / name).touch()
        else:
            (icons / name).write_text(content, encoding="utf-8")
    monkeypatch.syspath_prepend(tmp_path)


# ---------------------------------------------------------------------------
# The library: namespace laws and the defect families
# ---------------------------------------------------------------------------


def test_a_declared_package_must_be_importable() -> None:
    # The declaration is a claim: an icon package that is not
    # importable is a broken installation, taught at index build
    # with the fix — and the ModuleNotFoundError chained as the
    # cause, so what actually broke survives into the error.
    with pytest.raises(
        PluginAssetError, match="but the package is not importable"
    ) as exc_info:
        IconSource.for_plugin("bio", "iconfix_absent_package")
    assert isinstance(exc_info.value.__cause__, ModuleNotFoundError)


def test_a_missing_icon_directory_is_a_broken_installation() -> None:
    # The framework's own package is the natural fixture: after the
    # move it genuinely ships no assets/icons/ directory — icons live
    # with their owning plugins now.  A declared source whose
    # directory is missing is an installation defect, taught with
    # the source label and the fix; the exact OSError flavor is the
    # platform's, so only its family is pinned.
    source = IconSource.for_plugin("broken", "workflow_coda")
    with pytest.raises(PluginAssetError, match="is missing or unreadable") as exc_info:
        IconLibrary((source,))
    assert isinstance(exc_info.value.__cause__, OSError)


def test_icon_files_carry_their_plugins_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The prefix is law, enforced at index build on the file itself:
    # a mis-named icon never reaches a report.  The empty file is
    # deliberate — index-time laws read names, never contents.
    _icon_package(tmp_path, monkeypatch, "iconfix_prefix", {"oops.svg": None})
    source = IconSource.for_plugin("iconfx", "iconfix_prefix")
    with pytest.raises(PluginAssetError, match="does not carry its plugin's prefix"):
        IconLibrary((source,))


def test_two_plugins_cannot_declare_one_icon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The prefix law alone cannot prevent this collision — the design
    # pin this test holds: when one plugin id is a hyphen-prefix of
    # another ('fake' and 'fake-two'), one filename satisfies both
    # prefixes, which is exactly why the library re-checks while
    # building the index, the same defense the registry runs for
    # component ids.
    _icon_package(tmp_path, monkeypatch, "iconfix_dupe_a", {"fake-two-dupe.svg": None})
    _icon_package(tmp_path, monkeypatch, "iconfix_dupe_b", {"fake-two-dupe.svg": None})
    with pytest.raises(PluginAssetError, match="two plugins declare the icon"):
        IconLibrary(
            (
                IconSource.for_plugin("fake", "iconfix_dupe_a"),
                IconSource.for_plugin("fake-two", "iconfix_dupe_b"),
            )
        )


def test_a_corrupt_icon_teaches_at_load_not_at_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Lazy by decision, pinned: the index reads names only, so a
    # corrupt shipped icon harms nothing until addressed — and then
    # it is the broken-installation family, the validator's own
    # teaching wrapped, with the ValueError chained as the cause.
    evil = _svg("<script>alert(1)</script>")
    _icon_package(tmp_path, monkeypatch, "iconfix_evil", {"iconfx-evil.svg": evil})
    library = IconLibrary((IconSource.for_plugin("iconfx", "iconfix_evil"),))
    assert library.names() == frozenset({"iconfx-evil"})  # the index built anyway
    with pytest.raises(PluginAssetError, match="fails icon validation") as exc_info:
        library.load("iconfx-evil")
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_an_unreadable_icon_file_teaches_at_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The OSError half of the wrap: a directory named like an icon
    # lists in the index (it ends in .svg) but cannot be read — the
    # read failure joins the same broken-installation family, and
    # only the OSError family is pinned, not the platform's flavor.
    _icon_package(tmp_path, monkeypatch, "iconfix_unread", {})
    (tmp_path / "iconfix_unread" / "assets" / "icons" / "iconfx-dir.svg").mkdir()
    library = IconLibrary((IconSource.for_plugin("iconfx", "iconfix_unread"),))
    with pytest.raises(
        PluginAssetError, match="unreadable or fails icon validation"
    ) as exc_info:
        library.load("iconfx-dir")
    assert isinstance(exc_info.value.__cause__, OSError)


def test_snake_case_plugin_ids_can_ship_icons(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The name grammar is the filenames plus the prefix law — the
    # old kebab-case pattern died so plugin ids like 'my_plugin'
    # could ship icons; this is that legality, pinned end to end:
    # import probe, index, lazy load, and the embed rewrite.
    leaf = _svg('<path d="M12 3l4 6h-8z"/>')
    _icon_package(tmp_path, monkeypatch, "iconfix_snake", {"my_plugin-leaf.svg": leaf})
    library = IconLibrary((IconSource.for_plugin("my_plugin", "iconfix_snake"),))
    icon = library.load("my_plugin-leaf")
    assert 'class="coda-icon"' in icon.markup  # sanitized and embed-ready


def test_an_empty_library_teaches_honestly() -> None:
    # The direct-construction default's pins: RenderContext's
    # icon-free default is exactly IconLibrary(()), so a library with
    # no sources is that default, and an icon request there teaches
    # the fact rather than an empty-roster oddity.
    library = IconLibrary(())
    assert library.names() == frozenset()
    with pytest.raises(ValueError, match="no installed plugin ships icons"):
        library.load("core-check")
