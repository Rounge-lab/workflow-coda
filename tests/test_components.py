"""Tests for the component contracts: the render outcome."""

import pytest
from helpers import assert_frozen_dataclass

from workflow_coda.components import ComponentStatus, RenderedComponent


class FakeFigure:
    """Plotly-shaped figure for testing ``from_figure``.

    Records the embedding flags so tests can pin the exact incantation
    the constructor applies.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def to_html(
        self, full_html: bool = True, include_plotlyjs: bool | str = "cdn"
    ) -> str:
        self.calls.append(
            {"full_html": full_html, "include_plotlyjs": include_plotlyjs}
        )
        return '<div class="plotly-graph-div"></div>'


# ---------------------------------------------------------------------------
# ok outcomes
# ---------------------------------------------------------------------------


def test_from_html_yields_ok() -> None:
    rendered = RenderedComponent.from_html("<p>Hello</p>")
    assert rendered.status is ComponentStatus.OK
    assert rendered.html == "<p>Hello</p>"
    assert rendered.message is None


def test_from_figure_applies_the_plotly_incantation() -> None:
    # The embedding flags live in the constructor, not in every plugin:
    # a bare <div> for the wrapper, no plotly.js bundle for the page.
    figure = FakeFigure()
    rendered = RenderedComponent.from_figure(figure)
    assert rendered.status is ComponentStatus.OK
    assert figure.calls == [{"full_html": False, "include_plotlyjs": False}]
    assert rendered.html == '<div class="plotly-graph-div"></div>'


def test_ok_requires_html() -> None:
    with pytest.raises(ValueError, match="requires html content"):
        RenderedComponent(status=ComponentStatus.OK, html=None)


def test_ok_rejects_blank_html() -> None:
    with pytest.raises(ValueError, match="visible content"):
        RenderedComponent(status=ComponentStatus.OK, html="   ")


def test_ok_rejects_message() -> None:
    with pytest.raises(ValueError, match="takes no message"):
        RenderedComponent(status=ComponentStatus.OK, html="<p/>", message="hi")


# ---------------------------------------------------------------------------
# unavailable outcomes
# ---------------------------------------------------------------------------


def test_unavailable_helper_yields_unavailable() -> None:
    rendered = RenderedComponent.unavailable("CheckV was not run")
    assert rendered.status is ComponentStatus.UNAVAILABLE
    assert rendered.message == "CheckV was not run"
    assert rendered.html is None


def test_unavailable_requires_message() -> None:
    with pytest.raises(ValueError, match="requires an explanation message"):
        RenderedComponent(status=ComponentStatus.UNAVAILABLE)


def test_unavailable_rejects_blank_message() -> None:
    with pytest.raises(ValueError, match="visible text"):
        RenderedComponent(status=ComponentStatus.UNAVAILABLE, message="   ")


def test_unavailable_rejects_html() -> None:
    with pytest.raises(ValueError, match="renders no html"):
        RenderedComponent(status=ComponentStatus.UNAVAILABLE, message="m", html="<p/>")


# ---------------------------------------------------------------------------
# skipped outcomes
# ---------------------------------------------------------------------------


def test_skipped_helper_yields_skipped() -> None:
    rendered = RenderedComponent.skipped()
    assert rendered.status is ComponentStatus.SKIPPED
    assert rendered.html is None
    assert rendered.message is None


def test_skipped_rejects_html() -> None:
    with pytest.raises(ValueError, match="carries no content"):
        RenderedComponent(status=ComponentStatus.SKIPPED, html="<p/>")


def test_skipped_rejects_message() -> None:
    with pytest.raises(ValueError, match="carries no content"):
        RenderedComponent(status=ComponentStatus.SKIPPED, message="nope")


# ---------------------------------------------------------------------------
# status type guard and value semantics
# ---------------------------------------------------------------------------


def test_status_must_be_enum_member() -> None:
    with pytest.raises(ValueError, match="must be a ComponentStatus member"):
        RenderedComponent(status="ok", html="<p/>")  # type: ignore[arg-type]


def test_rendered_components_compare_by_value_and_hash() -> None:
    first = RenderedComponent.from_html("<p/>")
    second = RenderedComponent.from_html("<p/>")
    assert first == second
    assert hash(first) == hash(second)


def test_rendered_component_is_frozen() -> None:
    rendered = RenderedComponent.from_html("<p/>")
    assert_frozen_dataclass(rendered, "html")


def test_rendered_component_rejects_new_attributes() -> None:
    # slots=True is contract here: plugins cannot stash state on the
    # outcome object.
    rendered = RenderedComponent.skipped()
    with pytest.raises(AttributeError):
        rendered.extra = "nope"  # type: ignore[attr-defined]
