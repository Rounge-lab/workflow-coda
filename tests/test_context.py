"""Tests for the render context."""

from pathlib import Path

import pytest
from factories import (
    make_manifest_payload,
    make_theme_payload,
    write_manifest_file,
    write_report_bundle,
)
from helpers import assert_frozen_dataclass

from workflow_coda.artifact_store import ArtifactStore
from workflow_coda.context import RenderContext
from workflow_coda.theme import DEFAULT_THEME_PAIR, Theme, ThemePair


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    """A store over a manifest that declares one artifact (no files)."""
    manifest_path = write_manifest_file(tmp_path, make_manifest_payload())
    return ArtifactStore.from_manifest_file(manifest_path)


def test_context_bundles_store_and_theme(store: ArtifactStore) -> None:
    light = Theme.model_validate(make_theme_payload(name="test-light"))
    dark = Theme.model_validate(make_theme_payload(name="test-dark"))
    pair = ThemePair(light=light, dark=dark)
    context = RenderContext(store=store, theme=pair)

    assert context.store is store
    assert context.theme is pair
    assert context.theme.light is light
    assert context.theme.dark is dark


def test_context_defaults_to_the_default_theme_pair(
    store: ArtifactStore,
) -> None:
    context = RenderContext(store=store)
    assert context.theme is DEFAULT_THEME_PAIR


def test_context_equality_compares_fields(tmp_path: Path) -> None:
    # Stores compare by identity; theme pairs compare by value.
    manifest_path = write_manifest_file(tmp_path, make_manifest_payload())
    first = ArtifactStore.from_manifest_file(manifest_path)
    second = ArtifactStore.from_manifest_file(manifest_path)
    theme = Theme.model_validate(make_theme_payload())
    pair = ThemePair(light=theme, dark=theme)

    assert RenderContext(store=first, theme=pair) == RenderContext(
        store=first, theme=pair
    )
    assert RenderContext(store=first, theme=pair) != RenderContext(
        store=second, theme=pair
    )


def test_context_serves_artifacts_through_the_store(tmp_path: Path) -> None:
    # Wiring proof, end to end: bundle -> store -> context -> require.
    bundle = write_report_bundle(tmp_path)
    context = RenderContext(
        store=ArtifactStore.from_manifest_file(bundle.manifest_path)
    )
    text = context.store.require("org.example.sample_metrics").read_text()
    assert text == "sample_id\tpassed\nS1\ttrue\nS2\tfalse\n"


def test_context_is_frozen(store: ArtifactStore) -> None:
    context = RenderContext(store=store)
    assert_frozen_dataclass(context, "theme", "mutated")


def test_context_rejects_new_attributes(store: ArtifactStore) -> None:
    # slots=True is contract here, not optimization: plugins cannot
    # smuggle state through the context by stashing attributes on it.
    context = RenderContext(store=store)
    with pytest.raises(AttributeError):
        context.extra = "nope"  # type: ignore[attr-defined]
