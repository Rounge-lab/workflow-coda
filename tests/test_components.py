"""Tests for the component contracts: the render outcome."""

import re

import pytest
from factories import make_component, make_metadata, noop_render, stub_figure
from helpers import assert_frozen_dataclass

from workflow_coda.components import (
    PLACEMENT_KEYS,
    ComponentChrome,
    ComponentStatus,
    PlacementInfo,
    RenderedComponent,
    reject_unknown_parameters,
)
from workflow_coda.layout import ComponentPlacement

# ---------------------------------------------------------------------------
# ok outcomes
# ---------------------------------------------------------------------------


def test_from_html_yields_ok() -> None:
    rendered = RenderedComponent.from_html("<p>Hello</p>")
    assert rendered.status is ComponentStatus.OK
    assert rendered.html == "<p>Hello</p>"
    assert rendered.message is None


def test_ok_requires_html() -> None:
    with pytest.raises(ValueError, match="requires html content"):
        RenderedComponent(status=ComponentStatus.OK, html=None)


def test_ok_rejects_blank_html() -> None:
    with pytest.raises(ValueError, match="visible content"):
        RenderedComponent(status=ComponentStatus.OK, html="   ")


def test_ok_rejects_message() -> None:
    with pytest.raises(ValueError, match="takes no message"):
        RenderedComponent(status=ComponentStatus.OK, html="<p/>", message="hi")


def test_from_figure_pins_the_embedding_flags() -> None:
    figure = stub_figure()
    outcome = RenderedComponent.from_figure(figure, description="Depth per sample")
    assert outcome.status is ComponentStatus.OK
    assert figure.full_html is False
    assert figure.include_plotlyjs is False
    assert figure.config == {"responsive": True}


def test_from_figure_wraps_the_plot_in_the_framework_marker() -> None:
    outcome = RenderedComponent.from_figure(
        stub_figure("<div>the plot</div>"), description="Depth per sample"
    )
    assert outcome.html == (
        '<div class="coda-figure" role="img" aria-label="Depth per sample">'
        "<div>the plot</div></div>"
    )


def test_from_figure_without_description_wraps_unlabelled() -> None:
    # Optional by design: the accessibility label is the plugin's
    # decision — required for framework-owned components, trusted for
    # third parties.  Omitted, the plot carries no role/aria-label.
    outcome = RenderedComponent.from_figure(stub_figure("<div>the plot</div>"))
    assert outcome.html == ('<div class="coda-figure" ><div>the plot</div></div>')


def test_from_figure_requires_a_visible_description_when_given() -> None:
    with pytest.raises(ValueError, match="must contain visible text"):
        RenderedComponent.from_figure(stub_figure(), description="   ")


def test_from_figure_escapes_the_description_for_the_attribute() -> None:
    outcome = RenderedComponent.from_figure(stub_figure(), description='Say "10x"')
    assert outcome.html is not None  # OK outcomes always carry html
    assert 'aria-label="Say &quot;10x&quot;"' in outcome.html


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
# PlacementInfo: the render call's placement facts
# ---------------------------------------------------------------------------


def test_placement_info_round_trip() -> None:
    info = PlacementInfo(title="Mean depth")
    assert info.title == "Mean depth"


def test_placement_infos_compare_by_value_and_hash() -> None:
    # The builder resolves one per render call; value semantics keep
    # equality pins honest.
    assert PlacementInfo(title="Mean depth") == PlacementInfo(title="Mean depth")
    assert hash(PlacementInfo(title="x")) == hash(PlacementInfo(title="x"))
    assert PlacementInfo(title="x") != PlacementInfo(title="y")


def test_placement_info_is_frozen_and_slotted() -> None:
    info = PlacementInfo(title="Mean depth")
    assert_frozen_dataclass(info, "title")
    with pytest.raises(AttributeError):
        info.extra = "nope"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# ComponentChrome: who paints a component's chrome
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "member"),
    [("card", ComponentChrome.CARD), ("tile", ComponentChrome.TILE)],
)
def test_component_chrome_wire_values(value: str, member: ComponentChrome) -> None:
    # Lowercase wire values, like the status and diagnostic kinds:
    # they name vocabulary in messages and CSS classes.
    assert member.value == value
    assert ComponentChrome(value) is member


# ---------------------------------------------------------------------------
# Page chrome declarations: css and js
# ---------------------------------------------------------------------------


def test_components_default_to_no_page_chrome() -> None:
    # The channel is opt-in at the declaration: a simple plugin never
    # sees it, and every pre-channel declaration stands unchanged.
    component = make_component()
    assert component.css is None
    assert component.js is None


def test_components_accept_css_and_js_verbatim() -> None:
    # The strings are the plugin's own to write; the declaration
    # guards are the only interpretation made of them.
    css = ".coda-example-quality { color: inherit; }"
    js = "console.log('example.quality enhanced');"
    component = make_component(css=css, js=js)
    assert component.css == css
    assert component.js == js


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_chrome_is_rejected_when_given(blank: str) -> None:
    # A declared-but-blank contribution would inline as a bare banner
    # comment with nothing under it; blank means "not given".
    with pytest.raises(ValueError, match="css must not be blank when given"):
        make_component(css=blank)
    with pytest.raises(ValueError, match="js must not be blank when given"):
        make_component(js=blank)


