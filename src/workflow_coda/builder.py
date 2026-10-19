"""The report builder: one manifest, one layout, the loaded plugins →
one report document.

``build_report`` orchestrates the whole report building pipeline:

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
5. Walk every tab's composition: resolve each placement against the
   *gated* plugins and apply the ``on_missing`` policy (layout-level
   default, per-placement override); render the resolved ones; and
   compose row, grid, and card nodes around their walked children.
   A diagnostics node becomes its marker entry.  Compositions whose
   children all resolve away collapse, and so do tabs left with no
   nodes — the diagnostics already explain why.
6. Catch plugin bugs per component and collect them as ``failed``
   entries plus diagnostics; the build itself only fails on
   authoring and environment problems.

The result is a :class:`~workflow_coda.report.ReportDocument`: fully
resolved, registry-free, ready for the rendering layer.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from .artifact_store import ArtifactStore
from .assets import embed_asset
from .components import ComponentStatus, PlacementInfo, ReportComponent
from .context import RenderContext
from .errors import ComponentUnavailableError, LayoutError
from .layout import (
    CardNode,
    ComponentPlacement,
    DiagnosticsNode,
    GridLayout,
    LayoutNode,
    MissingPolicy,
    RowNode,
    UnavailablePolicy,
)
from .layout_loader import UniqueKeySafeLoader, load_layout
from .manifest import ManifestSchemaVersion
from .plugins import ReportPlugin
from .registry import PluginRegistry
from .report import (
    CardEntry,
    ComponentEntry,
    Diagnostic,
    DiagnosticKind,
    DiagnosticsEntry,
    DocumentNode,
    DocumentTab,
    EmbeddedAsset,
    EntryKind,
    GridEntry,
    ReportDocument,
    RowEntry,
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
) -> ComponentEntry:
    """Call the component's render and wrap the result.

    The boundary is ``Exception``: plugin bugs are collected, never
    fatal, and ``KeyboardInterrupt``/``SystemExit`` still propagate.
    The entry is constructed inside the ``try`` so a render result
    that violates the entry contract is collected as a plugin bug
    too, not a build crash.  The render call receives the resolved
    instance title through :class:`PlacementInfo` — the placement's
    own when the layout names it, the component declaration's
    default otherwise — so a TILE component can paint it; the entry
    carries the same title plus the component's declared chrome, so
    the renderer knows who painted what.
    """
    title = placement.title if placement.title is not None else component.title
    info = PlacementInfo(title=title)
    try:
        outcome = component.render(context, info, placement.parameters)
        return ComponentEntry(
            kind=EntryKind.RENDERED,
            component_id=placement.id,
            title=title,
            chrome=component.chrome,
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
                    f"{error}; the report shows the failure in place"
                ),
            )
        )
        return ComponentEntry(
            kind=EntryKind.FAILED,
            component_id=placement.id,
            title=title,
            chrome=component.chrome,
            error=error,
        )


@dataclass(frozen=True, slots=True)
class _WalkState:
    """Everything the composition walk carries, so each helper takes
    the state plus the node it walks."""

    gated: dict[str, tuple[ReportPlugin, ReportComponent]]
    """Component ids the manifest's schema version admits."""

    full: dict[str, tuple[ReportPlugin, ReportComponent]]
    """Every loaded component id, for the exclusion story."""

    context: RenderContext
    """The shared render context."""

    diagnostics: list[Diagnostic]
    """The builder's growing ledger."""

    missing_policy: MissingPolicy
    """The layout-level ``on_missing`` default."""

    unavailable_policy: UnavailablePolicy
    """The layout-level ``on_unavailable`` default."""

    schema_version: ManifestSchemaVersion
    """The manifest's schema version, for the teaching messages."""


def _triage_unavailable(
    state: _WalkState, placement: ComponentPlacement, entry: ComponentEntry
) -> ComponentEntry | None:
    """Apply the ``on_unavailable`` policy to an unavailable outcome.

    The second placement gate, post-render: the component resolved,
    its render ran, and the outcome says the data is missing.
    ``notice`` keeps the entry — the renderer paints the notice card
    with the outcome's message; ``skip`` drops the node and records
    the omission as an informational diagnostic, so the ledger
    remembers what the page does not show and a collapsed tab is
    already explained; ``fail`` refuses the build, carrying the
    outcome's own teaching message.  Plugin bugs (``FAILED`` entries)
    and deliberate ``SKIPPED`` outcomes are never governed: bugs are
    always collected in place, and an intentional skip already
    renders nothing.
    """
    if entry.kind is not EntryKind.RENDERED:
        return entry  # a plugin bug, not a data fact
    outcome = entry.outcome
    assert outcome is not None  # the RENDERED pairing
    if outcome.status is not ComponentStatus.UNAVAILABLE:
        return entry
    policy = (
        placement.on_unavailable
        if placement.on_unavailable is not None
        else state.unavailable_policy
    )
    if policy is UnavailablePolicy.NOTICE:
        return entry
    if policy is UnavailablePolicy.SKIP:
        state.diagnostics.append(
            Diagnostic(
                kind=DiagnosticKind.COMPONENT_UNAVAILABLE,
                subject=placement.id,
                message=(
                    f"component {placement.id!r} omitted: its render "
                    f"returned unavailable — {outcome.message}"
                ),
            )
        )
        return None
    raise ComponentUnavailableError(
        f"the layout places component {placement.id!r} with "
        f"on_unavailable: fail, but its render returned unavailable: "
        f"{outcome.message} — this report considers the component "
        f"fundamentally required; rerun the pipeline stage that "
        f"produces its data, or set on_unavailable: notice or skip"
    )


