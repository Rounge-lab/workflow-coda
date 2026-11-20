import os
from pathlib import Path

from workflow_coda.artifact_store import ArtifactStore
from workflow_coda.builder import build_report
from workflow_coda.core.plugin import get_plugin
from workflow_coda.registry import PluginRegistry
from workflow_coda.render import render_report


def _maybe_write_fixture_report(fixture: Path, html: str) -> None:
    if os.environ.get("WORKFLOW_CODA_WRITE_FIXTURE_REPORTS") != "1":
        return
    output_dir = fixture / "rendered"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.html").write_text(html, encoding="utf-8")


def test_core_table_fixture_builds_a_real_report(tmp_path: Path) -> None:
    fixture = Path(__file__).resolve().parent / "fixtures" / "report" / "core-table"
    manifest_path = fixture / "manifest.json"
    layout_path = fixture / "layout.yaml"
    output_path = tmp_path / "core-table-report.html"

    document = build_report(
        layout_path,
        ArtifactStore.from_manifest_file(manifest_path),
        PluginRegistry((get_plugin(),)),
    )
    html = render_report(document)
    output_path.write_text(html, encoding="utf-8")
    _maybe_write_fixture_report(fixture, html)

    assert output_path.exists()
    assert "Core table integration fixture" in html
    assert "Example table" in html
    assert "Overview" in html
    assert "sample" in html
    assert "value" in html
    assert "status" in html
    assert "S1" in html
    assert "S2" in html
    assert "S3" in html
    assert "pass" in html
    assert "warn" in html
