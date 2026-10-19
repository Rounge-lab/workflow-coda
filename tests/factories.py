"""Payload factories shared by workflow-coda tests.

Factories return raw dictionaries, not pydantic models, so tests can
freely omit keys, inject invalid values, and exercise every failure mode
through ``model_validate``.
"""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from workflow_coda.artifact_store import JsonValue
from workflow_coda.components import (
    ComponentChrome,
    ComponentParameters,
    ComponentRenderer,
    PlacementInfo,
    PluginMetadata,
    RenderedComponent,
    ReportComponent,
)
from workflow_coda.context import RenderContext
from workflow_coda.plugins import ReportPlugin
from workflow_coda.theme import DEFAULT_THEME

VALID_SHA256 = "a" * 64
"""A syntactically valid lowercase hexadecimal SHA-256 digest."""


def make_artifact_payload(**overrides: object) -> dict[str, object]:
    """Return a fresh, valid artifact declaration payload."""
    payload: dict[str, object] = {
        "id": "sample_metrics",
        "type": "org.example.sample_metrics",
        "schema_version": "1.0",
        "path": "report_data/sample_metrics.tsv",
        "format": "tsv",
        "status": "complete",
    }
    payload.update(overrides)
    return payload


def make_producer_payload(**overrides: object) -> dict[str, object]:
    """Return a fresh, valid producer metadata payload."""
    payload: dict[str, object] = {"name": "Example workflow", "version": "2.4.0"}
    payload.update(overrides)
    return payload


def make_manifest_payload(**overrides: object) -> dict[str, object]:
    """Return a fresh, valid report manifest payload."""
    payload: dict[str, object] = {
        "schema_version": "0.1.0",
        "producer": make_producer_payload(),
        "artifacts": [make_artifact_payload()],
    }
    payload.update(overrides)
    return payload


def write_manifest_file(
    directory: Path,
    payload: dict[str, object],
    name: str = "report_manifest.json",
) -> Path:
    """Serialize a manifest payload as UTF-8 JSON and return its path."""
    path = directory / name
    path.write_text(json.dumps(payload), encoding="utf-8", newline="\n")
    return path


def omit(payload: dict[str, object], *keys: str) -> dict[str, object]:
    """Return a copy of *payload* without *keys*."""
    return {key: value for key, value in payload.items() if key not in keys}


@dataclass(frozen=True)
class ReportBundle:
    """A standard three-artifact report bundle written to disk."""

    manifest_path: Path
    """The manifest file at the bundle root."""

    metrics_path: Path
    """``report_data/sample_metrics.tsv``: TSV artifact, no checksum."""

    summary_path: Path
    """``report_data/qc_summary.json``: JSON artifact, no checksum."""

    catalog_path: Path
    """``report_data/votu_catalog.tsv``: TSV artifact with matching sha256."""


@dataclass(frozen=True)
class ArtifactBundle:
    """A minimal one-artifact report bundle written to disk."""

    manifest_path: Path
    """The manifest file at the bundle root."""

    artifact_path: Path
    """The declared artifact file (not written when content is ``None``)."""


def write_report_bundle(bundle_root: Path) -> ReportBundle:
    """Write a standard report bundle: manifest plus a ``report_data/`` tree.

    Declares three artifacts: a plain TSV metrics table, a JSON summary, and
    a checksummed TSV catalog.  All files are written with LF newlines so
    fixtures are byte-identical on every platform.
    """
    data_dir = bundle_root / "report_data"
    data_dir.mkdir(parents=True, exist_ok=True)

    metrics_path = data_dir / "sample_metrics.tsv"
    metrics_path.write_text(
        "sample_id\tpassed\nS1\ttrue\nS2\tfalse\n", encoding="utf-8", newline="\n"
    )
    summary_path = data_dir / "qc_summary.json"
    summary_path.write_text(
        json.dumps({"passed": 1, "total_samples": 2}),
        encoding="utf-8",
        newline="\n",
    )
    catalog_content = "votu_id\tquality\nvOTU_001\tmedium\n"
    catalog_path = data_dir / "votu_catalog.tsv"
    catalog_path.write_text(catalog_content, encoding="utf-8", newline="\n")

    payload = make_manifest_payload(
        artifacts=[
            make_artifact_payload(),
            make_artifact_payload(
                id="qc_summary",
                type="org.example.qc_summary",
                path="report_data/qc_summary.json",
                format="json",
            ),
            make_artifact_payload(
                id="votu_catalog",
                type="org.example.votu_catalog",
                path="report_data/votu_catalog.tsv",
                sha256=hashlib.sha256(catalog_content.encode("utf-8")).hexdigest(),
            ),
        ]
    )
    manifest_path = write_manifest_file(bundle_root, payload)
    return ReportBundle(
        manifest_path=manifest_path,
        metrics_path=metrics_path,
        summary_path=summary_path,
        catalog_path=catalog_path,
    )


