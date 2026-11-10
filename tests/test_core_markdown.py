"""Tests for core.markdown: author prose with artifact-backed variables.

The component's contract, executable: a closed parameter vocabulary
(``artifact`` optional, ``text`` required), template variables
resolving directly against the artifact's top-level keys, values
rendering as text — never markup — and a strict markdown subset
taught at the parse boundary.  Every pin drives the component
through the shipped roster, so the registration is under test too.
"""

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from factories import make_artifact_payload, make_manifest_payload

from workflow_coda.artifact_store import ArtifactStore, JsonValue
from workflow_coda.components import (
    ComponentChrome,
    ComponentStatus,
    PlacementInfo,
    RenderedComponent,
    ReportComponent,
)
from workflow_coda.context import RenderContext
from workflow_coda.core.plugin import get_plugin
from workflow_coda.manifest import ReportManifest

STATS = '{"n_samples": 3, "run_id": "run-42", "depth": 12.5, "flag": true}'
"""The stats artifact the variable pins read from."""


def _markdown() -> ReportComponent:
    """core.markdown off the shipped roster — every pin's door, so
    the roster line is under test too."""
    for component in get_plugin().components:
        if component.id == "core.markdown":
            return component
    pytest.fail("core.markdown is not on the core roster")


def _render(
    store: ArtifactStore, parameters: Mapping[str, JsonValue]
) -> RenderedComponent:
    """One render call against a real context and placement."""
    return _markdown().render(
        RenderContext(store=store),
        PlacementInfo(title="Prose"),
        parameters,
    )


def _store(tmp_path: Path, stats: str | None = None) -> ArtifactStore:
    """A store; *stats*, when given, becomes a declared complete
    JSON artifact written as its own file."""
    if stats is not None:
        (tmp_path / "stats.json").write_text(stats, encoding="utf-8")
    artifacts = (
        [
            make_artifact_payload(
                id="stats",
                type="org.example.stats",
                path="stats.json",
                format="json",
            )
        ]
        if stats is not None
        else []
    )
    manifest = ReportManifest.model_validate(make_manifest_payload(artifacts=artifacts))
    return ArtifactStore(manifest, tmp_path)


# ---------------------------------------------------------------------------
# The roster
# ---------------------------------------------------------------------------


def test_markdown_is_on_the_core_roster() -> None:
    # The author's door: one prose component on the shipped roster,
    # CARD chrome — the framework's card owns the heading — with
    # self-hosted styles and no script: prose is static content.
    component = _markdown()
    assert component.id == "core.markdown"
    assert component.title == "Prose"
    assert component.chrome is ComponentChrome.CARD
    assert component.css is not None
    assert ".coda-prose" in component.css  # the scoped vocabulary
    assert component.js is None


# ---------------------------------------------------------------------------
# The parameter grammar
# ---------------------------------------------------------------------------


def test_unknown_parameter_teaches_with_the_closest_match(tmp_path: Path) -> None:
    # The closed vocabulary law, shared by the roster: a typo'd key
    # teaches with a suggestion before any data is touched.
    with pytest.raises(ValueError, match="did you mean 'text'"):
        _render(_store(tmp_path), {"txt": "hello"})


def test_a_nested_placement_key_teaches_the_move(tmp_path: Path) -> None:
    # The field-agnostic trap machinery: on_unavailable is a
    # placement key, not a component parameter.
    with pytest.raises(ValueError, match="placement key"):
        _render(_store(tmp_path), {"text": "hello", "on_unavailable": "notice"})


def test_text_is_required(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="core.markdown"):
        _render(_store(tmp_path), {"artifact": "org.example.stats"})


def test_text_must_be_visible(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="core.markdown"):
        _render(_store(tmp_path), {"text": "   "})


def test_a_non_json_artifact_teaches_the_format_gate(tmp_path: Path) -> None:
    # The same gate as the roster's siblings: core.markdown reads
    # JSON artifacts.
    (tmp_path / "stats.txt").write_text("n_samples: 3", encoding="utf-8")
    manifest = ReportManifest.model_validate(
        make_manifest_payload(
            artifacts=[
                make_artifact_payload(
                    id="stats",
                    type="org.example.stats",
                    path="stats.txt",
                    format="txt",
                )
            ]
        )
    )
    with pytest.raises(ValueError, match="JSON"):
        _render(
            ArtifactStore(manifest, tmp_path),
            {"artifact": "org.example.stats", "text": "{{ n_samples }}"},
        )


