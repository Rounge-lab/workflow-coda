"""The report renderer: one report document in one self-contained
HTML page out.

Rendering is a pure function of the document.  The report builder has
already resolved plugins, gated versions, loaded the theme, and
embedded assets; the renderer reads the document plus the framework's
own chrome — Jinja templates, stylesheet, navigation scripts shipped
as package data — and produces the page. No registry or user files.

Two responsibilities meet here:

**The tree walk** (:func:`_node_html` and friends) turns each tab's
node tree into body html — the card vocabulary for placed components,
the group box for cards, the ratio containers for rows and grids, the
diagnostics panel at its markers, and every expanded states panel in
axis order. The walk escapes every framework text it interpolates
(titles, state labels, messages, errors) and leaves exactly one raw
point inside each component: its rendered plugin html, trusted
because plugins are installed code. Tabs become the page's navigation:
one panel per tab, a tab bar generated from them when there is more
than one. Navigation enhancement is emitted when there are multiple
tabs or states; otherwise a figure-free report needs no framework
script. State panel ids use one counter local to each render call,
shared across tabs and nested states, never derived from raw labels.

**Generated layout CSS** (:func:`_splits_css`) turns the tree's split
ratios into deduplicated rules — one class per distinct ratio tuple,
grouped mobile defaults, ratios inside one ``min-width`` block — so
every ratio layout collapses to a single column on small screens by
construction, with no inline styles and no ``!important``.

Component page chrome (:func:_component_css and :func:_component_js) inlines the css and
js that rendered components declared — once per report, under the contributing
component's id banner, the style block after the framework stylesheet and the script
block after the framework's own scripts, so plugin code reads an established DOM. These
blocks are the page's second raw family: plugin strings, guarded at declaration, trusted
like plugin html and never escaped.

Self-containment holds as before: the theme ships as generated CSS
custom properties, the stylesheet, split rules, and navigation scripts
are inlined, the favicon is a data URI and the logo either a data URI
or inlined svg markup — an inline logo is real markup in the page, so
``currentColor`` inherits the header's ink — and Plotly.js is inlined
from the installed ``plotly`` package exactly when the document
contains figures, including figures inside states.

Failures are environment failures, never authoring failures.
:class:`~workflow_coda.errors.RenderError` names the fix — install
``plotly``, or reinstall the framework. Selection policy operates at
read time over complete content; the renderer makes no axis decisions.
"""

import importlib.metadata
import importlib.resources
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from itertools import count
from typing import Final, Literal

from jinja2 import Environment, PackageLoader, StrictUndefined, TemplateNotFound
from markupsafe import Markup, escape

from .components import (
    FIGURE_DIV_CLASS,
    ComponentChrome,
    ComponentStatus,
    ThemeColorProperty,
)
from .errors import RenderError
from .icons import IconLibrary, IconSource
from .manifest import ArtifactStatus, ReportManifest
from .report import (
    CardEntry,
    ComponentEntry,
    Diagnostic,
    DiagnosticsEntry,
    DocumentNode,
    DocumentTab,
    EntryKind,
    GridEntry,
    ReportDocument,
    RowEntry,
    StatesEntry,
)
from .theme import ColorHex, Theme, ThemePair, ThemeToken

_ENV: Final[Environment] = Environment(
    loader=PackageLoader("workflow_coda", "templates"),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
    undefined=StrictUndefined,
)
"""The one Jinja environment: framework templates, escaping on, and
``StrictUndefined`` so a template bug is a loud error, never a silent
blank in the page."""


