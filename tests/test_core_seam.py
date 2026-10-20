"""The end-to-end seam test: the core plugin through the real CLI.

One bundle, one layout placing core.kpi twice — one healthy placement
with a title override, a threshold policy, and an icon; one untitled
placement against a failed artifact — plus a placed diagnostics
panel, built through the installed environment's entry point (no
injected registry anywhere): CLI → builder → registry → component →
renderer → the written page.  The seam proof: framework-owned content
rendering through the full pipeline, through the tab grammar, in both
chrome modes — the healthy TILE's self-painted card and the degraded
tile's framework notice card — with the diagnostics panel placed
where the layout chose."""

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
    """A 0.2.0 tab layout placing core.kpi twice — once titled,
    statused, and iconed; once untitled against the failed artifact —
    and the diagnostics panel in its own tab: the M7 grammar, end to
    end."""
    layout = """\
schema_version: "0.2.0"
title: Sample QC
tabs:
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
  - title: Diagnostics
    components:
      - type: diagnostics
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
    # The tab grammar end to end: a bar of two buttons driving two
    # panels, and the tab script inlined to wire them — no figures,
    # so no Plotly.js alongside it.
    assert '<nav class="coda-tabs" role="tablist"' in page
    assert 'id="tabbtn-1-headlines"' in page
    assert 'id="tabbtn-2-diagnostics"' in page
    assert '<section class="coda-tabpanel" id="1-headlines" role="tabpanel"' in page
    assert '<section class="coda-tabpanel" id="2-diagnostics" role="tabpanel"' in page
    assert page.count("<script>") == 1
    assert 'document.documentElement.classList.add("coda-js")' in page
    # The healthy placement: a TILE that painted its own card — the
    # resolved title, the value, the status ink and class, the icon.
    assert '<article class="coda-tile" data-component="core.kpi">' in page
    assert '<p class="coda-kpi__title">Mean depth</p>' in page
    assert ">12.4" in page
    assert 'style="color: #198754;"' in page
    assert "coda-kpi--ok" in page
    assert 'class="coda-icon"' in page
    assert 'aria-hidden="true"' in page
    # The degraded placement: an unavailable TILE teaches in the
    # framework's notice card, the declaration's default title its
    # heading — chrome mode is independent of degradation.
    assert "coda-card--notice" in page
    assert "<h3>Key metric</h3>" in page
    # The message's quoting renders as &#39; on disk — the pin
    # unescapes first: content, not bytes.
    assert "declared with status 'failed'" in html.unescape(page)
    # Both placements name their component: a placement is an instance.
    assert page.count('data-component="core.kpi"') == 2
    # The placed diagnostics panel: the build's informational notes,
    # rendered in the tab the layout chose for them.
    assert '<section class="coda-diagnostics"' in page
    assert "no theme file declared in the layout" in page
    # Self-hosted chrome, end to end: the KPI's stylesheet inlines as
    # its own block after the framework's — one banner however many
    # placements the layout makes (the once-per-report dedup) — and
    # the script census stands at one because core.kpi declares no
    # js.
    assert page.count("<style>") == 2
    assert page.count("/* core.kpi */") == 1
    assert ".coda-kpi__title {" in page
