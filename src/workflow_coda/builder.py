"""The report builder: one manifest, one layout, the loaded plugins →
one report document.

``build_report`` orchestrates the whole layout building pipeline:

1. Load the layout file (raising
   :class:`~workflow_coda.errors.LayoutError` on any authoring
   failure).
2. Load the plugin registry — the installed environment by default;
   the ``registry`` parameter injects a fixed one, which is how the
   tests run.
3. Gate plugins by the manifest's schema version.  Excluded plugins do
   not render; placements that reference them are named — with both
   sides' versions — in the failure or diagnostic the ``on_missing``
   policy chooses.
4. Load the theme and embed the declared assets, both under the
   declared-then-strict rule: omitted means default theme and missing
   logo/favicon, each recorded as an informational diagnostic;
   declared must load, or the build fails.
5. Resolve every placement against the *gated* plugins and apply the
   ``on_missing`` policy (layout-level default, per-placement
   override).  ``fail`` raises
   :class:`~workflow_coda.errors.ComponentUnavailableError` naming what
   *is* available; ``notice`` renders without the component and
   records why; ``skip`` omits silently.
6. Render each resolved component — its declared render call with the
   shared :class:`~workflow_coda.context.RenderContext` and the
   placement's parameters.  Plugin bugs are caught per component and
   collected as ``failed`` entries plus diagnostics; the build itself
   only fails on authoring and environment problems.

The result is a :class:`~workflow_coda.report.ReportDocument`: fully
resolved, registry-free, ready for the rendering layer.  Sections
whose placements all resolve away are dropped — the diagnostics
already explain why.
"""

from pathlib import Path

import yaml
from pydantic import ValidationError

from .artifact_store import ArtifactStore
from .assets import embed_asset
from .components import ReportComponent
from .context import RenderContext
from .errors import ComponentUnavailableError, LayoutError
from .layout import ComponentPlacement, MissingPolicy
from .layout_loader import UniqueKeySafeLoader, load_layout
from .plugins import ReportPlugin
from .registry import PluginRegistry
from .report import (
    Diagnostic,
    DiagnosticKind,
    DocumentSection,
    EmbeddedAsset,
    EntryKind,
    ReportDocument,
    SectionEntry,
)
from .theme import DEFAULT_THEME, Theme


def _load_theme(layout_path: Path, declared: str) -> Theme:
    """Load the theme file declared in the layout, strictly.

    Teaching errors name the theme file and the layout that declared
    it; duplicate keys are rejected through the shared loader, and
    validation problems are condensed to one line per token.
    """
    theme_path = layout_path.parent / declared
    try:
        text = theme_path.read_text(encoding="utf-8")
    except OSError as e:
        raise LayoutError(
            f"cannot read the theme file {theme_path} declared in "
            f"{layout_path.name!r}: {e.strerror or e}"
        ) from e
    try:
        parsed = yaml.load(text, Loader=UniqueKeySafeLoader)
    except yaml.YAMLError as e:
        detail = " ".join(str(e).split())
        raise LayoutError(
            f"{theme_path} (declared in the layout) is not valid YAML: {detail}"
        ) from e
    if not isinstance(parsed, dict):
        found = (
            "nothing (the file is empty)"
            if parsed is None
            else f"a single {type(parsed).__name__} value"
        )
        raise LayoutError(
            f"{theme_path} (declared in the layout) must be a mapping "
            f"of theme tokens, but contains {found}"
        )
    try:
        return Theme.model_validate(parsed)
    except ValidationError as e:
        detail = "; ".join(f"{error['loc']}: {error['msg']}" for error in e.errors())
        raise LayoutError(
            f"{theme_path} (declared in the layout) is not a valid theme: {detail}"
        ) from e


def _prepare_asset(
    layout_path: Path,
    declared: str | None,
    role: str,
    omitted: DiagnosticKind,
    diagnostics: list[Diagnostic],
) -> EmbeddedAsset | None:
    """Embed the declared asset, or record the omission diagnostic."""
    if declared is None:
        diagnostics.append(
            Diagnostic(
                kind=omitted,
                subject=role,
                message=(
                    f"no {role} declared in the layout — the report "
                    f"renders without it; add a '{role}:' path next to "
                    f"the layout file to embed one"
                ),
            )
        )
        return None
    return embed_asset(layout_path, declared, role)


def _render(
    component: ReportComponent,
    placement: ComponentPlacement,
    context: RenderContext,
    diagnostics: list[Diagnostic],
) -> SectionEntry:
    """Call the component's render and wrap the result.

    The boundary is ``Exception``: plugin bugs are collected, never
    fatal, and ``KeyboardInterrupt``/``SystemExit`` still propagate.
    The entry is constructed inside the ``try`` so a render result
    that violates the entry contract is collected as a plugin bug
    too, not a build crash.
    """
    try:
        outcome = component.render(context, placement.parameters)
        return SectionEntry(
            kind=EntryKind.RENDERED,
            component_id=placement.id,
            title=component.title,
            outcome=outcome,
        )
    except Exception as e:  # noqa: BLE001 — the plugin-bug boundary
        error = f"{type(e).__name__}: {e}"
        diagnostics.append(
            Diagnostic(
                kind=DiagnosticKind.PLUGIN_BUG,
                subject=placement.id,
                message=(
                    f"rendering component {placement.id!r} raised "
                    f"{error}; the section shows the failure in place"
                ),
            )
        )
        return SectionEntry(
            kind=EntryKind.FAILED,
            component_id=placement.id,
            title=component.title,
            error=error,
        )


