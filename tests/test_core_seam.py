"""The end-to-end seam test: the core plugin through the real CLI.

One bundle, one layout placing core.kpi twice — one healthy placement
with a title override, a threshold policy, and an icon; one untitled
placement against a failed artifact — and core.table twice — one
titled placement with the columns policy and a caption, one default —
plus a placed diagnostics panel, built through the installed
environment's entry point (no injected registry anywhere): CLI →
builder → registry → component → renderer → the written page.  The
seam proof: framework-owned content rendering through the full
pipeline, through the tab grammar, in both chrome modes — the healthy
TILE's self-painted card and the CARD's framework-painted card, the
degraded tile's notice card — with the page-chrome channel census
pinned end to end, and the diagnostics panel placed where the layout
chose."""

import html
import json
from pathlib import Path

from workflow_coda.cli import main
from workflow_coda.theme import DEFAULT_THEME

_STATS_TYPE = "org.example.stats"
_FAILED_TYPE = "org.example.failed"
_SAMPLES_TYPE = "org.example.samples"


def _write_bundle(tmp_path: Path) -> Path:
    """A three-artifact bundle: one complete JSON stats file, one
    declared-but-failed artifact whose file need not exist (the
    status check fires before the filesystem is consulted), and one
    complete core.table-format samples table whose depths are chosen
    so numeric and lexicographic sort orders differ — the fixture the
    eyeball session sorts by hand."""
    (tmp_path / "stats.json").write_text(json.dumps({"depth": 12.4}), encoding="utf-8")
    (tmp_path / "samples.tsv").write_text(
        "sample_id\tdepth\tstatus\nS1\t9\tpassed\nS2\t100\tfailed\nS3\t10\tpassed\n",
        encoding="utf-8",
        newline="\n",
    )
    manifest = {
        "schema_version": "0.2.0",
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
            {
                "id": "samples",
                "type": _SAMPLES_TYPE,
                "schema_version": "0.1.0",
                "path": "samples.tsv",
                "format": "core.table",
                "status": "complete",
            },
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _write_layout(tmp_path: Path) -> Path:
    """A 0.2.0 tab layout placing core.kpi twice — once titled,
    statused, and iconed; once untitled against the failed artifact —
    core.table twice — once titled with the columns policy and a
    caption, once default — and the diagnostics panel in its own tab:
    the tab grammar and both chrome modes, end to end."""
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
  - title: Samples
    components:
      - id: core.table
        title: Sample status
        parameters:
          artifact: org.example.samples
          columns: [status, sample_id]
          caption: Per-sample status.
      - id: core.table
        parameters:
          artifact: org.example.samples
  - title: Diagnostics
    components:
      - type: diagnostics
"""
    path = tmp_path / "layout.yaml"
    path.write_text(layout, encoding="utf-8")
    return path


def test_core_components_render_through_the_cli(tmp_path: Path) -> None:
    manifest = _write_bundle(tmp_path)
    layout = _write_layout(tmp_path)
    output = tmp_path / "report.html"

    main(["build", str(manifest), str(layout), "-o", str(output)])

    page = output.read_text(encoding="utf-8")
    # The tab grammar end to end: a bar of three buttons driving three
    # panels, and the tab script inlined to wire them.
    assert '<nav class="coda-tabs" role="tablist"' in page
    assert 'id="tabbtn-1-headlines"' in page
    assert 'id="tabbtn-2-samples"' in page
    assert 'id="tabbtn-3-diagnostics"' in page
    assert '<section class="coda-tabpanel" id="1-headlines" role="tabpanel"' in page
    assert '<section class="coda-tabpanel" id="2-samples" role="tabpanel"' in page
    assert '<section class="coda-tabpanel" id="3-diagnostics" role="tabpanel"' in page
    assert 'document.documentElement.classList.add("coda-js")' in page
    # The healthy KPI placement: a TILE that painted its own card —
    # the resolved title, the value, the status ink and class, the icon.
    assert '<article class="coda-tile" data-component="core.kpi">' in page
    assert '<p class="coda-kpi__title">Mean depth</p>' in page
    assert ">12.4" in page
    success = DEFAULT_THEME.colors["success"]
    assert f'style="color: {success};"' in page
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
    # Both KPI placements name their component: a placement is an instance.
    assert page.count('data-component="core.kpi"') == 2
    # The table placements: CARD bodies — the framework paints the
    # card and the resolved title (the TILE above paints its own); one
    # placement carries the columns policy and a caption, the other
    # the header's own order; the build-time stamps ride along.
    assert page.count('data-component="core.table"') == 2
    assert page.count('<div class="coda-table">') == 2
    assert "<h3>Sample status</h3>" in page  # the placement's resolved title
    assert "<h3>Table</h3>" in page  # the untitled placement: the declaration default
    assert (
        '<th scope="col" data-key="status" data-type="text">status</th>'
        '<th scope="col" data-key="sample_id" data-type="text">sample_id</th>' in page
    )
    assert "<tr><td>passed</td><td>S1</td></tr>" in page
    assert "<tr><td>failed</td><td>S2</td></tr>" in page
    assert (
        page.count('data-key="depth" data-type="numeric"') == 1
    )  # default placement alone
    assert "<tr><td>S1</td><td>9</td><td>passed</td></tr>" in page
    assert "<tr><td>S2</td><td>100</td><td>failed</td></tr>" in page
    assert '<p class="coda-table__caption">Per-sample status.</p>' in page
    # The controls bar ships in every placement's markup — display-none
    # until the page is scripted, so the DOM carries no lies.
    assert page.count('<div class="coda-table__controls">') == 2
    assert page.count("Filter rows") == 2
    assert page.count("Copy as TSV") == 3
    assert "coda-table--filtered" in page
    assert "navigator.clipboard" in page
    # The placed diagnostics panel: the build's informational notes,
    # rendered in the tab the layout chose for them.
    assert '<section class="coda-diagnostics"' in page
    assert "no theme file declared in the layout" in page
    # The channel census, end to end, from the settled model: the
    # framework stylesheet and one merged component block inline as
    # two <style> elements; the tab wiring and one merged component
    # script as two <script> elements.  The channel stamps each
    # contribution with its component id — /* id */ for css, // id
    # for js — once per report however many placements.  No figures,
    # so no Plotly.js.
    assert page.count("<style>") == 2
    assert page.count("<script>") == 2
    assert page.count("/* core.kpi */") == 1
    assert page.count("/* core.table */") == 1
    assert page.count("// core.table") == 1
    assert ".coda-kpi__title {" in page
