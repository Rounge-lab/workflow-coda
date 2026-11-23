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
   policy chooses.  The gated plugins' icon declarations are also
   assembled here, into the build's icon library: a gated-out
   plugin's icons are unaddressable, and its defects must not fail
   an unrelated report. The library is assembled before the declared
   assets are prepared, because the logo's icon-name branch loads
   through it.
4. Load the theme, validate the declared header_color token against it
   (omitted carries None to the document — the renderer derives primary),
   and embed the declared assets, both under the declared-then-strict
   rule: omitted means the default theme and missing logo/favicon, each
   recorded as an informational diagnostic (the header color excepted —
   a styling default, not an omission); declared must load, or the
   build fails.
5. Walk every tab's composition: resolve each placement against the
   *gated* plugins and apply the ``on_missing`` policy (layout-level
   default, per-placement override); render the resolved ones; and
   compose row, grid, card, and states nodes around their walked
   children.  A diagnostics node becomes its marker entry.  A states
   node expands its template once per axis value — the declared
   ``values``, or the axis derived from the manifest's artifact
   types — substituting the value into every free string leaf
   before the walk descends, so the document holds every state's
   content and no states placeholder survives it. Valid markdown
   variables in string-valued ``core.markdown.text`` remain opaque
   during expansion; the component resolves them from its artifact.
   Compositions whose children all resolve away collapse, and so do
   tabs left with no nodes — the diagnostics already explain why.
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

from .artifact_store import ArtifactStore, JsonValue
from .assets import embed_asset, embed_inline_svg
from .components import ComponentStatus, PlacementInfo, ReportComponent
from .context import RenderContext
from .core.markdown_variables import MARKDOWN_VARIABLE_RE
from .errors import ComponentUnavailableError, LayoutError, SpecError
from .icons import IconLibrary, IconSource
from .layout import (
    CardNode,
    ComponentPlacement,
    DiagnosticsNode,
    GridLayout,
    LayoutNode,
    MissingPolicy,
    RowNode,
    StatesNode,
    UnavailablePolicy,
)
from .layout_loader import load_layout
from .manifest import ManifestSchemaVersion
from .plugins import ReportPlugin
from .registry import PluginRegistry
from .report import (
    CardEntry,
    ChromeContribution,
    ComponentEntry,
    Diagnostic,
    DiagnosticKind,
    DiagnosticsEntry,
    DocumentNode,
    DocumentTab,
    EmbeddedAsset,
    EntryKind,
    GridEntry,
    InlineLogo,
    ReportDocument,
    RowEntry,
    StatePanel,
    StatesEntry,
)
from .theme import DEFAULT_THEME, Theme, ThemeToken
from .verification.expansion import expand_template, substitute_raw
from .yaml_loader import UniqueKeySafeLoader


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


def _resolve_header_color(
    theme: Theme,
    declared: ThemeToken | tuple[ThemeToken, ThemeToken] | None,
) -> ThemeToken | tuple[ThemeToken, ThemeToken] | None:
    """Validate each declared reference; omission stays omitted."""
    if declared is None:
        return None

    references = declared if isinstance(declared, tuple) else (declared,)
    for reference in references:
        try:
            theme.resolve_color("the layout's header_color", reference)
        except ValueError as e:
            available = ", ".join(sorted(theme.colors))
            raise LayoutError(
                f"the layout declares header_color {reference!r}, but the "
                f"report's theme cannot resolve it ({available}) — "
                "declare the token in the theme, or name one it carries "
                f"or a valid series entry; {e}"
            ) from e

    return declared


def _logo_from_icon(library: IconLibrary, declared: str) -> InlineLogo:
    """The layout's logo as a bundled icon, by name.

    The declared-then-strict rule's icon branch: the name must be
    one the build's library carries — an unknown name is the
    layout's typo, taught with the roster the environment ships; a
    shipped icon that fails its own validation teaches as the
    broken-installation family, already wrapped by the library.
    The sanitized markup rides the document; the page inlines it
    as a real ``<svg>``, so ``currentColor`` inherits the header's
    ink.
    """
    try:
        icon = library.load(declared)
    except ValueError as e:
        raise LayoutError(str(e)) from e
    return InlineLogo(source=declared, markup=icon.markup)


