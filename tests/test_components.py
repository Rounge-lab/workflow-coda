"""Tests for the component contracts: the render outcome."""

import pytest
from factories import make_component, make_metadata, noop_render
from helpers import assert_frozen_dataclass

from workflow_coda.components import (
    ComponentStatus,
    RenderedComponent,
    has_visible_text,
)


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


# ---------------------------------------------------------------------------
# ReportComponent declarations
# ---------------------------------------------------------------------------


def test_component_defaults_round_trip() -> None:
    component = make_component()
    assert component.id == "example.quality"
    assert component.title == "Quality overview"
    assert component.description is None
    assert component.render is noop_render


def test_component_accepts_description() -> None:
    component = make_component(description="Per-sample QC summary")
    assert component.description == "Per-sample QC summary"


@pytest.mark.parametrize(
    "id",
    [
        "quality",  # no dot: missing plugin prefix
        "example.quality.extra",  # two dots
        "example.QUALITY",  # uppercase in the name half
        "Example.quality",  # uppercase in the prefix half
        "example.1quality",  # digit-leading name half
        "example.q-uality",  # hyphen in the name half
        "example.",  # empty name half
        ".quality",  # empty prefix half
        "example quality",  # space
        "",  # empty
    ],
)
def test_component_rejects_malformed_ids(id: str) -> None:
    with pytest.raises(ValueError, match="invalid component id"):
        make_component(id=id)


def test_component_requires_visible_title() -> None:
    with pytest.raises(ValueError, match="title must contain visible text"):
        make_component(title="   ")


def test_component_rejects_blank_description() -> None:
    with pytest.raises(ValueError, match="description must contain visible text"):
        make_component(description="   ")


def test_component_rejects_non_callable_render() -> None:
    with pytest.raises(ValueError, match="render must be a callable"):
        make_component(render="<p/>")  # type: ignore[arg-type]


def test_components_compare_by_value_and_hash() -> None:
    # Equality is by fields, but render callables compare by identity, so
    # value-equal components share the same renderer — which is what the
    # builder relies on when looking components up.
    first = make_component()
    second = make_component()
    assert first == second
    assert first.render is second.render  # both default to noop_render
    assert hash(first) == hash(second)


def test_component_is_frozen() -> None:
    assert_frozen_dataclass(make_component(), "title")


def test_component_rejects_new_attributes() -> None:
    with pytest.raises(AttributeError):
        make_component().extra = "nope"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# PluginMetadata declarations
# ---------------------------------------------------------------------------


def test_metadata_defaults_round_trip() -> None:
    metadata = make_metadata()
    assert metadata.id == "example"
    assert metadata.name == "Example plugin"
    assert metadata.version == "1.0.0"
    assert metadata.description == "Components for the test suite."
    assert metadata.supported_schema_versions == frozenset({"0.1.0"})


@pytest.mark.parametrize(
    "id",
    ["Example", "example-plugin", "example plugin", "1example", "", "_example"],
)
def test_metadata_rejects_malformed_ids(id: str) -> None:
    with pytest.raises(ValueError, match="invalid plugin id"):
        make_metadata(id=id)


def test_metadata_requires_visible_text_fields() -> None:
    for field in ("name", "version", "description"):
        with pytest.raises(
            ValueError, match=rf"plugin 'example': {field} must contain visible text"
        ):
            make_metadata(**{field: "   "})


def test_metadata_requires_at_least_one_schema_version() -> None:
    with pytest.raises(ValueError, match="at least one manifest schema version"):
        make_metadata(supported_schema_versions=())


def test_metadata_accepts_multiple_schema_versions() -> None:
    metadata = make_metadata(supported_schema_versions=["0.1.0", "0.2.0"])
    assert metadata.supported_schema_versions == frozenset({"0.1.0", "0.2.0"})


def test_metadata_is_frozen_and_hashable() -> None:
    first = make_metadata()
    second = make_metadata()
    assert first == second
    assert hash(first) == hash(second)
    assert_frozen_dataclass(first, "name")


def test_metadata_rejects_new_attributes() -> None:
    with pytest.raises(AttributeError):
        make_metadata().extra = "nope"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", False),
        ("   ", False),
        ("\t\n ", False),
        ("x", True),
        ("  provenance  ", True),
        ("0", True),
    ],
)
def test_has_visible_text(text: str, expected: bool) -> None:
    # The shared predicate behind both the component gates and the
    # layout model's VisibleText validator.
    assert has_visible_text(text) is expected