def _slugify(value: str) -> str:
    """Anchor ids from tab titles: lowercase, runs of non-alphanumerics
    collapse to one dash, stripped; a title with no anchor-able
    characters anchors as ``section``."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "section"


_ENV.filters["slugify"] = _slugify


def _css_tokens(
    theme: Theme,
    header_color: ThemeToken | tuple[ThemeToken, ThemeToken] | None,
    header_variant: Literal["fill", "gradient"] = "fill",
) -> str:
    """The ``:root`` custom-property block for one theme.

    One rule, no special cases: every theme color token becomes
    ``--coda-<token>``, the categorical palette becomes
    ``--coda-series-1..N``, and the two font stacks become
    ``--coda-font-body`` and ``--coda-font-heading``. Additional
    theme tokens become usable by plugin-supplied html automatically.

    Three properties derive rather than declare: ``--coda-text``,
    the theme's contrast-picked ink on the page background, and
    the header pair — ``--coda-header-background`` from the
    layout's header color token (``primary`` when the layout is
    silent), with ``--coda-header-text`` contrast-picked against
    the effective background. A theme that declares its own
    ``text``, ``header-background``, or ``header-text`` tokens
    wins: the loop above emitted them, and the derivation yields
    — the declared token rides through.
    """
    lines = [":root {"]
    for token, color in theme.colors.items():
        lines.append(f"  --coda-{token}: {color};")
    if "text" not in theme.colors:
        # The body ink is derived, not declared: the theme's
        # light-or-dark pair, contrast-picked against the page
        # background. A theme that still declares the retired
        # `text` token keeps its own ink — the loop above emitted
        # it, and a declared token wins.
        lines.append(f"  --coda-text: {theme.text_on(theme.colors['background'])};")
    header_backgrounds: tuple[ColorHex, ...]
    if "header-background" in theme.colors:
        # Preserve the established rule: a theme declaration wins.
        header_background = theme.colors["header-background"]
        header_backgrounds = (header_background,)
    elif header_variant == "gradient":
        if not isinstance(header_color, tuple) or len(header_color) != 2:
            raise ValueError("a gradient header requires two header_color references")
        stops = (
            theme.resolve_color("header_color", header_color[0]),
            theme.resolve_color("header_color", header_color[1]),
        )
        header_background = f"linear-gradient(135deg, {stops[0]}, {stops[1]})"
        header_backgrounds = stops
        lines.append(f"  --coda-header-background: {header_background};")
    else:
        if isinstance(header_color, tuple):
            raise ValueError("a solid header requires one header_color reference")
        reference = header_color if header_color is not None else "primary"
        header_background = theme.resolve_color("header_color", reference)
        header_backgrounds = (header_background,)
        lines.append(f"  --coda-header-background: {header_background};")

    if "header-text" not in theme.colors:
        lines.append(f"  --coda-header-text: {theme.text_on(*header_backgrounds)};")
    for index, color in enumerate(theme.series, start=1):
        lines.append(f"  --coda-series-{index}: {color};")
    lines.append(f"  --coda-font-body: {theme.font_body};")
    lines.append(f"  --coda-font-heading: {theme.font_heading};")
    lines.append("}")
    return "\n".join(lines)


def _css_theme_pair(
    pair: ThemePair,
    header_color: ThemeToken | tuple[ThemeToken, ThemeToken] | None,
    header_variant: Literal["fill", "gradient"] = "fill",
) -> str:
    """Both modes' custom properties, with light-only printing.

    Without JavaScript, screen styling follows the browser preference.
    A read-time controller may explicitly select a mode through
    data-coda-theme on the document element.

    All declarations derive independently, including optional page
    overrides, gradients, contrast-picked ink, series, and fonts.
    """

    def block(theme: Theme, selector: str, mode: str) -> str:
        generated = _css_tokens(theme, header_color, header_variant)
        generated = generated.replace(":root {", f"{selector} {{", 1)
        return generated.replace("\n}", f"\n  color-scheme: {mode};\n}}", 1)

    def inside_media(query: str, rule: str) -> str:
        indented = "\n".join(f"  {line}" for line in rule.splitlines())
        return f"@media {query} {{\n{indented}\n}}"

    return "\n\n".join(
        (
            block(pair.light, ":root", "light"),
            inside_media(
                "screen and (prefers-color-scheme: dark)",
                block(
                    pair.dark,
                    ":root:not([data-coda-theme])",
                    "dark",
                ),
            ),
            inside_media(
                "screen",
                "\n\n".join(
                    (
                        block(
                            pair.light,
                            ':root[data-coda-theme="light"]',
                            "light",
                        ),
                        block(
                            pair.dark,
                            ':root[data-coda-theme="dark"]',
                            "dark",
                        ),
                    )
                ),
            ),
            inside_media(
                "print",
                block(pair.light, ":root", "light"),
            ),
        )
    )


def _chrome_file(name: str) -> str:
    """Read framework chrome through the templates' package loader."""
    loader = _ENV.loader
    if loader is None:  # cannot happen: the environment is built with one
        raise RenderError("the renderer's template loader is not configured")
    try:
        source, _, _ = loader.get_source(_ENV, name)
    except TemplateNotFound as e:
        raise RenderError(
            f"the framework's report chrome file {name!r} is missing: "
            f"the workflow-coda installation is broken; reinstall it"
        ) from e
    return source