def _prepare_logo(
    layout_path: Path,
    declared: str | None,
    library: IconLibrary,
    diagnostics: list[Diagnostic],
) -> EmbeddedAsset | InlineLogo | None:
    """The layout's logo: one key, two vocabularies.

    A value carrying a path separator or a dot addresses a file
    next to the layout — an SVG file inlines as sanitized markup
    (so ``currentColor`` inherits the header's ink; raster formats
    embed as a data URI, which cannot inherit and does not pretend
    to).  Anything else addresses the build's icon library by name
    — icon names are ``<plugin_id>-<name>`` stems, no separators
    and no dots, so the branch is law, not guesswork: each typo
    lands in its own vocabulary's teaching.  Omitted, the omission
    diagnostic stands, teaching both vocabularies.
    """
    if declared is None:
        diagnostics.append(
            Diagnostic(
                kind=DiagnosticKind.LOGO_OMITTED,
                subject="logo",
                message=(
                    "no logo declared in the layout — the report "
                    "renders without it; add a 'logo:' image path "
                    "next to the layout file, or a bundled icon's "
                    "name (e.g. 'core-coda'), to embed one"
                ),
            )
        )
        return None
    if any(mark in declared for mark in ("/", "\\", ".")):
        if declared.lower().endswith(".svg"):
            return embed_inline_svg(layout_path, declared, "logo")
        return embed_asset(layout_path, declared, "logo")
    return _logo_from_icon(library, declared)


def _prepare_asset(
    layout_path: Path,
    declared: str | None,
    role: str,
    omitted: DiagnosticKind,
    diagnostics: list[Diagnostic],
) -> EmbeddedAsset | None:
    """Embed the declared asset, or record the omission diagnostic.
    Serves the favicon today; the logo has its own two-vocabulary
    prep (:func:_prepare_logo)."""
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
    too, not a build crash.  A healthy render's notes merge into the
    diagnostics ledger after the entry guard has validated the
    result — informational, in placement order.  The render call
    receives the resolved instance title through :class:`PlacementInfo` — the placement's
    own when the layout names it, the component declaration's
    default otherwise — so a TILE component can paint it; the entry
    carries the same title plus the component's declared chrome, so
    the renderer knows who painted what.
    """
    title = placement.title if placement.title is not None else component.title
    info = PlacementInfo(title=title)
    try:
        outcome = component.render(context, info, placement.parameters)
        entry = ComponentEntry(
            kind=EntryKind.RENDERED,
            component_id=placement.id,
            title=title,
            chrome=component.chrome,
            outcome=outcome,
        )
        for note in outcome.notes:
            diagnostics.append(
                Diagnostic(
                    kind=DiagnosticKind.COMPONENT_NOTE,
                    subject=placement.id,
                    message=note,
                )
            )
        return entry
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

    ok_component_ids: list[str]
    """Component ids that rendered at least one ``OK`` outcome — the
    chrome channel's collection: first-use order, deduplicated.
    Accumulated during the walk, resolved into the document's chrome
    after it."""

    missing_policy: MissingPolicy
    """The layout-level ``on_missing`` default."""

    unavailable_policy: UnavailablePolicy
    """The layout-level ``on_unavailable`` default."""

    schema_version: ManifestSchemaVersion
    """The manifest's schema version, for the teaching messages."""

    layout_path: Path
    """The layout file's path — the states substitution boundary
    wraps the expansion teachings in :class:`LayoutError`, and it
    rides down to them as their path, so the teaching names the
    author's own file."""


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


def _note_ok_component(
    state: _WalkState, placement: ComponentPlacement, entry: ComponentEntry
) -> None:
    """Record the placement's component in the chrome collection when
    its outcome rendered ``OK`` — first-use order, deduplicated.

    The chrome channel's predicate: a component contributes its
    declared css and js to the report exactly when at least one of
    its placements rendered content.  Degraded instances —
    unavailable outcomes, plugin bugs — never record: the
    framework's notice and failure cards need no plugin chrome.
    """
    if (
        entry.kind is EntryKind.RENDERED
        and entry.outcome is not None
        and entry.outcome.status is ComponentStatus.OK
        and placement.id not in state.ok_component_ids
    ):
        state.ok_component_ids.append(placement.id)


