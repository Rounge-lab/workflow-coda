"""Generated documentation gallery for framework-owned themes.

The public theme API owns discovery and loading. The docs-only preview
reuses the renderer's custom-property derivation to avoid maintaining
a second implementation of page and header ink selection.
"""

from html import escape
from importlib import resources
from pathlib import Path
from typing import ClassVar

from docutils import nodes
from sphinx.application import Sphinx
from sphinx.util.docutils import SphinxDirective

from workflow_coda.render import _css_tokens
from workflow_coda.theme import Theme, bundled_theme_names, load_bundled_theme


def _tokens(theme: Theme) -> list[tuple[str, str]]:
    """Declared colors and series, in their original order."""
    tokens = [(f"--coda-{name}", str(value)) for name, value in theme.colors.items()]
    tokens.extend(
        (f"--coda-series-{index}", str(value))
        for index, value in enumerate(theme.series, start=1)
    )
    return tokens


def _properties(theme: Theme) -> str:
    """Renderer-derived declarations for a preview-local style attribute."""
    lines = _css_tokens(theme, None).splitlines()
    declarations = " ".join(line.strip() for line in lines[1:-1])
    return escape(declarations, quote=True)


def _chart(theme: Theme) -> str:
    """Static illustrative bars, one for every categorical palette entry."""
    count = len(theme.series)
    width = count * 18
    bars = []
    for index, color in enumerate(theme.series, start=1):
        height = 24 + ((index - 1) % 5) * 12
        bars.append(
            f'<rect x="{(index - 1) * 18 + 2}" y="{90 - height}" '
            f'width="14" height="{height}" fill="{escape(color)}">'
            f"<title>series-{index}: {escape(color)}</title>"
            "</rect>"
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} 100" role="img" '
        'aria-label="Illustrative categorical palette; '
        'bar heights are sample values">'
        f"{''.join(bars)}</svg>"
    )


def _preview(theme: Theme) -> str:
    """One unscripted report-like preview, not an exact report rendering."""
    notices = "".join(
        f'<span class="coda-theme-gallery__notice" '
        f'style="background: {escape(theme.colors[token])}; '
        f'color: {escape(theme.text_on(theme.colors[token]))}">'
        f"{label}</span>"
        for token, label in (
            ("success", "Success"),
            ("warning", "Warning"),
            ("danger", "Danger"),
        )
    )
    return (
        '<div class="coda-theme-gallery__preview" '
        f'style="{_properties(theme)}">'
        '<div class="coda-theme-gallery__header">'
        "<strong>Example workflow</strong>"
        "<span>Illustrative report preview</span>"
        "</div>"
        '<div class="coda-theme-gallery__body">'
        '<div class="coda-theme-gallery__card">'
        '<strong class="coda-theme-gallery__heading">Run summary</strong>'
        "<p>Sample content for comparing palettes and typography.</p>"
        '<div class="coda-theme-gallery__metric">128'
        "<span> illustrative records</span></div>"
        f'<div class="coda-theme-gallery__notices">{notices}</div>'
        "</div>"
        '<div class="coda-theme-gallery__card">'
        '<strong class="coda-theme-gallery__heading">'
        "Categorical series</strong>"
        f"{_chart(theme)}"
        '<p class="coda-theme-gallery__muted">'
        "Illustrative palette preview; heights are not workflow data.</p>"
        "</div>"
        "</div></div>"
    )


def _swatches(theme: Theme) -> str:
    """Labeled chips; color is never the only way to identify an entry."""
    items = "".join(
        '<div class="coda-theme-gallery__swatch">'
        '<span class="coda-theme-gallery__chip" aria-hidden="true" '
        f'style="background: {escape(value)}"></span>'
        f"<code>{escape(name)}</code>"
        f'<code class="coda-theme-gallery__value">{escape(value)}</code>'
        "</div>"
        for name, value in _tokens(theme)
    )
    return f'<div class="coda-theme-gallery__swatches">{items}</div>'


def _palette_text(theme: Theme) -> nodes.definition_list:
    """Non-HTML fallback retaining the complete palette."""
    items = [
        nodes.definition_list_item(
            "",
            nodes.term("", name),
            nodes.definition("", nodes.literal(value, value)),
        )
        for name, value in _tokens(theme)
    ]
    return nodes.definition_list("", *items)


class BundledThemesDirective(SphinxDirective):
    """Generate previews and palette references for all bundled themes."""

    has_content: ClassVar[bool] = False

    def _dependencies(self, names: list[str]) -> None:
        """Track ordinary filesystem resources without extracting archives."""
        directory = resources.files("workflow_coda.theme") / "assets"
        if isinstance(directory, Path):
            # Directory changes also invalidate discovery when a theme
            # is added or removed.
            self.env.note_dependency(str(directory))
            for name in names:
                self.env.note_dependency(str(directory / f"{name}.yaml"))
        self.env.note_dependency(str(Path(__file__).resolve()))

    def run(self) -> list[nodes.Node]:
        names = sorted(bundled_theme_names())
        self._dependencies(names)
        sections: list[nodes.Node] = []
        is_html = self.env.app.builder.format == "html"

        for name in names:
            theme = load_bundled_theme(name)
            section = nodes.section(
                "",
                ids=[f"bundled-theme-{name}"],
                classes=["coda-theme-gallery"],
            )
            section += nodes.title("", name)
            section += nodes.paragraph("", f"Declaration display name: {theme.name}")
            section += nodes.paragraph("", f"Body font: {theme.font_body}")
            section += nodes.paragraph("", f"Heading font: {theme.font_heading}")
            if is_html:
                section += nodes.raw(
                    "", _preview(theme) + _swatches(theme), format="html"
                )
            else:
                section += _palette_text(theme)
            sections.append(section)

        return sections


def setup(app: Sphinx) -> dict[str, object]:
    """Register the gallery and its separate documentation stylesheet."""
    app.add_directive("bundled-themes", BundledThemesDirective)
    app.add_css_file("theme_gallery.css")
    return {
        "version": "0.1",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