def _plotly_js() -> str:
    """The bundled Plotly.js library, read from the installed ``plotly``
    package for inlining when the document contains figures."""
    try:
        source = importlib.resources.files("plotly") / "package_data" / "plotly.min.js"
        return source.read_text(encoding="utf-8")
    except (ImportError, OSError) as e:
        raise RenderError(
            "the report contains figures, which the renderer inlines as "
            "Plotly.js from the installed plotly package — but plotly "
            "is not installed (or its bundled plotly.min.js cannot be "
            "read). Install plotly and build again"
        ) from e


@dataclass
class _PlacementColors:
    """Paired rules accumulated during one HTML walk."""

    properties: list[tuple[str, tuple[ThemeColorProperty, ...]]] = field(
        default_factory=list
    )

    def scope(self, entry: ComponentEntry) -> str:
        outcome = entry.outcome
        if (
            entry.kind is not EntryKind.RENDERED
            or outcome is None
            or outcome.status is not ComponentStatus.OK
            or not outcome.theme_colors
        ):
            return ""

        scope = f"coda-placement-{len(self.properties) + 1}"
        self.properties.append((scope, outcome.theme_colors))
        return f' data-coda-placement="{scope}"'

    def css(self) -> str:
        if not self.properties:
            return ""

        def rules(mode: str, prefix: str = "") -> str:
            blocks = []
            for scope, properties in self.properties:
                selector = f'{prefix}[data-coda-placement="{scope}"]'
                declarations = "\n".join(
                    f"  {prop.name}: {getattr(prop, mode)};" for prop in properties
                )
                blocks.append(f"{selector} {{\n{declarations}\n}}")
            return "\n\n".join(blocks)

        def media(query: str, body: str) -> str:
            indented = "\n".join(f"  {line}" for line in body.splitlines())
            return f"@media {query} {{\n{indented}\n}}"

        return "\n\n".join(
            (
                rules("light"),
                media(
                    "screen and (prefers-color-scheme: dark)",
                    rules("dark", ":root:not([data-coda-theme]) "),
                ),
                media(
                    "screen",
                    "\n\n".join(
                        (
                            rules("light", ':root[data-coda-theme="light"] '),
                            rules("dark", ':root[data-coda-theme="dark"] '),
                        )
                    ),
                ),
                media("print", rules("light")),
            )
        )


# ---------------------------------------------------------------------------
# Tree scans
# ---------------------------------------------------------------------------


def _walk_nodes(nodes: tuple[DocumentNode, ...]) -> Iterator[DocumentNode]:
    """Every node in the tree, depth-first, including all state panels."""
    for node in nodes:
        yield node
        if isinstance(node, (RowEntry, GridEntry, CardEntry)):
            yield from _walk_nodes(node.children)
        elif isinstance(node, StatesEntry):
            for panel in node.panels:
                yield from _walk_nodes(panel.children)


def _has_figures(document: ReportDocument) -> bool:
    """Whether any rendered component in the tree contains a figure.

    Detection keys on the framework's own figure marker — the class
    :meth:`RenderedComponent.from_figure` wraps its embedding in — so
    the renderer can never disagree with the constructor about what a
    figure is. ``html`` is optional on the outcome model, so it is
    narrowed inside the scan.
    """
    for tab in document.tabs:
        for node in _walk_nodes(tab.nodes):
            if (
                isinstance(node, ComponentEntry)
                and node.kind is EntryKind.RENDERED
                and node.outcome is not None
                and node.outcome.html is not None
                and FIGURE_DIV_CLASS in node.outcome.html
            ):
                return True
    return False


def _dropdown_icon(document: ReportDocument) -> str | None:
    """Load framework dropdown chrome independently of the plugin registry."""
    has_categorical_states = any(
        isinstance(node, StatesEntry) and node.kind == "categorical"
        for tab in document.tabs
        for node in _walk_nodes(tab.nodes)
    )
    if not has_categorical_states:
        return None

    library = IconLibrary((IconSource.for_plugin("core", "workflow_coda.core"),))
    return library.load("core-dropdown").markup


def _navigation_js(document: ReportDocument) -> str | None:
    """One merged navigation block, only for multiple tabs or states.

    The codec, pure policy, and selector planner load before the
    controller. Merging keeps the established script census.
    """
    has_states = any(
        isinstance(node, StatesEntry)
        for tab in document.tabs
        for node in _walk_nodes(tab.nodes)
    )
    if len(document.tabs) < 2 and not has_states:
        return None
    return "\n\n".join(
        _chrome_file(name)
        for name in (
            "selection_url.js",
            "selection_policy.js",
            "selection_widgets.js",
            "report.js",
        )
    )