def _resolve_placement(
    state: _WalkState, placement: ComponentPlacement
) -> ComponentEntry | None:
    """Resolve and render one placement, or ``None`` when it resolves
    away under the policy.

    ``fail`` raises with the full story; ``notice`` records the
    diagnostic; ``skip`` is silent.  The teaching messages are the
    contract the CLI's exit-1 family pins — unchanged in wording.
    A gated placement's OK outcome is also recorded in the chrome collection — see
    :func:_note_ok_component.
    """
    if placement.id in state.gated:
        _, component = state.gated[placement.id]
        entry = _render(component, placement, state.context, state.diagnostics)
        _note_ok_component(state, placement, entry)
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


def _states_axis(state: _WalkState, node: StatesNode) -> tuple[str, ...]:
    """The node's axis: the declared ``values`` as written, or — the
    derived door — the manifest's distinct artifact types, in
    declaration order."""
    if node.values is not None:
        return tuple(node.values)
    artifacts = state.context.store.manifest.artifacts
    return tuple(dict.fromkeys(artifact.type for artifact in artifacts))


def _pending_dimensions(node: LayoutNode) -> tuple[str, ...]:
    """The dimensions states nodes inside *node*'s subtree will bind,
    in traversal order, deduplicated.

    One substitution round passes these placeholders through
    untouched: they belong to inner rounds, which substitute them
    when the walk reaches their owning nodes.  A states node binds
    its own dimension, so the node itself counts.
    """
    if isinstance(node, StatesNode):
        pending = [node.dimension]
        for child in node.children:
            pending.extend(_pending_dimensions(child))
        return tuple(dict.fromkeys(pending))
    if isinstance(node, (RowNode, GridLayout, CardNode)):
        nested: list[str] = []
        for child in node.children:
            nested.extend(_pending_dimensions(child))
        return tuple(dict.fromkeys(nested))
    return ()


def _expand_all(
    nodes: tuple[LayoutNode, ...],
    *,
    dimension: str,
    raw: str,
    bound: tuple[str, ...],
    path: Path,
) -> tuple[LayoutNode, ...]:
    """One substitution round over every child, in order."""
    return tuple(
        _expand_node(child, dimension=dimension, raw=raw, bound=bound, path=path)
        for child in nodes
    )


def _expand_markdown_text(
    text: str,
    *,
    dimension: str,
    raw: str,
    bound: tuple[str, ...],
    path: Path,
) -> str:
    """Expand states text between valid markdown artifact variables.

    Valid markdown variables are opaque only within string-valued
    ``core.markdown.text``. This helper preserves their exact spelling;
    malformed braces and unbound states placeholders still reach the
    strict expansion engine. The joined result is never re-expanded.
    """
    parts: list[str] = []
    cursor = 0
    for match in MARKDOWN_VARIABLE_RE.finditer(text):
        parts.append(
            expand_template(
                text[cursor : match.start()],
                dimension=dimension,
                raw=raw,
                path=path,
                scope=bound,
            )
        )
        parts.append(match.group(0))
        cursor = match.end()
    parts.append(
        expand_template(
            text[cursor:],
            dimension=dimension,
            raw=raw,
            path=path,
            scope=bound,
        )
    )
    return "".join(parts)