def write_artifact_bundle(
    bundle_root: Path,
    declaration: dict[str, object],
    content: str | bytes | None = "",
    *,
    newline: str = "\n",
) -> ArtifactBundle:
    """Write a one-artifact manifest bundle plus the artifact's file.

    The declaration payload must include ``path``.  *content* is written to
    that location — as text with *newline* translation, or as raw bytes.
    ``None`` writes no artifact file, for tests that need the declared
    artifact absent.  The declared path's parent directories are always
    created.
    """
    artifact_path = bundle_root / str(declaration["path"])
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    if content is not None:
        if isinstance(content, bytes):
            artifact_path.write_bytes(content)
        else:
            artifact_path.write_text(content, encoding="utf-8", newline=newline)
    manifest_path = write_manifest_file(
        bundle_root, make_manifest_payload(artifacts=[declaration])
    )
    return ArtifactBundle(manifest_path=manifest_path, artifact_path=artifact_path)


def make_theme_payload(**overrides: object) -> dict[str, object]:
    """Return a fresh, valid design-token theme payload.

    Built from :data:`workflow_coda.theme.DEFAULT_THEME` via ``model_dump``,
    so the factory can never drift from the default theme: changing the
    default palette updates the fixtures automatically.
    """
    payload: dict[str, object] = DEFAULT_THEME.model_dump()
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Plugin and component factories
# ---------------------------------------------------------------------------


def noop_render(
    _context: RenderContext, _info: PlacementInfo, _parameters: ComponentParameters
) -> RenderedComponent:
    """The do-nothing renderer: every outcome is a skip.

    A stable module-level callable, so factory-built components are
    hashable and ``component.render is noop_render`` is checkable.
    Underscore-prefixed parameters mark them as intentionally unused.
    """
    return RenderedComponent.skipped()


def make_metadata(
    id: str = "example",
    name: str = "Example plugin",
    version: str = "1.0.0",
    description: str = "Components for the test suite.",
    supported_schema_versions: Iterable[str] = ("0.1.0",),
) -> PluginMetadata:
    """A fresh, valid plugin metadata value."""
    return PluginMetadata(
        id=id,
        name=name,
        version=version,
        description=description,
        supported_schema_versions=frozenset(supported_schema_versions),
    )


def make_component(
    id: str = "example.quality",
    title: str = "Quality overview",
    description: str | None = None,
    render: ComponentRenderer = noop_render,
    chrome: ComponentChrome = ComponentChrome.CARD,
) -> ReportComponent:
    """A fresh, valid component declaration.

    The default id is prefixed with :func:`make_metadata`'s default id, so
    ``make_plugin()`` assembles cleanly; override either side to build the
    invalid combinations the integrity tests exercise.
    """
    return ReportComponent(
        id=id,
        title=title,
        description=description,
        render=render,
        chrome=chrome,
    )


def make_plugin(
    metadata: PluginMetadata | None = None,
    components: tuple[ReportComponent, ...] | None = None,
) -> ReportPlugin:
    """A fresh, valid single-component report plugin."""
    return ReportPlugin(
        metadata=metadata if metadata is not None else make_metadata(),
        components=components if components is not None else (make_component(),),
    )


# ---------------------------------------------------------------------------
# Layout factories
# ---------------------------------------------------------------------------


def make_layout_payload(**overrides: JsonValue) -> dict[str, JsonValue]:
    """The suite's layout payload: schema 0.2.0, one tab, one placement.

    Overrides merge onto the default payload wholesale — arbitrary
    keys included, so the typo-key tests build their typo'd payloads
    through the same factory.
    """
    payload: dict[str, JsonValue] = {
        "schema_version": "0.2.0",
        "title": "Metagenomic analysis",
        "tabs": [
            {
                "title": "Quality control",
                "components": [{"id": "example_bio.qc"}],
            }
        ],
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Figure factories
# ---------------------------------------------------------------------------


def stub_figure(html: str = "<div>the plot</div>") -> StubFigure:
    """A minimal ``SupportsToHtml`` that records the embedding flags it
    was called with; the default figure fixture for figure tests."""
    return StubFigure(html)


class StubFigure:
    """Minimal ``SupportsToHtml`` for tests: records the embedding
    flags from_figure must pass, returns canned html."""

    def __init__(self, html: str = "<div>the plot</div>") -> None:
        self._html = html
        self.full_html: object = "unset"
        self.include_plotlyjs: object = "unset"
        self.config: object = "unset"

    def to_html(
        self,
        *,
        full_html: bool,
        include_plotlyjs: bool,
        config: dict[str, Any] | None = None,
    ) -> str:
        self.full_html = full_html
        self.include_plotlyjs = include_plotlyjs
        self.config = config
        return self._html
