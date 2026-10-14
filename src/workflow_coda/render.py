"""The report renderer: one report document in one self-contained
HTML page out.

Rendering is a pure function of the document.  The report builder has
already resolved plugins, gated versions, loaded the theme, and
embedded assets; the renderer reads the document plus the framework's
own chrome — Jinja templates and stylesheet shipped as package data —
and produces the page.  No registry, no user files, no decisions:
every branch the renderer takes is expressed in the document's types.

Two promises hold by construction:

**Self-containment.**  The finished page needs no network and no files
from the build machine.  The theme ships as generated CSS custom
properties in the page head; the stylesheet and Plotly.js, are inlined;
the logo and favicon are already data URIs; and
fonts are family lists rendered by whatever the reading machine has
installed (theme fonts never name fetched files).  Plotly.js is inlined
from the installed ``plotly`` package when — and only when — the
document contains figures; a report without figures stays small.

**The trust boundary.**  Autoescaping is on for every value the
templates print — titles, messages, diagnostics, provenance — and
exactly one plugin-owned point opts out: a rendered component's html,
marked safe inside the card macro.  Plugins are installed code; their
html is trusted.  The three framework-owned strings (two CSS blocks
and Plotly.js) are marked safe at their fixed points in the page
skeleton.

Failures are environment failures, never authoring failures.
:class:`~workflow_coda.errors.RenderError` names the fix — install
``plotly``, or reinstall the framework — and nothing else can go
wrong: with a validated document and shipped chrome, rendering has no
decision left to make.
"""

import importlib.metadata
import importlib.resources
import re
from typing import Final

from jinja2 import Environment, PackageLoader, StrictUndefined, TemplateNotFound

from .components import FIGURE_DIV_CLASS
from .errors import RenderError
from .manifest import ArtifactStatus, ReportManifest
from .report import Diagnostic, EntryKind, ReportDocument
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
    """Anchor ids from section titles: lowercase, runs of
    non-alphanumerics collapse to one dash, stripped; a title with no
    anchor-able characters anchors as ``section``."""
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
    """Read one of the framework's chrome files — the stylesheet or the
    figure bootstrap — through the same package loader as the
    templates, so chrome and templates always resolve from one place
    (editable installs included)."""
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


def _has_figures(document: ReportDocument) -> bool:
    """Whether any rendered entry contains a figure.

    Detection keys on the framework's own figure marker — the class
    :meth:`RenderedComponent.from_figure` wraps its embedding in — so
    the renderer can never disagree with the constructor about what a
    figure is.  ``html`` is optional on the outcome model (it is the
    ``OK`` status's pairing), so it is narrowed inside the scan.
    """
    for section in document.sections:
        for entry in section.entries:
            if (
                entry.kind is EntryKind.RENDERED
                and entry.outcome is not None
                and entry.outcome.html is not None
                and FIGURE_DIV_CLASS in entry.outcome.html
            ):
                return True
    return False


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
    has_figures = _has_figures(document)
    problem_diagnostics: list[Diagnostic] = [
        d for d in document.diagnostics if d.kind.is_problem
    ]
    informational_diagnostics: list[Diagnostic] = [
        d for d in document.diagnostics if not d.kind.is_problem
    ]
    return _ENV.get_template("report.html.jinja").render(
        document=document,
        css_tokens=_css_tokens(document.theme),
        css_base=_chrome_file("style.css"),
        plotly_js=_plotly_js() if has_figures else None,
        provenance_lines=_provenance_lines(document.manifest),
        attribution=_attribution(),
        problem_diagnostics=problem_diagnostics,
        informational_diagnostics=informational_diagnostics,
    )