def build_report(
    layout_path: Path,
    store: ArtifactStore,
    registry: PluginRegistry | None = None,
) -> ReportDocument:
    """Build the report document for one artifact bundle under one layout.

    *store* is the bundle's artifact store; the manifest is read from
    ``store.manifest``, so the two can never disagree.  *registry*
    defaults to the plugins installed in the environment; pass one to
    build against a fixed set.

    Raises :class:`~workflow_coda.errors.LayoutError` for authoring
    problems (the layout file, the theme file it declares, declared
    image assets), :class:`~workflow_coda.errors.PluginLoadError` /
    ``PluginConflictError`` for a broken plugin environment, and
    :class:`~workflow_coda.errors.ComponentUnavailableError`` when the
    ``fail`` policy meets an unresolvable placement.  Plugin bugs never
    propagate — they become ``failed`` entries and diagnostics.
    """
    if registry is None:
        registry = PluginRegistry.load()
    manifest = store.manifest
    layout = load_layout(layout_path)
    diagnostics: list[Diagnostic] = []

    # Theme and assets: declared-then-strict.
    if layout.theme is not None:
        theme = _load_theme(layout_path, layout.theme)
    else:
        theme = DEFAULT_THEME
        diagnostics.append(
            Diagnostic(
                kind=DiagnosticKind.DEFAULT_THEME,
                subject=DEFAULT_THEME.name,
                message=(
                    "no theme file declared in the layout — rendered "
                    "with the built-in default theme; add a 'theme:' "
                    "path to customize"
                ),
            )
        )
    logo = _prepare_asset(
        layout_path,
        layout.logo,
        "logo",
        DiagnosticKind.LOGO_OMITTED,
        diagnostics,
    )
    favicon = _prepare_asset(
        layout_path,
        layout.favicon,
        "favicon",
        DiagnosticKind.FAVICON_OMITTED,
        diagnostics,
    )

    # Plugin gating and lookup tables.
    gated: dict[str, tuple[ReportPlugin, ReportComponent]] = {
        component.id: (plugin, component)
        for plugin in registry.plugins_supporting(manifest.schema_version)
        for component in plugin.components
    }
    full: dict[str, tuple[ReportPlugin, ReportComponent]] = {
        component.id: (plugin, component)
        for plugin in registry.plugins
        for component in plugin.components
    }
    context = RenderContext(store=store, theme=theme)

    # Placement resolution, policy, rendering.
    sections: list[DocumentSection] = []
    for layout_section in layout.sections:
        entries: list[SectionEntry] = []
        for placement in layout_section.components:
            policy = (
                placement.on_missing
                if placement.on_missing is not None
                else layout.on_missing
            )
            if placement.id in gated:
                _, component = gated[placement.id]
                entries.append(_render(component, placement, context, diagnostics))
                continue
            if placement.id in full:
                plugin, _ = full[placement.id]
                versions = ", ".join(sorted(plugin.metadata.supported_schema_versions))
                reason = (
                    f"its plugin {plugin.metadata.id!r} does not support "
                    f"this manifest's schema version "
                    f"{manifest.schema_version!r} (it supports: {versions})"
                )
                subject = plugin.metadata.id
                kind = DiagnosticKind.PLUGIN_EXCLUDED
            else:
                available = ", ".join(sorted(gated)) or "none"
                reason = (
                    f"no loaded plugin supporting manifest schema "
                    f"version {manifest.schema_version!r} offers it "
                    f"(available: {available})"
                )
                subject = placement.id
                kind = DiagnosticKind.COMPONENT_MISSING
            if policy is MissingPolicy.FAIL:
                raise ComponentUnavailableError(
                    f"the layout places component {placement.id!r}, "
                    f"but {reason} — correct the id, install a plugin "
                    f"that offers it, or set on_missing: notice or skip"
                )
            if policy is MissingPolicy.NOTICE:
                diagnostics.append(
                    Diagnostic(
                        kind=kind,
                        subject=subject,
                        message=f"component {placement.id!r} omitted: {reason}",
                    )
                )
            # SKIP: omit silently.
        if entries:
            sections.append(
                DocumentSection(title=layout_section.title, entries=tuple(entries))
            )

    return ReportDocument(
        title=layout.title,
        subtitle=layout.subtitle,
        author=layout.author,
        version=layout.version,
        theme=theme,
        logo=logo,
        favicon=favicon,
        manifest=manifest,
        sections=tuple(sections),
        diagnostics=tuple(diagnostics),
        toc=layout.toc,
    )