def _expand_parameters(
    placement: ComponentPlacement,
    *,
    dimension: str,
    raw: str,
    bound: tuple[str, ...],
    path: Path,
) -> dict[str, JsonValue]:
    """Expand parameter keys and values in their declared order.

    Valid markdown variables are opaque only within string-valued
    ``core.markdown.text``. Eligibility uses the original placement id
    and parameter key, never the expanded key. Other values recurse
    through the ordinary states engine, preserving its overwrite
    behavior when expanded keys coincide.
    """
    parameters: dict[str, JsonValue] = {}
    for key, value in placement.parameters.items():
        expanded_key = expand_template(
            key, dimension=dimension, raw=raw, path=path, scope=bound
        )
        if placement.id == "core.markdown" and key == "text" and isinstance(value, str):
            expanded_value: JsonValue = _expand_markdown_text(
                value, dimension=dimension, raw=raw, bound=bound, path=path
            )
        else:
            expanded_value = substitute_raw(
                value, dimension=dimension, raw=raw, path=path, scope=bound
            )
        parameters[expanded_key] = expanded_value
    return parameters


def _expand_placement(
    placement: ComponentPlacement,
    *,
    dimension: str,
    raw: str,
    bound: tuple[str, ...],
    path: Path,
) -> ComponentPlacement:
    """One substitution round over a placement: the free string
    leaves take the round's value; the addressing and policy fields
    ride untouched — ``id`` refuses placeholders at load, and the
    policies are enums. Valid markdown variables in string-valued
    ``core.markdown.text`` remain opaque for component resolution.
    """
    title = (
        expand_template(
            placement.title, dimension=dimension, raw=raw, path=path, scope=bound
        )
        if placement.title is not None
        else None
    )
    parameters = _expand_parameters(
        placement, dimension=dimension, raw=raw, bound=bound, path=path
    )
    return placement.model_copy(update={"title": title, "parameters": parameters})


def _expand_states_node(
    node: StatesNode,
    *,
    dimension: str,
    raw: str,
    bound: tuple[str, ...],
    path: Path,
) -> StatesNode:
    """One substitution round over a nested states node: its declared
    values take the round's value too — the one-law ruling, an outer
    placeholder in a nested axis substitutes in the outer round —
    and its children recurse.  The structural fields — ``dimension``
    and ``kind`` — ride untouched.
    """
    values = (
        tuple(
            expand_template(value, dimension=dimension, raw=raw, path=path, scope=bound)
            for value in node.values
        )
        if node.values is not None
        else None
    )
    return node.model_copy(
        update={
            "values": values,
            "children": _expand_all(
                node.children, dimension=dimension, raw=raw, bound=bound, path=path
            ),
        }
    )


def _expand_node(
    node: LayoutNode,
    *,
    dimension: str,
    raw: str,
    bound: tuple[str, ...],
    path: Path,
) -> LayoutNode:
    """One substitution round over a copy of *node*: *raw* replaces
    every ``{dimension}`` in the subtree's free string leaves.

    The decided architecture, one round per states node: this round
    substitutes exactly its own dimension across the whole subtree
    — placement titles, parameter keys and values, card titles,
    and nested states nodes' declared values included — while
    placeholders naming a dimension in *bound* pass through
    untouched, because their owning node's round substitutes them
    when the walk reaches it. Valid markdown variables in
    string-valued ``core.markdown.text`` are opaque to every round.
    Nesting resolves by round order, and a shadowed dimension means
    the outer round wins: its round has already replaced every
    occurrence before the inner node's round runs.

    The structural fields ride untouched — placement ``id`` refuses
    placeholders at load, policies are enums, splits are numbers,
    and a states node's ``dimension`` cannot carry braces by its
    own grammar.  The copy is built with ``model_copy``, which
    skips the models' validators — safe by construction: an axis
    value is visible text, so substituting it keeps every
    visible-text field visible.
    """
    if isinstance(node, ComponentPlacement):
        return _expand_placement(
            node, dimension=dimension, raw=raw, bound=bound, path=path
        )
    if isinstance(node, (RowNode, GridLayout)):
        return node.model_copy(
            update={
                "children": _expand_all(
                    node.children, dimension=dimension, raw=raw, bound=bound, path=path
                )
            }
        )
    if isinstance(node, CardNode):
        title = (
            expand_template(
                node.title, dimension=dimension, raw=raw, path=path, scope=bound
            )
            if node.title is not None
            else None
        )
        return node.model_copy(
            update={
                "title": title,
                "children": _expand_all(
                    node.children, dimension=dimension, raw=raw, bound=bound, path=path
                ),
            }
        )
    if isinstance(node, StatesNode):
        return _expand_states_node(
            node, dimension=dimension, raw=raw, bound=bound, path=path
        )
    assert isinstance(node, DiagnosticsNode)  # the node union is exhausted
    return node