def _iter_ratios(nodes: tuple[DocumentNode, ...]) -> Iterator[tuple[float, ...]]:
    """Every split ratio tuple in the tree, in traversal order.

    An unsplit row (or a card's unsplit row or grid) declares equal
    widths — one ratio per child — so the default is a ratio tuple
    like any other and the generated CSS covers it without special
    cases. Every state's children contribute their ratios.
    """
    for node in nodes:
        if isinstance(node, RowEntry):
            yield node.split if node.split is not None else (1.0,) * len(node.children)
            yield from _iter_ratios(node.children)
        elif isinstance(node, GridEntry):
            yield node.split
            yield from _iter_ratios(node.children)
        elif isinstance(node, CardEntry):
            if node.layout in ("row", "grid"):
                yield (
                    node.split
                    if node.split is not None
                    else (1.0,) * len(node.children)
                )
            yield from _iter_ratios(node.children)
        elif isinstance(node, StatesEntry):
            for panel in node.panels:
                yield from _iter_ratios(panel.children)


def _split_class(ratios: tuple[float, ...]) -> str:
    """The class name for one ratio tuple — ``[2, 1]`` →
    ``coda-split-2-1``; a fractional ratio renders its point as ``p``
    (``1.5`` → ``1p5``), keeping the name one valid identifier."""
    return "coda-split-" + "-".join(f"{value:g}".replace(".", "p") for value in ratios)


def _splits_css(document: ReportDocument) -> str:
    """The generated column rules for every distinct split in the tree.

    Ratios are data, so the rules are generated: one class per
    distinct ratio tuple, deduplicated, so every row, grid, and card
    layout that declares the same split shares one rule. The mobile
    default (one column) is one grouped rule; the ratios live inside a
    single ``min-width`` block, so the whole layout system collapses
    on small screens by construction.
    """
    ratios = list(
        dict.fromkeys(
            ratio for tab in document.tabs for ratio in _iter_ratios(tab.nodes)
        )
    )
    if not ratios:
        return ""
    lines = [
        "/* Generated from the layout's split ratios: one rule per "
        "distinct split; ratio layouts collapse to a single column "
        "below 48rem. */"
    ]
    mobile = ",\n".join(f".{_split_class(ratio)}" for ratio in ratios)
    lines.append(f"{mobile} {{\n  grid-template-columns: 1fr;\n}}")
    lines.append("@media (min-width: 48rem) {")
    for ratio in ratios:
        columns = " ".join(f"{value:g}fr" for value in ratio)
        lines.append(
            f"  .{_split_class(ratio)} {{ grid-template-columns: {columns}; }}"
        )
    lines.append("}")
    return "\n".join(lines)


def _component_css(document: ReportDocument) -> str:
    """The page's component style block, or ``''`` when no component
    contributed css.

    One ``<style>`` element placed after the framework stylesheet:
    each contribution under its ``/* <component id> */`` banner, in
    the document's first-use order. The strings are the plugins'
    own, guarded at declaration — the second raw-point family,
    alongside OK outcome html — so the block reaches the page
    verbatim, never escaped.
    """
    contributions = [c for c in document.chrome if c.css is not None]
    if not contributions:
        return ""
    body = "\n\n".join(f"/* {c.component_id} */\n{c.css}" for c in contributions)
    return f"<style>\n{body}\n</style>"


def _component_js(document: ReportDocument) -> str:
    """The page's component script block, or ``''`` when no component
    contributed js.

    One ``<script>`` element placed after the framework's own
    scripts, so the DOM is established when plugin code runs: each
    contribution under its ``// <component id>`` banner, in the
    document's first-use order. Enhancement-only script, per the
    contract — and raw into the page, like the css block.
    """
    contributions = [c for c in document.chrome if c.js is not None]
    if not contributions:
        return ""
    body = "\n\n".join(f"// {c.component_id} */\n{c.js}" for c in contributions)
    return f"<script>\n{body}\n</script>"


# ---------------------------------------------------------------------------
# The tree walk: nodes to body html
# ---------------------------------------------------------------------------