def _resolve_placement(
    state: _WalkState, placement: ComponentPlacement
) -> ComponentEntry | None:
    """Resolve and render one placement, or ``None`` when it resolves
    away under the policy.

    ``fail`` raises with the full story; ``notice`` records the
    diagnostic; ``skip`` is silent.  The teaching messages are the
    contract the CLI's exit-1 family pins — unchanged in wording.
    """
    if placement.id in state.gated:
        _, component = state.gated[placement.id]
        entry = _render(component, placement, state.context, state.diagnostics)
        return _triage_unavailable(state, placement, entry)
    if placement.id in state.full:
        plugin, _ = state.full[placement.id]
        versions = ", ".join(sorted(plugin.metadata.supported_schema_versions))
        reason = (
            f"its plugin {plugin.metadata.id!r} does not support "
            f"this manifest's schema version "
            f"{state.schema_version!r} (it supports: {versions})"
        )
        subject = plugin.metadata.id
        kind = DiagnosticKind.PLUGIN_EXCLUDED
    else:
        available = ", ".join(sorted(state.gated)) or "none"
        reason = (
            f"no loaded plugin supporting manifest schema "
            f"version {state.schema_version!r} offers it "
            f"(available: {available})"
        )
        subject = placement.id
        kind = DiagnosticKind.COMPONENT_MISSING
    missing_policy = (
        placement.on_missing
        if placement.on_missing is not None
        else state.missing_policy
    )
    if missing_policy is MissingPolicy.FAIL:
        raise ComponentUnavailableError(
            f"the layout places component {placement.id!r}, "
            f"but {reason} — correct the id, install a plugin "
            f"that offers it, or set on_missing: notice or skip"
        )
    if missing_policy is MissingPolicy.NOTICE:
        state.diagnostics.append(
            Diagnostic(
                kind=kind,
                subject=subject,
                message=f"component {placement.id!r} omitted: {reason}",
            )
        )
    return None


def _walk(state: _WalkState, node: LayoutNode) -> DocumentNode | None:
    """One layout node to its document node, or ``None`` when it
    collapses."""
    if isinstance(node, ComponentPlacement):
        return _resolve_placement(state, node)
    if isinstance(node, DiagnosticsNode):
        return DiagnosticsEntry()
    if isinstance(node, RowNode):
        children = _walk_all(state, node.children)
        if not children:
            return None
        return RowEntry(split=node.split, children=children)
    if isinstance(node, GridLayout):
        children = _walk_all(state, node.children)
        if not children:
            return None
        return GridEntry(split=node.split, children=children)
    assert isinstance(node, CardNode)  # the node union is exhausted
    children = _walk_all(state, node.children)
    if not children:
        return None
    return CardEntry(
        title=node.title, layout=node.layout, split=node.split, children=children
    )


def _walk_all(
    state: _WalkState, nodes: Iterable[LayoutNode]
) -> tuple[DocumentNode, ...]:
    """Walk every node, keeping the ones that survive."""
    return tuple(walked for node in nodes if (walked := _walk(state, node)) is not None)


def build_report(
    layout_path: Path,
    store: ArtifactStore,
    registry: PluginRegistry | None = None,
) -> ReportDocument:
    """Build the report document for one artifact bundle under one
    layout.

    *store* is the bundle's artifact store; the manifest is read from
    ``store.manifest``, so the two can never disagree.  *registry*
    defaults to the plugins installed in the environment; pass one to
    build against a fixed set.

    Raises :class:`~workflow_coda.errors.LayoutError` for authoring
    problems (the layout file, the theme file it declares, declared
    image assets), :class:`~workflow_coda.errors.PluginLoadError` /
    ``PluginConflictError`` for a broken plugin environment, and
    :class:`~workflow_coda.errors.ComponentUnavailableError` when the
    ``fail`` policy meets an unresolvable placement.  Plugin bugs
    never propagate — they become ``failed`` entries and diagnostics.
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
        layout_path, layout.logo, "logo", DiagnosticKind.LOGO_OMITTED, diagnostics
    )
    favicon = _prepare_asset(
        layout_path,
        layout.favicon,
        "favicon",
        DiagnosticKind.FAVICON_OMITTED,
        diagnostics,
    )

    # Plugin gating and the walk's resolution tables.
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
    state = _WalkState(
        gated=gated,
        full=full,
        context=context,
        diagnostics=diagnostics,
        missing_policy=layout.on_missing,
        unavailable_policy=layout.on_unavailable,
        schema_version=manifest.schema_version,
    )

    # The tab walk: compose, resolve, render — and collapse empties.
    tabs: list[DocumentTab] = []
    for layout_tab in layout.tabs:
        nodes = _walk_all(state, layout_tab.components)
        if nodes:
            tabs.append(DocumentTab(title=layout_tab.title, nodes=nodes))

    return ReportDocument(
        title=layout.title,
        subtitle=layout.subtitle,
        author=layout.author,
        version=layout.version,
        theme=theme,
        logo=logo,
        favicon=favicon,
        manifest=manifest,
        tabs=tuple(tabs),
        diagnostics=tuple(diagnostics),
    )