def _walk_states(
    state: _WalkState, node: StatesNode, scope_prefix: tuple[str, ...]
) -> StatesEntry | None:
    """Walk one states node: expand its children once per axis value.

    The axis is :func:`_states_axis`'s — declared values as written,
    or the manifest's distinct artifact types.  A derived-empty axis
    is a build-time fact, not a load-time contradiction: the node
    collapses and an informational diagnostic names the two ways to
    give it values.

    Per value, every child takes one substitution round — the
    round's value substituted into every free string leaf, with the
    dimensions inner states nodes will bind passed through for
    their own rounds — and the substituted copy walks like any
    other node, under the layout-error family: the expansion
    teachings (a malformed or unbindable placeholder) wrap as
    :class:`LayoutError`, the authoring family.  A value whose
    children all collapse drops its panel; a node whose every panel
    dropped collapses too — the ledger already explains why.
    """
    axis = _states_axis(state, node)
    if not axis:
        state.diagnostics.append(
            Diagnostic(
                kind=DiagnosticKind.STATES_EMPTY,
                subject=node.dimension,
                message=(
                    f"states node omitted: its dimension "
                    f"{node.dimension!r} derives an empty axis — the "
                    "manifest declares no artifacts to derive one "
                    "from; declare artifacts in the manifest, or name "
                    "the axis with 'values:' on the states node"
                ),
            )
        )
        return None
    scope = scope_prefix + (node.dimension,)
    panels: list[StatePanel] = []
    for raw in axis:
        children: list[DocumentNode] = []
        for child in node.children:
            bound = scope + _pending_dimensions(child)
            try:
                expanded = _expand_node(
                    child,
                    dimension=node.dimension,
                    raw=raw,
                    bound=bound,
                    path=state.layout_path,
                )
            except SpecError as e:
                # The expansion teachings already open with the
                # layout's path — it rides down as the expansion
                # path — so the wrap adds the authoring family, not
                # a second path prefix.
                raise LayoutError(str(e)) from e
            walked = _walk(state, expanded, scope_prefix=scope)
            if walked is not None:
                children.append(walked)
        if children:
            panels.append(StatePanel(value=raw, children=tuple(children)))
    if not panels:
        return None
    return StatesEntry(dimension=node.dimension, kind=node.kind, panels=tuple(panels))


def _walk(
    state: _WalkState, node: LayoutNode, scope_prefix: tuple[str, ...] = ()
) -> DocumentNode | None:
    """Walk one layout node into its document node, or ``None`` when
    the node collapses.

    Placements resolve through the two policy gates; a diagnostics
    node becomes its marker; compositions walk their children and
    collapse when none survive.  *scope_prefix* carries the states
    dimensions already bound by outer rounds — only a states node
    consumes it, composing it into its own scope so nested
    dimensions stack; every other node passes it through unchanged.
    """
    if isinstance(node, ComponentPlacement):
        return _resolve_placement(state, node)
    if isinstance(node, DiagnosticsNode):
        return DiagnosticsEntry()
    if isinstance(node, StatesNode):
        return _walk_states(state, node, scope_prefix)
    if isinstance(node, RowNode):
        children = _walk_all(state, node.children, scope_prefix)
        if not children:
            return None
        return RowEntry(split=node.split, children=children)
    if isinstance(node, GridLayout):
        children = _walk_all(state, node.children, scope_prefix)
        if not children:
            return None
        return GridEntry(split=node.split, children=children)
    assert isinstance(node, CardNode)  # the node union is exhausted
    children = _walk_all(state, node.children, scope_prefix)
    if not children:
        return None
    return CardEntry(
        title=node.title, layout=node.layout, split=node.split, children=children
    )