def test_css_breakout_is_rejected_at_declaration() -> None:
    # '</style' would terminate the report's inline style block early
    # and corrupt the page — a declaration-time teaching error, the
    # same boundary as the id-shape checks.
    with pytest.raises(ValueError, match="css must not contain '</style'"):
        make_component(css='p::after { content: "</style>"; }')


def test_js_breakout_is_rejected_at_declaration() -> None:
    with pytest.raises(ValueError, match="js must not contain '</script'"):
        make_component(js="document.write('</script>');")


@pytest.mark.parametrize("sequence", ["</style>", "</STYLE>", "</Style"])
def test_css_guard_matches_case_insensitively(sequence: str) -> None:
    # The HTML tokenizer ends an inline block on '</STYLE' as readily
    # as '</style'; the guard matches what the tokenizer would.
    with pytest.raises(ValueError, match="css must not contain"):
        make_component(css=f".sel::after {{ content: {sequence!r} }}")


@pytest.mark.parametrize("sequence", ["</script>", "</SCRIPT>"])
def test_js_guard_matches_case_insensitively(sequence: str) -> None:
    with pytest.raises(ValueError, match="js must not contain"):
        make_component(js=f"document.write({sequence!r});")


def test_breakout_guards_teach_the_escapes() -> None:
    # Both escapes are real, in their own languages: '\<' is a CSS
    # string escape for '<', '<\/script' the JS idiom — each reads
    # back as the original sequence in its own language while the
    # bytes the HTML tokenizer scans never contain the closing form.
    with pytest.raises(ValueError, match=re.escape("escape the '<' as '\\<'")):
        make_component(css='p::after { content: "</style>"; }')
    with pytest.raises(ValueError, match=re.escape("escape it as '<\\/script'")):
        make_component(js="document.write('</script>');")


def test_chrome_fields_participate_in_equality() -> None:
    # css and js are real contract fields, not decoration: a component
    # that declares chrome is not its chrome-less twin.
    assert make_component() != make_component(css=".coda-example-quality { }")
    assert make_component() != make_component(js="console.log('hi');")


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


def test_component_defaults_to_card_chrome() -> None:
    # The default keeps every existing declaration valid; TILE is a
    # declaration, never a surprise.
    assert make_component().chrome is ComponentChrome.CARD


def test_component_accepts_tile_chrome() -> None:
    component = make_component(chrome=ComponentChrome.TILE)
    assert component.chrome is ComponentChrome.TILE


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


# ---------------------------------------------------------------------------
# Parameter vocabulary teaching
# ---------------------------------------------------------------------------

_ACCEPTED = frozenset({"artifact", "color", "key"})


def test_accepted_keys_pass_silently() -> None:
    # The helper is a no-op when the block is clean — the common case.
    reject_unknown_parameters("example.hello", {"artifact": "x"}, _ACCEPTED)


def test_unknown_keys_teach_the_vocabulary() -> None:
    with pytest.raises(ValueError, match="the accepted parameters are"):
        reject_unknown_parameters("example.hello", {"explode": 1}, _ACCEPTED)
    with pytest.raises(ValueError, match="'artifact', 'color', 'key'"):
        reject_unknown_parameters("example.hello", {"explode": 1}, _ACCEPTED)


def test_typos_get_a_closest_match_suggestion() -> None:
    with pytest.raises(ValueError, match="did you mean 'color'"):
        reject_unknown_parameters("example.hello", {"colour": "red"}, _ACCEPTED)


def test_placement_keys_teach_the_move() -> None:
    # The trap the helper exists for: a policy or title nested inside
    # parameters is inert without this — teach the move instead.
    with pytest.raises(
        ValueError, match="move it out of 'parameters:' to the placement level"
    ):
        reject_unknown_parameters(
            "example.hello", {"on_unavailable": "skip"}, _ACCEPTED
        )
    with pytest.raises(ValueError, match="move it out of 'parameters:'"):
        reject_unknown_parameters("example.hello", {"title": "x"}, _ACCEPTED)


def test_every_unknown_key_reports_in_one_error() -> None:
    # One pass, one error: every offender is named, with its own
    # teaching line — substring pins, robust to listing order.
    with pytest.raises(ValueError) as excinfo:
        reject_unknown_parameters(
            "example.hello", {"on_missing": "skip", "colour": "red"}, _ACCEPTED
        )
    message = str(excinfo.value)
    assert "did you mean 'color'?" in message
    assert "'on_missing' is a placement key" in message
    assert "the accepted parameters are" in message


def test_placement_keys_mirror_the_placement_model() -> None:
    # The helper teaches placement keys by name; the layout grammar
    # owns them.  This pin keeps the mirror from drifting when the
    # grammar grows a placement key.
    assert PLACEMENT_KEYS == frozenset(ComponentPlacement.model_fields)
