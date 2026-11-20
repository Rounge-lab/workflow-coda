"""Tests for core.notice: the author's stance card, in the framework's
notice family.

The component's contract, executable: a TILE component painting its
own card as a native ``<details>`` disclosure, levels mapped onto the
framework's card family (``coda-card--<level>``), the note level
optionally wearing a theme token the author names, content through the
prose subset — definition lists included — and v1's text static:
template variables teach toward core.markdown.
"""

from collections.abc import Mapping
from pathlib import Path

import pytest
from factories import make_manifest_payload

from workflow_coda.artifact_store import ArtifactStore, JsonValue
from workflow_coda.builder import build_report
from workflow_coda.components import (
    ComponentChrome,
    ComponentStatus,
    PlacementInfo,
    RenderedComponent,
    ReportComponent,
)
from workflow_coda.context import RenderContext
from workflow_coda.core.plugin import get_plugin
from workflow_coda.layout import LAYOUT_SCHEMA_VERSION
from workflow_coda.manifest import ReportManifest
from workflow_coda.registry import PluginRegistry
from workflow_coda.render import render_report


def _notice() -> ReportComponent:
    """core.notice off the shipped roster — every pin's door, so the
    roster line is under test too."""
    for component in get_plugin().components:
        if component.id == "core.notice":
            return component
    pytest.fail("core.notice is not on the core roster")


def _render(
    store: ArtifactStore,
    parameters: Mapping[str, JsonValue],
    *,
    title: str = "Notice",
) -> RenderedComponent:
    """One render call against a real context and placement."""
    return _notice().render(
        RenderContext(store=store), PlacementInfo(title=title), parameters
    )


def _store(tmp_path: Path) -> ArtifactStore:
    """A store over an empty manifest: a notice reads no artifacts, so
    an empty bundle is the notice's whole world."""
    return ArtifactStore(
        ReportManifest.model_validate(make_manifest_payload(artifacts=[])), tmp_path
    )


# ---------------------------------------------------------------------------
# The roster
# ---------------------------------------------------------------------------


def test_notice_is_on_the_core_roster() -> None:
    # The author's stance card: a TILE component — it paints its own
    # card, the disclosure included — with self-hosted styles drawn
    # from the prose vocabulary plus the notice's own affordances,
    # and no script: the collapse is native <details>.
    component = _notice()
    assert component.id == "core.notice"
    assert component.title == "Notice"
    assert component.chrome is ComponentChrome.TILE
    assert component.css is not None
    assert ".coda-prose" in component.css  # markdown.css, concatenated
    assert ".coda-notice__summary" in component.css  # notice.css
    assert component.js is None


# ---------------------------------------------------------------------------
# The parameter grammar
# ---------------------------------------------------------------------------


def test_unknown_parameter_teaches_with_the_closest_match(tmp_path: Path) -> None:
    # The closed vocabulary law, shared by the roster: a typo'd key
    # teaches with a suggestion before anything else happens.
    with pytest.raises(ValueError, match="did you mean 'level'"):
        _render(_store(tmp_path), {"levl": "note", "text": "Hello."})


def test_a_nested_placement_key_teaches_the_move(tmp_path: Path) -> None:
    # The field-agnostic trap machinery: on_unavailable is a
    # placement key, not a component parameter.
    with pytest.raises(ValueError, match="placement key"):
        _render(_store(tmp_path), {"text": "Hello.", "on_unavailable": "notice"})


def test_text_is_required(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="core.notice"):
        _render(_store(tmp_path), {"level": "note"})


def test_level_is_a_closed_vocabulary(tmp_path: Path) -> None:
    # 'info' is the synonym the design considered and refused.
    with pytest.raises(ValueError, match="must be one of"):
        _render(_store(tmp_path), {"level": "info", "text": "Hello."})


