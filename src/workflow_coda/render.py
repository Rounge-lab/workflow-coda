"""The report renderer: one report document in one self-contained
HTML page out.

Rendering is a pure function of the document.  The report builder has
already resolved plugins, gated versions, loaded the theme, and
embedded assets; the renderer reads the document plus the framework's
own chrome — Jinja templates, stylesheet, tab script shipped as
package data — and produces the page.  No registry, no user files, no
decisions: every branch the renderer takes is expressed in the
document's types.

Two responsibilities meet here:

**The tree walk** (:func:`_node_html` and friends) turns each tab's
node tree into body html — the card vocabulary for placed components,
the group box for cards, the ratio containers for rows and grids, the
diagnostics panel at its markers.  The walk escapes every framework
text it interpolates (titles, messages, errors) and leaves exactly one
raw point: a rendered component's plugin html, trusted because
plugins are installed code.  Tabs become the page's navigation: one
panel per tab, a tab bar generated from them when there is more than
one, and single-tab reports render no bar and no script.

**Generated layout CSS** (:func:`_splits_css`) turns the tree's split
ratios into deduplicated rules — one class per distinct ratio tuple,
grouped mobile defaults, ratios inside one ``min-width`` block — so
every ratio layout collapses to a single column on small screens by
construction, with no inline styles and no ``!important``.

Self-containment holds as before: the theme ships as generated CSS
custom properties, the stylesheet, split rules, and tab script are
inlined, the logo and favicon are data URIs, and Plotly.js is inlined
from the installed ``plotly`` package exactly when the document
contains figures.  A single-tab, figure-free report inlines no
``<script>`` at all.

Failures are environment failures, never authoring failures.
:class:`~workflow_coda.errors.RenderError` names the fix — install
``plotly``, or reinstall the framework — and nothing else can go
wrong: with a validated document and shipped chrome, rendering has no
decision left to make.
"""

import importlib.metadata
import importlib.resources
import re
from collections.abc import Iterator
from typing import Final

from jinja2 import Environment, PackageLoader, StrictUndefined, TemplateNotFound
from markupsafe import Markup, escape

from .components import FIGURE_DIV_CLASS, ComponentChrome, ComponentStatus
from .errors import RenderError
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
)
from .theme import Theme

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


def _css_tokens(theme: Theme) -> str:
    """The ``:root`` custom-property block for one theme.

    One rule, no special cases: every theme color token becomes
    ``--coda-<token>``, the categorical palette becomes
    ``--coda-series-1..N``, and the two font stacks become
    ``--coda-font-body`` and ``--coda-font-heading``.  Additional
    theme tokens become usable by plugin-supplied html automatically.
    """
    lines = [":root {"]
    for token, color in theme.colors.items():
        lines.append(f"  --coda-{token}: {color};")
    for index, color in enumerate(theme.series, start=1):
        lines.append(f"  --coda-series-{index}: {color};")
    lines.append(f"  --coda-font-body: {theme.font_body};")
    lines.append(f"  --coda-font-heading: {theme.font_heading};")
    lines.append("}")
    return "\n".join(lines)


def _chrome_file(name: str) -> str:
    """Read one of the framework's chrome files — the stylesheet, the
    tab script, or the figure bootstrap — through the same package
    loader as the templates, so chrome and templates always resolve
    from one place (editable installs included)."""
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
            "read).  Install plotly and build again"
        ) from e


# ---------------------------------------------------------------------------
# Tree scans
# ---------------------------------------------------------------------------


def _walk_nodes(nodes: tuple[DocumentNode, ...]) -> Iterator[DocumentNode]:
    """Every node in the tree, depth-first, for tree-wide scans."""
    for node in nodes:
        yield node
        if isinstance(node, (RowEntry, GridEntry, CardEntry)):
            yield from _walk_nodes(node.children)