# ---------------------------------------------------------------------------
# The variables: values from the artifact, text into the prose
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "rendered"),
    [
        ("n_samples", "3"),  # integers render as written
        ("depth", "12.5"),  # floats render as written
        ("run_id", "run-42"),  # strings pass through verbatim
        ("flag", "true"),  # booleans render as JSON literals
    ],
)
def test_scalars_substitute_as_text(tmp_path: Path, key: str, rendered: str) -> None:
    # The design's example line: the template lives in the layout,
    # the values come from the artifact, plain text in place.
    outcome = _render(
        _store(tmp_path, STATS),
        {"text": "**{{ " + key + " }}**"},
    )
    assert outcome.status is ComponentStatus.OK
    assert outcome.html is not None
    assert f"<strong>{rendered}</strong>" in outcome.html


def test_variables_substitute_without_inner_spaces(tmp_path: Path) -> None:
    # '{{depth}}' and '{{ depth }}' are the same variable: both
    # spellings will be written, so both resolve.
    outcome = _render(_store(tmp_path, STATS), {"text": "Depth {{depth}} x"})
    assert outcome.html is not None
    assert "Depth 12.5 x" in outcome.html


@pytest.mark.parametrize(
    ("value", "forbidden", "survives"),
    [
        ("*not emphasis*", "<em>", "*not emphasis*"),
        ("**not strong**", "<strong>", "**not strong**"),
        ("`not code`", "<code>", "`not code`"),
        ("<script>alert(1)</script>", "<script>", "&lt;script&gt;"),
    ],
)
def test_values_are_text_never_markup(
    tmp_path: Path, value: str, forbidden: str, survives: str
) -> None:
    # The values-as-text law: substitution happens before parsing,
    # so an unescaped value could re-parse as markup — data would
    # be injecting presentation.  The value's characters render
    # (escaped); no markup interpretation survives.
    stats = '{"note": ' + json.dumps(value) + "}"
    outcome = _render(_store(tmp_path, stats), {"text": "{{ note }}"})
    assert outcome.status is ComponentStatus.OK
    assert outcome.html is not None
    assert forbidden not in outcome.html
    assert survives in outcome.html


@pytest.mark.parametrize(
    ("stats", "name", "kind"),
    [
        ('{"samples": ["S1", "S2"]}', "samples", "a list"),
        ('{"nested": {"a": 1}}', "nested", "an object"),
        ('{"nothing": null}', "nothing", "null"),
    ],
)
def test_non_scalar_variables_teach(
    tmp_path: Path, stats: str, name: str, kind: str
) -> None:
    # Prose renders scalars; a variable resolving to structured
    # data is an authoring mistake — the artifact's shape does not
    # fit the sentence — and teaches, naming variable and kind.
    with pytest.raises(ValueError, match=f"{name!r} resolved to {kind}"):
        _render(_store(tmp_path, stats), {"text": "{{ " + name + " }}"})


def test_a_variable_the_artifact_does_not_carry_teaches(tmp_path: Path) -> None:
    # A declared, complete artifact missing a variable is a broken
    # contract, not missing data: the sentence promised a value the
    # artifact does not carry.
    with pytest.raises(ValueError, match="missing"):
        _render(_store(tmp_path, STATS), {"text": "Ran {{ missing }} samples"})


def test_variables_without_an_artifact_teach(tmp_path: Path) -> None:
    # The text promises substitution with no source for it.
    with pytest.raises(ValueError, match="artifact"):
        _render(_store(tmp_path), {"text": "Ran {{ n_samples }} samples"})


def test_unclosed_braces_render_as_written(tmp_path: Path) -> None:
    # The typo family that matters — a variable the artifact does
    # not carry — teaches above; a stray '{{' with no closing
    # braces is not a variable, and renders exactly as written.
    outcome = _render(_store(tmp_path), {"text": "a {{ b"})
    assert outcome.status is ComponentStatus.OK
    assert outcome.html is not None
    assert "a {{ b" in outcome.html


# ---------------------------------------------------------------------------
# The subset: what prose is
# ---------------------------------------------------------------------------


def test_static_prose_renders_paragraphs(tmp_path: Path) -> None:
    # artifact is optional: a methods or conclusions card is a real
    # report need with no data dependency.
    outcome = _render(
        _store(tmp_path), {"text": "A methods paragraph.\n\nAnd another."}
    )
    assert outcome.status is ComponentStatus.OK
    assert outcome.html is not None
    assert '<div class="coda-prose">' in outcome.html
    assert "<p>A methods paragraph.</p>" in outcome.html
    assert "<p>And another.</p>" in outcome.html


@pytest.mark.parametrize(
    ("written", "rendered"),
    [
        ("## What ran", "<h3>What ran</h3>"),  # demoted one level
        ("### Detail", "<h4>Detail</h4>"),
        ("#### Deeper", "<h5>Deeper</h5>"),
    ],
)
def test_headings_demote_below_the_card_title(
    tmp_path: Path, written: str, rendered: str
) -> None:
    # The card's title is the section's heading, so prose sections
    # start at '##' and render one level down.
    outcome = _render(_store(tmp_path), {"text": written})
    assert outcome.html is not None
    assert rendered in outcome.html