def _walk_all(
    state: _WalkState,
    nodes: tuple[LayoutNode, ...],
    scope_prefix: tuple[str, ...] = (),
) -> tuple[DocumentNode, ...]:
    """Walk a node list in order, dropping the nodes that collapse —
    the composition law: a row whose every child resolved away
    renders nothing, and the ledger already explains why."""
    walked = (_walk(state, node, scope_prefix) for node in nodes)
    return tuple(entry for entry in walked if entry is not None)


def _component_map(
    plugins: Iterable[ReportPlugin],
) -> dict[str, tuple[ReportPlugin, ReportComponent]]:
    """Index a plugin set's components by id, in declaration order.

    The registry guarantees id uniqueness across plugins, so this is
    an index build, not a re-check — the one shape both of the walk's
    maps (gated and full) share."""
    return {
        component.id: (plugin, component)
        for plugin in plugins
        for component in plugin.components
    }


def build_report(
    layout_path: Path,
    store: ArtifactStore,
    registry: PluginRegistry | None = None,
) -> ReportDocument:
    """Build one report document: a layout, a manifest's artifact
    store, and the loaded plugins in, one registry-free document out.

    *registry* injects a fixed plugin set — the tests' door — and
    defaults to the installed environment.  Authoring failures raise
    :class:`~workflow_coda.errors.LayoutError` (layout, theme, and
    states-expansion problems), a policy-``fail`` placement raises
    :class:`~workflow_coda.errors.ComponentUnavailableError`, and a
    plugin's own bug never fails the build: it renders in place, the
    ledger carrying the details.  See the module docstring for the
    pipeline's steps.
    """
    layout = load_layout(layout_path)
    if registry is None:
        registry = PluginRegistry.load()
    schema_version = store.manifest.schema_version
    supporting = registry.plugins_supporting(schema_version)
    gated = _component_map(supporting)
    full = _component_map(registry.plugins)
    library = IconLibrary(
        IconSource.for_plugin(plugin.metadata.id, plugin.metadata.icons_package)
        for plugin in supporting
        if plugin.metadata.icons_package is not None
    )
    diagnostics: list[Diagnostic] = []
    if layout.theme is None:
        theme = DEFAULT_THEME
        diagnostics.append(
            Diagnostic(
                kind=DiagnosticKind.DEFAULT_THEME,
                subject="theme",
                message=(
                    "no theme declared in the layout — the report "
                    "renders with the built-in default theme; add a "
                    "'theme:' path next to the layout file to load one"
                ),
            )
        )
    else:
        theme = _load_theme(layout_path, layout.theme)
    header_color = _resolve_header_color(theme, layout.header_color)
    logo = _prepare_logo(layout_path, layout.logo, library, diagnostics)
    favicon = _prepare_asset(
        layout_path,
        layout.favicon,
        "favicon",
        DiagnosticKind.FAVICON_OMITTED,
        diagnostics,
    )
    context = RenderContext(store=store, theme=theme, icons=library)
    state = _WalkState(
        gated=gated,
        full=full,
        context=context,
        diagnostics=diagnostics,
        ok_component_ids=[],
        missing_policy=layout.on_missing,
        unavailable_policy=layout.on_unavailable,
        schema_version=schema_version,
        layout_path=layout_path,
    )
    tabs: list[DocumentTab] = []
    for tab in layout.tabs:
        nodes = _walk_all(state, tab.components)
        if nodes:
            tabs.append(DocumentTab(title=tab.title, nodes=nodes))
    chrome: list[ChromeContribution] = []
    for component_id in state.ok_component_ids:
        _, component = gated[component_id]
        if component.css is not None or component.js is not None:
            chrome.append(
                ChromeContribution(
                    component_id=component_id,
                    css=component.css,
                    js=component.js,
                )
            )
    return ReportDocument(
        title=layout.title,
        subtitle=layout.subtitle,
        author=layout.author,
        version=layout.version,
        theme=theme,
        logo=logo,
        favicon=favicon,
        manifest=store.manifest,
        tabs=tuple(tabs),
        diagnostics=tuple(diagnostics),
        chrome=tuple(chrome),
        header_color=header_color,
        header_variant=layout.header_variant,
    )