def _component_entry_html(
    entry: ComponentEntry,
    placement_colors: _PlacementColors | None = None,
) -> str:
    """One placed component, with optional placement-local color scope."""
    component_id = escape(entry.component_id)
    title = escape(entry.title)
    scope_attr = placement_colors.scope(entry) if placement_colors is not None else ""

    if entry.kind is EntryKind.RENDERED:
        outcome = entry.outcome
        assert outcome is not None  # the RENDERED pairing

        if outcome.status is ComponentStatus.OK:
            assert outcome.html is not None  # OK outcomes always carry html
            if entry.chrome is ComponentChrome.TILE:
                return (
                    f'<article class="coda-tile" '
                    f'data-component="{component_id}"{scope_attr}>'
                    f"{outcome.html}"
                    "</article>"
                )
            return (
                f'<article class="coda-card" '
                f'data-component="{component_id}"{scope_attr}>'
                f"<h3>{title}</h3>"
                f'<div class="coda-card-body">{outcome.html}</div>'
                "</article>"
            )

        if outcome.status is ComponentStatus.UNAVAILABLE:
            return (
                f'<article class="coda-card coda-card--notice" '
                f'data-component="{component_id}">'
                f"<h3>{title}</h3>"
                f"<p>{escape(outcome.message)}</p>"
                "</article>"
            )

        return ""  # SKIPPED

    assert entry.error is not None  # the FAILED pairing
    return (
        f'<article class="coda-card coda-card--failure" '
        f'data-component="{component_id}">'
        f"<h3>{title}</h3>"
        f"<p>{escape(entry.error)}</p>"
        "</article>"
    )


def _diagnostics_panel(problems: list[Diagnostic], notes: list[Diagnostic]) -> str:
    """The diagnostics panel: problems first, then notes — or the
    muted no-issues state when the ledger is empty, so a placed panel
    is always predictable."""
    parts = [
        '<section class="coda-diagnostics" aria-label="Diagnostics">',
        "<h2>Diagnostics</h2>",
    ]
    if not problems and not notes:
        parts.append('<p class="coda-diagnostics__empty">No issues.</p>')
    for heading, group in (("Problems", problems), ("Notes", notes)):
        if group:
            parts.append(f"<h3>{heading}</h3>")
            for diagnostic in group:
                kind = diagnostic.kind.value
                parts.append(
                    f'<p class="coda-diagnostic">'
                    f'<span class="coda-badge coda-badge--{kind}">{kind}</span>'
                    f"{escape(diagnostic.message)}</p>"
                )
    parts.append("</section>")
    return "".join(parts)


def _container_html(
    kind: str,
    children: tuple[DocumentNode, ...],
    split: tuple[float, ...] | None,
    panel_html: str,
    state_ids: Iterator[int],
    placement_colors: _PlacementColors,
) -> str:
    """A ratio container, carrying generated layout classes."""
    ratios = split if split is not None else (1.0,) * len(children)
    inner = "".join(
        _node_html(child, panel_html, state_ids, placement_colors) for child in children
    )
    return f'<div class="{kind} {_split_class(ratios)}">{inner}</div>'


def _states_html(
    entry: StatesEntry,
    panel_html: str,
    state_ids: Iterator[int],
    placement_colors: _PlacementColors,
) -> str:
    """Every expanded state panel, with escaped raw labels."""
    dimension = escape(entry.dimension)
    kind = escape(entry.kind)
    parts = [
        f'<div class="coda-states" data-states-dimension="{dimension}" '
        f'data-kind="{kind}">'
    ]

    for panel in entry.panels:
        panel_id = f"coda-state-{next(state_ids)}"
        value = escape(panel.value)
        parts.append(
            f'<section class="coda-state" id="{panel_id}" '
            f'data-state-dimension="{dimension}" data-state-value="{value}">'
            f"<h3>{value}</h3>"
        )
        parts.extend(
            _node_html(child, panel_html, state_ids, placement_colors)
            for child in panel.children
        )
        parts.append("</section>")

    parts.append("</div>")
    return "".join(parts)