def test_lists_render_nested_and_ordered(tmp_path: Path) -> None:
    outcome = _render(
        _store(tmp_path),
        {"text": "- flat\n\n- outer\n  - inner\n\n1. first\n2. second"},
    )
    assert outcome.html is not None
    assert outcome.html.count("<ul>") == 2  # the nested list rides inside
    assert "<li>flat</li>" in outcome.html
    assert "<li>inner</li>" in outcome.html
    assert "<ol>" in outcome.html
    assert "<li>first</li>" in outcome.html


def test_blockquotes_render(tmp_path: Path) -> None:
    outcome = _render(_store(tmp_path), {"text": "> As cited in the paper."})
    assert outcome.html is not None
    assert "<blockquote>" in outcome.html
    assert "As cited in the paper." in outcome.html


def test_fenced_code_renders_escaped(tmp_path: Path) -> None:
    # Code is author-written content, so it escapes, never teaches
    # — the contrast with raw HTML below is the line: structure
    # teaches, content renders.
    outcome = _render(_store(tmp_path), {"text": "```\nif x < y:\n    pass\n```"})
    assert outcome.html is not None
    assert "<pre>" in outcome.html
    assert "<code>" in outcome.html
    assert "x &lt; y" in outcome.html
    assert "<y:" not in outcome.html


def test_thematic_rules_render(tmp_path: Path) -> None:
    outcome = _render(_store(tmp_path), {"text": "before\n\n---\n\nafter"})
    assert outcome.html is not None
    assert "<hr>" in outcome.html
    assert "<p>before</p>" in outcome.html
    assert "<p>after</p>" in outcome.html


def test_ampersands_render_without_double_escaping(tmp_path: Path) -> None:
    # CommonMark's guarantee: no raw '<' survives into a text
    # token, so escaping '<' and '>' alone is safe — and escaping
    # '&' too would double-escape the author's own '&amp;'.
    outcome = _render(_store(tmp_path), {"text": "Tom & Jerry &amp; friends"})
    assert outcome.html is not None
    assert "Tom &amp; Jerry" not in outcome.html
    assert "Tom & Jerry" in outcome.html


# ---------------------------------------------------------------------------
# What teaches: the vocabulary the framework owns or refuses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("written", "teaching"),
    [
        ("# Title", "prose sections at '##'"),
        ("A [link](https://example.com) here", "links are not part"),
        ("<https://example.com>", "links are not part"),
        ("![a figure](figure.png)", "images are not part"),
        ("| a | b |\n| - | - |\n| 1 | 2 |", "core.table"),
        ("Text with <b>bold</b> inside", "raw HTML"),
    ],
)
def test_out_of_vocabulary_constructs_teach(
    tmp_path: Path, written: str, teaching: str
) -> None:
    # The subset's fence: what the framework owns (tables, figures,
    # navigation) or refuses (raw HTML into a card) teaches with the
    # move — never renders as literal syntax or silent structure.
    with pytest.raises(ValueError, match=teaching):
        _render(_store(tmp_path), {"text": written})


# ---------------------------------------------------------------------------
# Outcomes: the honest-data law, then the poster
# ---------------------------------------------------------------------------


def test_a_missing_artifact_is_a_notice_not_a_failure(tmp_path: Path) -> None:
    # Missing data is a fact about the run: the store's own message
    # rides an unavailable outcome, exactly like the roster's
    # siblings.
    outcome = _render(
        _store(tmp_path),
        {"artifact": "org.example.stats", "text": "{{ n_samples }} samples"},
    )
    assert outcome.status is ComponentStatus.UNAVAILABLE
    assert outcome.message is not None
    assert "manifest declares no artifact of type 'org.example.stats'" in (
        outcome.message
    )


def test_the_designs_example_renders_end_to_end(tmp_path: Path) -> None:
    # The example that started the design, whole: heading, strong
    # substitution, inline code, and a list — one sentence of prose
    # carrying its numbers from the artifact.
    outcome = _render(
        _store(tmp_path, STATS),
        {
            "text": (
                "## What ran\n\n"
                "We analyzed **{{ n_samples }}** samples during run "
                "`{{ run_id }}`.\n\n"
                "- host reads removed first\n"
                "- low-complexity reads dropped"
            )
        },
    )
    assert outcome.status is ComponentStatus.OK
    assert outcome.html is not None
    assert "<h3>What ran</h3>" in outcome.html
    assert (
        "We analyzed <strong>3</strong> samples during run <code>run-42</code>."
        in outcome.html
    )
    assert "<li>host reads removed first</li>" in outcome.html