def _has_figures(document: ReportDocument) -> bool:
    """Whether any rendered component in the tree contains a figure.

    Detection keys on the framework's own figure marker — the class
    :meth:`RenderedComponent.from_figure` wraps its embedding in — so
    the renderer can never disagree with the constructor about what a
    figure is.  ``html`` is optional on the outcome model, so it is
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


def _iter_ratios(nodes: tuple[DocumentNode, ...]) -> Iterator[tuple[float, ...]]:
    """Every split ratio tuple in the tree, in traversal order.

    An unsplit row (or a card's unsplit row or grid) declares equal
    widths — one ratio per child — so the default is a ratio tuple
    like any other and the generated CSS covers it without special
    cases.
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


def _split_class(ratios: tuple[float, ...]) -> str:
    """The class name for one ratio tuple — ``[2, 1]`` →
    ``coda-split-2-1``; a fractional ratio renders its point as ``p``
    (``1.5`` → ``1p5``), keeping the name one valid identifier."""
    return "coda-split-" + "-".join(f"{value:g}".replace(".", "p") for value in ratios)


def _splits_css(document: ReportDocument) -> str:
    """The generated column rules for every distinct split in the tree.

    Ratios are data, so the rules are generated: one class per
    distinct ratio tuple, deduplicated, so every row, grid, and card
    layout that declares the same split shares one rule.  The mobile
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


# ---------------------------------------------------------------------------
# The tree walk: nodes to body html
# ---------------------------------------------------------------------------


def _component_entry_html(entry: ComponentEntry) -> str:
    """One placed component — the honest visual grammar.

    A skipped outcome renders nothing at all.  A CARD component
    renders in the framework's card vocabulary: the title, then the
    plugin's body.  A TILE component that rendered painted its own
    card — title, plate, corners — and the framework contributes
    only the ``data-component`` wrapper.  Degradation is the
    framework's own vocabulary in both modes: an unavailable or
    failed render, tile or card, teaches in place — the plugin is
    not rendering.  Every framework text is escaped; the OK
    outcome's plugin html is the walk's single raw point.
    """
    component_id = escape(entry.component_id)
    title = escape(entry.title)
    if entry.kind is EntryKind.RENDERED:
        outcome = entry.outcome
        assert outcome is not None  # the RENDERED pairing
        if outcome.status is ComponentStatus.OK:
            assert outcome.html is not None  # OK outcomes always carry html
            if entry.chrome is ComponentChrome.TILE:
                return (
                    f'<article class="coda-tile" data-component="{component_id}">'
                    f"{outcome.html}"
                    "</article>"
                )
            return (
                f'<article class="coda-card" data-component="{component_id}">'
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
        return ""  # SKIPPED: no card; the surrounding flow shows where it sat
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
                kind = diagnostic.kind.value  # framework vocabulary, not text
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
) -> str:
    """A ratio container (row or grid): the generated split class
    carries the widths; the structural grid lives in the stylesheet."""
    ratios = split if split is not None else (1.0,) * len(children)
    inner = "".join(_node_html(child, panel_html) for child in children)
    return f'<div class="{kind} {_split_class(ratios)}">{inner}</div>'


def _node_html(node: DocumentNode, panel_html: str) -> str:
    """One document node as html — the tree walk's dispatch."""
    if isinstance(node, ComponentEntry):
        return _component_entry_html(node)
    if isinstance(node, DiagnosticsEntry):
        return panel_html
    if isinstance(node, RowEntry):
        return _container_html("coda-row", node.children, node.split, panel_html)
    if isinstance(node, GridEntry):
        return _container_html("coda-grid", node.children, node.split, panel_html)
    assert isinstance(node, CardEntry)  # the node union is exhausted
    title = f"<h3>{escape(node.title)}</h3>" if node.title is not None else ""
    if node.layout == "stack":
        inner = "".join(_node_html(child, panel_html) for child in node.children)
    elif node.layout == "row":
        inner = _container_html("coda-row", node.children, node.split, panel_html)
    else:
        inner = _container_html("coda-grid", node.children, node.split, panel_html)
    return f'<div class="coda-group">{title}{inner}</div>'


def _tab_body(tab: DocumentTab, panel_html: str) -> Markup:
    """One tab's node tree as assembled body html: framework chrome
    throughout, every framework text escaped by the walk, and exactly
    one raw point inside (a rendered component's plugin html)."""
    return Markup("".join(_node_html(node, panel_html) for node in tab.nodes))


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
    """Render *document* to one complete, self-contained HTML page.

    Pure: the result is fully determined by the document and the
    framework's shipped chrome.  Callers own writing the string
    wherever it goes.

    Raises :class:`~workflow_coda.errors.RenderError` only on
    environment failures; see the module docstring.
    """
    problem_diagnostics = [d for d in document.diagnostics if d.kind.is_problem]
    informational_diagnostics = [
        d for d in document.diagnostics if not d.kind.is_problem
    ]
    panel_html = _diagnostics_panel(problem_diagnostics, informational_diagnostics)
    tabs = [
        (
            tab,
            f"{index}-{_slugify(tab.title)}",
            _tab_body(tab, panel_html),
        )
        for index, tab in enumerate(document.tabs, start=1)
    ]
    has_tabs = len(document.tabs) > 1
    return _ENV.get_template("report.html.jinja").render(
        document=document,
        tabs=tabs,
        has_tabs=has_tabs,
        css_tokens=_css_tokens(document.theme),
        css_base=_chrome_file("style.css"),
        css_layout=_splits_css(document),
        plotly_js=_plotly_js() if _has_figures(document) else None,
        report_js=_chrome_file("report.js") if has_tabs else None,
        provenance_lines=_provenance_lines(document.manifest),
        attribution=_attribution(),
    )
