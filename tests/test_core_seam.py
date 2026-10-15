"""The end-to-end seam test: the core plugin through the real CLI.

One bundle, one layout placing core.kpi twice — one healthy placement
with a title override, a threshold policy, and an icon; one untitled
placement against a failed artifact — built through the installed
environment's entry point (no injected registry anywhere): CLI →
builder → registry → component → renderer → the written page.  This
is the seam proof M6 owes since 2c: framework-owned content rendering
through the full pipeline."""

import html
import json
from pathlib import Path

from workflow_coda.cli import main

_STATS_TYPE = "org.example.stats"
_FAILED_TYPE = "org.example.failed"


def _write_bundle(tmp_path: Path) -> Path:
    """A two-artifact bundle: one complete JSON stats file, one
    declared-but-failed artifact whose file need not exist — the
    status check fires before the filesystem is consulted."""
    (tmp_path / "stats.json").write_text(json.dumps({"depth": 12.4}), encoding="utf-8")
    manifest = {
        "schema_version": "0.1.0",
        "producer": {"name": "seam-fixture", "version": "1.0"},
        "artifacts": [
            {
                "id": "stats",
                "type": _STATS_TYPE,
                "schema_version": "0.1.0",
                "path": "stats.json",
                "format": "json",
                "status": "complete",
            },
            {
                "id": "broken",
                "type": _FAILED_TYPE,
                "schema_version": "0.1.0",
                "path": "broken.json",
                "format": "json",
                "status": "failed",
            },
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _write_layout(tmp_path: Path) -> Path:
    """A layout placing core.kpi twice: once titled, statused, and
    iconed; once untitled against the failed artifact — pinning both
    title behaviors (override and declaration default) in one page."""
    layout = """\
schema_version: "0.1.0"
title: Sample QC
sections:
  - title: Headlines
    components:
      - id: core.kpi
        title: Mean depth
        parameters:
          artifact: org.example.stats
          key: depth
          unit: x
          caption: All samples above 10x.
          icon: core-check
          thresholds:
            ok: {above: 10}
      - id: core.kpi
        parameters:
          artifact: org.example.failed
          key: depth
"""
    path = tmp_path / "layout.yaml"
    path.write_text(layout, encoding="utf-8")
    return path


def test_core_kpi_renders_through_the_cli(tmp_path: Path) -> None:
    manifest = _write_bundle(tmp_path)
    layout = _write_layout(tmp_path)
    output = tmp_path / "report.html"

    main(["build", str(manifest), str(layout), "-o", str(output)])

    page = output.read_text(encoding="utf-8")
    # The placement's own title, then the declaration default.
    assert "<h3>Mean depth</h3>" in page
    assert "<h3>Key metric</h3>" in page
    # The healthy KPI: value, status ink and class, sanitized icon.
    assert ">12.4" in page
    assert 'style="color: #198754;"' in page
    assert "coda-kpi--ok" in page
    assert 'class="coda-icon"' in page
    assert 'aria-hidden="true"' in page
    # The failed-artifact KPI renders as a notice through the real
    # template, carrying the store's own teaching message.  The page
    # is escaped markup — the message's quoting quotes render as
    # &#39; on disk — so the pin unescapes first: content, not bytes.
    assert "coda-card--notice" in page
    assert "declared with status 'failed'" in html.unescape(page)
    # Both cards name their component: a placement is an instance.
    assert page.count('data-component="core.kpi"') == 2
    # A figure-free report inlines no Plotly.js — self-containment
    # without dead weight.
    assert "<script" not in page