def test_collapsed_must_be_a_boolean(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be a boolean"):
        _render(_store(tmp_path), {"text": "Hello.", "collapsed": "true"})


# ---------------------------------------------------------------------------
# Levels and the note's color
# ---------------------------------------------------------------------------


def test_the_note_level_is_the_default(tmp_path: Path) -> None:
    # No level declared: the card wears the note family class, the
    # muted stance.
    outcome = _render(_store(tmp_path), {"text": "Hello."})
    assert outcome.status is ComponentStatus.OK
    assert outcome.html is not None
    assert "coda-card--note" in outcome.html


@pytest.mark.parametrize("level", ["note", "success", "warning", "failure"])
def test_levels_wear_their_card_family_classes(tmp_path: Path, level: str) -> None:
    # The unification: the author's notice wears the same family
    # classes the framework's own degradation cards wear — the level
    # is the class, the theme token does the coloring.
    outcome = _render(_store(tmp_path), {"level": level, "text": "Hello."})
    assert outcome.status is ComponentStatus.OK
    assert outcome.html is not None
    assert f'<details class="coda-card coda-card--{level} coda-notice" open>' in (
        outcome.html
    )


def test_a_custom_color_pairs_with_the_note_level(tmp_path: Path) -> None:
    # The note level makes no semantic claim, so naming a token is
    # pure presentation — rendered inline, overriding the border
    # color alone (the shared rule keeps the width).
    outcome = _render(_store(tmp_path), {"color": "accent", "text": "Hello."})
    assert outcome.status is ComponentStatus.OK
    assert outcome.html is not None
    assert ' style="border-left-color: #' in outcome.html


def test_a_custom_color_on_a_judgment_level_teaches(tmp_path: Path) -> None:
    # The judgment levels wear their own theme tokens — color pairs
    # with level: note.
    with pytest.raises(ValueError, match="pairs with level 'note'"):
        _render(
            _store(tmp_path),
            {"level": "success", "color": "accent", "text": "Hello."},
        )


def test_a_custom_color_may_not_forge_a_status(tmp_path: Path) -> None:
    # A note wearing 'danger' would read as a failure the author
    # never judged — the reserved tokens teach.
    with pytest.raises(ValueError, match="forge a status"):
        _render(_store(tmp_path), {"color": "danger", "text": "Hello."})


def test_an_unknown_color_token_teaches_from_the_theme(tmp_path: Path) -> None:
    # Resolution rides theme.resolve_color, requester-named: the
    # teaching points at core.notice and lists the theme's tokens.
    with pytest.raises(ValueError, match="core.notice"):
        _render(_store(tmp_path), {"color": "brand", "text": "Hello."})


# ---------------------------------------------------------------------------
# The collapse: native <details>, one structure both ways
# ---------------------------------------------------------------------------


def test_an_open_notice_renders_expanded(tmp_path: Path) -> None:
    # The default: expanded, but still a <details> — the summary row
    # is always the toggle, so readers can close it.
    outcome = _render(_store(tmp_path), {"text": "Hello."})
    assert outcome.html is not None
    assert '<details class="coda-card coda-card--note coda-notice" open>' in (
        outcome.html
    )


def test_a_collapsed_notice_starts_closed(tmp_path: Path) -> None:
    # collapsed sets the initial state only: same structure, no
    # 'open' attribute.
    outcome = _render(_store(tmp_path), {"text": "Hello.", "collapsed": True})
    assert outcome.status is ComponentStatus.OK
    assert outcome.html is not None
    assert '<details class="coda-card coda-card--note coda-notice">' in outcome.html


def test_the_summary_carries_the_resolved_title_escaped(tmp_path: Path) -> None:
    # The placement's resolved title is the summary's label — the
    # card's header — and it escapes like every author-sourced text.
    outcome = _render(
        _store(tmp_path),
        {"text": "Hello."},
        title="QC & thresholds",
    )
    assert outcome.html is not None
    assert '<summary class="coda-notice__summary">QC &amp; thresholds</summary>' in (
        outcome.html
    )


# ---------------------------------------------------------------------------
# The content: the prose subset, notice-flavored
# ---------------------------------------------------------------------------


def test_the_body_wears_the_prose_vocabulary(tmp_path: Path) -> None:
    # The notice's body is prose: one element carrying both the
    # notice's body chrome and the prose styles.
    outcome = _render(_store(tmp_path), {"text": "Hello."})
    assert outcome.html is not None
    assert '<div class="coda-notice__body coda-prose">' in outcome.html


def test_notice_text_renders_through_the_prose_subset(tmp_path: Path) -> None:
    # A notice is prose with a stance: the same walk, the same
    # teachings.
    outcome = _render(
        _store(tmp_path), {"text": "Every sample **cleared** the thresholds."}
    )
    assert outcome.status is ComponentStatus.OK
    assert outcome.html is not None
    assert "<p>Every sample <strong>cleared</strong> the thresholds.</p>" in (
        outcome.html
    )


def test_a_collapsed_column_guide_is_the_driving_use_case(tmp_path: Path) -> None:
    # The use case that started the design: a column guide as a
    # collapsed notice, its definition list the prose subset's
    # reference construct.
    outcome = _render(
        _store(tmp_path),
        {
            "collapsed": True,
            "text": "`sample`\n: Sample name parsed from the filenames.",
        },
        title="Column guide",
    )
    assert outcome.status is ComponentStatus.OK
    assert outcome.html is not None
    assert '<details class="coda-card coda-card--note coda-notice">' in outcome.html
    assert '<summary class="coda-notice__summary">Column guide</summary>' in (
        outcome.html
    )
    assert "<dt><code>sample</code></dt>" in outcome.html
    assert "<dd>Sample name parsed from the filenames.</dd>" in outcome.html


def test_out_of_vocabulary_inside_a_notice_teaches(tmp_path: Path) -> None:
    # The fence holds inside notices: a link teaches with the move,
    # never renders as literal syntax.
    with pytest.raises(ValueError, match="links are not part"):
        _render(_store(tmp_path), {"text": "See [the docs](https://example.com)."})


def test_template_variables_teach_toward_core_markdown(tmp_path: Path) -> None:
    # v1's text is static authorship: a variable has no artifact
    # source here, and the teaching points at the component that
    # owns artifact-backed prose.
    with pytest.raises(ValueError, match="core.markdown"):
        _render(_store(tmp_path), {"text": "{{ n_samples }} samples analyzed."})


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------


def test_the_notice_reaches_the_page_under_its_banner(tmp_path: Path) -> None:
    # Through the real builder: the TILE wrapper, and the component's
    # css in the page's component style block under its own banner —
    # the chrome channel's once-per-report law.
    (tmp_path / "layout.yaml").write_text(
        f'schema_version: "{LAYOUT_SCHEMA_VERSION}"\n'
        "title: Notices\n"
        "tabs:\n"
        "  - title: One\n"
        "    components:\n"
        "      - id: core.notice\n"
        "        title: A note\n"
        "        parameters:\n"
        "          text: Hello.\n",
        encoding="utf-8",
    )
    document = build_report(
        tmp_path / "layout.yaml",
        _store(tmp_path),
        PluginRegistry((get_plugin(),)),
    )
    page = render_report(document)
    assert 'data-component="core.notice"' in page
    assert "/* core.notice */" in page
    assert ".coda-notice__summary" in page
