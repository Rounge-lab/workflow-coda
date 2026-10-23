"""Theme-token swatches, auto-generated from the shipped default theme.

A docs-only Sphinx extension: one directive, ``.. theme-colors::``,
with no options and no content.  It imports the framework's shipped
``DEFAULT_THEME`` at build time and renders every color token as a
swatch — the colored chip, the ``--coda-<token>`` name, the declared
value — in the theme's own declared order, then the categorical
series palette as ``--coda-series-1..N``.  The theme is the single
source: this file copies nothing, so the reference can never drift
from what reports actually render.

The directive reads exactly the interface the renderer reads
(``theme.colors.items()``, ``theme.series``), so the swatches and
the generated page custom properties can never disagree.  House
rules apply: names and values are escaped; the import failure
teaches the fix; non-HTML builders get an honest text fallback; the
swatch style ships inside the directive's own raw html so the
extension needs no static-path or theme coupling in ``conf.py``.
"""

from html import escape
from typing import ClassVar

from docutils import nodes
from sphinx.application import Sphinx
from sphinx.util.docutils import SphinxDirective

_SWATCH_STYLE = """\
.coda-swatches {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(17rem, 1fr));
  gap: 0.5rem;
  margin: 1rem 0;
}

.coda-swatches__item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.5rem;
  border: 1px solid #ccc;
  border-radius: 4px;
}

.coda-swatches__chip {
  flex: none;
  width: 1.5rem;
  height: 1.5rem;
  border: 1px solid rgba(0, 0, 0, 0.3);
  border-radius: 4px;
}

.coda-swatches__name {
  font-weight: 600;
}

.coda-swatches__value {
  margin-left: auto;
}
"""


class ThemeColorsDirective(SphinxDirective):
    """``.. theme-colors::`` — the default theme's color tokens as
    swatches, read from the installed package at build time."""

    has_content: ClassVar[bool] = False

    def run(self) -> list[nodes.Node]:
        try:
            from workflow_coda.theme import DEFAULT_THEME
        except ImportError as e:
            message = (
                "theme-colors: cannot import workflow_coda — the "
                f"swatches read the real DEFAULT_THEME at build time "
                f"({e}); install the package in the docs environment "
                "and build again"
            )
            return [self.state.document.reporter.error(message)]
        tokens = [
            (f"--coda-{token}", str(color))
            for token, color in DEFAULT_THEME.colors.items()
        ]
        tokens.extend(
            (f"--coda-series-{index}", str(color))
            for index, color in enumerate(DEFAULT_THEME.series, start=1)
        )
        builder_format = getattr(self.env.app.builder, "format", "html")
        if builder_format != "html":
            return self._text(tokens)
        items = "".join(self._item(name, value) for name, value in tokens)
        page = (
            '<div class="coda-swatches">\n<style>\n'
            f"{_SWATCH_STYLE}</style>\n{items}</div>"
        )
        return [nodes.raw("", page, format="html")]

    @staticmethod
    def _item(name: str, value: str) -> str:
        """One swatch: the chip, the token name, the declared value."""
        return (
            '<div class="coda-swatches__item">'
            f'<span class="coda-swatches__chip" '
            f'style="background: {escape(value)}"></span> '
            f'<code class="coda-swatches__name">{escape(name)}</code> '
            f'<code class="coda-swatches__value">{escape(value)}</code>'
            "</div>\n"
        )

    @staticmethod
    def _text(tokens: list[tuple[str, str]]) -> list[nodes.Node]:
        """The non-HTML builder's honest fallback: the same tokens,
        as a definition list — no swatch colors, no silence."""
        items = [
            nodes.definition_list_item(
                "",
                nodes.term("", name),
                nodes.definition("", nodes.literal(value, value)),
            )
            for name, value in tokens
        ]
        return [nodes.definition_list("", *items)]


def setup(app: Sphinx) -> dict[str, object]:
    """Register the one directive; nothing else moves."""
    app.add_directive("theme-colors", ThemeColorsDirective)
    return {
        "version": "0.1",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