def _node_html(
    node: DocumentNode,
    panel_html: str,
    state_ids: Iterator[int],
    placement_colors: _PlacementColors,
) -> str:
    """One document node as HTML."""
    if isinstance(node, ComponentEntry):
        return _component_entry_html(node, placement_colors)

    if isinstance(node, DiagnosticsEntry):
        return panel_html

    if isinstance(node, StatesEntry):
        return _states_html(node, panel_html, state_ids, placement_colors)

    if isinstance(node, RowEntry):
        return _container_html(
            "coda-row",
            node.children,
            node.split,
            panel_html,
            state_ids,
            placement_colors,
        )

    if isinstance(node, GridEntry):
        return _container_html(
            "coda-grid",
            node.children,
            node.split,
            panel_html,
            state_ids,
            placement_colors,
        )

    assert isinstance(node, CardEntry)
    title = f"<h3>{escape(node.title)}</h3>" if node.title is not None else ""

    if node.layout == "stack":
        inner = "".join(
            _node_html(child, panel_html, state_ids, placement_colors)
            for child in node.children
        )
    elif node.layout == "row":
        inner = _container_html(
            "coda-row",
            node.children,
            node.split,
            panel_html,
            state_ids,
            placement_colors,
        )
    else:
        inner = _container_html(
            "coda-grid",
            node.children,
            node.split,
            panel_html,
            state_ids,
            placement_colors,
        )

    return f'<div class="coda-group">{title}{inner}</div>'


def _tab_body(
    tab: DocumentTab,
    panel_html: str,
    state_ids: Iterator[int],
    placement_colors: _PlacementColors,
) -> Markup:
    """One tab's assembled body, preserving trusted plugin HTML."""
    return Markup(
        "".join(
            _node_html(node, panel_html, state_ids, placement_colors)
            for node in tab.nodes
        )
    )


# ---------------------------------------------------------------------------
# Provenance and assembly
# ---------------------------------------------------------------------------


def _provenance_lines(manifest: ReportManifest) -> list[str]:
    """The manifest's provenance, one line per fact, for the footer.

    Pinned to the manifest's envelope: the producer's identity and,
    when declared, its workflow module and run identifiers; the
    manifest schema version; and the artifact census — the pipeline's
    own record of itself, as the report's provenance record.
    """
    complete = sum(
        1
        for artifact in manifest.artifacts
        if artifact.status is ArtifactStatus.COMPLETE
    )
    lines = [f"Produced by {manifest.producer.name} {manifest.producer.version}"]
    if manifest.producer.module_id is not None:
        lines.append(f"Workflow module: {manifest.producer.module_id}")
    if manifest.producer.run_id is not None:
        lines.append(f"Run: {manifest.producer.run_id}")
    lines.append(f"Manifest schema version {manifest.schema_version}")
    lines.append(f"{complete} of {len(manifest.artifacts)} artifacts completed")
    return lines


def _attribution() -> str:
    """The footer's generated-by line, with the framework's version
    when installation metadata provides one."""
    try:
        version = importlib.metadata.version("workflow-coda")
    except importlib.metadata.PackageNotFoundError:
        return "This report was generated by workflow-coda."
    return f"This report was generated by workflow-coda {version}."


def render_report(document: ReportDocument) -> str:
    """Render one document to a complete, self-contained HTML page.

    Panel ids and placement-color scopes are local to this render call.
    """
    problem_diagnostics = [d for d in document.diagnostics if d.kind.is_problem]
    informational_diagnostics = [
        d for d in document.diagnostics if not d.kind.is_problem
    ]
    panel_html = _diagnostics_panel(
        problem_diagnostics,
        informational_diagnostics,
    )

    state_ids = count(1)
    placement_colors = _PlacementColors()

    # Rendering the bodies also collects placement-local color rules.
    tabs = [
        (
            tab,
            f"{index}-{_slugify(tab.title)}",
            _tab_body(tab, panel_html, state_ids, placement_colors),
        )
        for index, tab in enumerate(document.tabs, start=1)
    ]

    # Collect CSS only after every tab body has been rendered.
    css_layout = "\n\n".join(
        css
        for css in (
            _splits_css(document),
            placement_colors.css(),
        )
        if css
    )

    has_tabs = len(document.tabs) > 1
    return _ENV.get_template("report.html.jinja").render(
        document=document,
        tabs=tabs,
        has_tabs=has_tabs,
        css_tokens=_css_theme_pair(
            document.theme,
            document.header_color,
            document.header_variant,
        ),
        css_base=_chrome_file("style.css") + "\n" + _chrome_file("selection.css"),
        css_layout=css_layout,
        component_css=_component_css(document),
        plotly_js=_plotly_js() if _has_figures(document) else None,
        dropdown_icon=_dropdown_icon(document),
        theme_js=_chrome_file("theme.js"),
        report_js=_navigation_js(document),
        component_js=_component_js(document),
        provenance_lines=_provenance_lines(document.manifest),
        attribution=_attribution(),
    )
