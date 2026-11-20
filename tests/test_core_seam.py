"""The end-to-end seam test: the core plugin through the real CLI.

One bundle, one layout placing core.kpi twice — one healthy placement
with a title override, a threshold policy, and an icon; one untitled
placement against a failed artifact — core.table twice — one titled
placement with the columns policy and a caption, one default — and
core.chart once — the same samples artifact as a hue-grouped bar
figure, the tabular format's second reader — plus a placed
diagnostics panel, built through the installed environment's entry
point (no injected registry anywhere): CLI → builder → registry →
component → renderer → the written page.  The seam proof:
framework-owned content rendering through the full pipeline, through
the tab grammar, in both chrome modes — the healthy TILE's
self-painted card and the CARD's framework-painted card, the degraded
tile's notice card — with the page-chrome channel census and the
figure channel (Plotly.js plus the figure's own bootstrap) pinned end
to end, and the diagnostics panel placed where the layout chose."""

import html
import json
from pathlib import Path

from workflow_coda.cli import main
from workflow_coda.layout import LAYOUT_SCHEMA_VERSION
from workflow_coda.manifest import MANIFEST_SCHEMA_VERSION
from workflow_coda.theme import DEFAULT_THEME

_STATS_TYPE = "org.example.stats"
_FAILED_TYPE = "org.example.failed"
_SAMPLES_TYPE = "org.example.samples"


def _write_bundle(tmp_path: Path) -> Path:
    """A three-artifact bundle: one complete JSON stats file, one
    declared-but-failed artifact whose file need not exist (the
    status check fires before the filesystem is consulted), and one
    complete core.tabular-format samples table whose depths are chosen
    so numeric and lexicographic sort orders differ — the fixture the
    eyeball session sorts by hand."""
    (tmp_path / "stats.json").write_text(json.dumps({"depth": 12.4}), encoding="utf-8")
    (tmp_path / "samples.tsv").write_text(
        "sample_id\tdepth\tstatus\nS1\t9\tpassed\nS2\t100\tfailed\nS3\t10\tpassed\n",
        encoding="utf-8",
        newline="\n",
    )
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
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
                "format": "core.tabular",
                "status": "complete",
            },
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _write_layout(tmp_path: Path) -> Path:
    """A tab layout placing core.kpi twice — once titled,
    statused, and iconed; once untitled against the failed artifact —
    core.table twice — once titled with the columns policy and a
    caption, once default — core.chart once — the samples artifact as
    a hue-grouped bar figure beside its table — and the diagnostics
    panel in its own tab: the tab grammar, both chrome modes, and the
    figure channel, end to end."""
    layout = (
        f'schema_version: "{LAYOUT_SCHEMA_VERSION}"\n'
        + """\
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
      - id: core.chart
        title: Depth by sample
        parameters:
          artifact: org.example.samples
          chart: bar
          x: sample_id
          y: depth
          hue: status
  - title: Diagnostics
    components:
      - type: diagnostics
"""
    )
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
    # Knowing shift (sort-state icons): was — the two header cells
    # pinned byte-adjacent, adjacency carrying the columns policy's
    # order; now — every column label carries the sort-state stamp
    # before its </th>, so each label pins against the stamp's
    # opening and an index assert carries the order.  Everything
    # else in this census survives: substring pins.
    assert (
        '<th scope="col" data-key="status" data-type="text">status'
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in page
    )
    assert (
        '<th scope="col" data-key="sample_id" data-type="text">sample_id'
        '<span class="coda-table__sort-icon coda-table__sort-icon--idle">' in page
    )
    assert page.index('data-key="status"') < page.index('data-key="sample_id"')
    # Knowing shift (iconed controls): "Filter rows" survives at 2 —
    # the name moved from a label element to the field's aria-label;
    # "Copy as TSV" was 3 and is now 2 — the two buttons' aria-labels
    # — because the js feedback constant that carried the third
    # retired: feedback is a live region now, not a label restore.
    assert page.count("Filter rows") == 2
    assert page.count("Copy as TSV") == 2
    assert "coda-table--filtered" in page
    assert "navigator.clipboard" in page
    # The chart placement: the tabular format's second reader — the
    # same samples artifact as a bar figure, hue-grouped by status
    # (first-appearance order: passed, then failed — two series-
    # colored traces), inside the framework's CARD chrome: the
    # framework painted the card, the placement's resolved title its
    # heading, and the inferred accessibility label rides the
    # figure's marker div.
    assert '<article class="coda-card" data-component="core.chart">' in page
    assert "<h3>Depth by sample</h3>" in page
    assert 'class="coda-figure"' in page
    assert (
        'aria-label="Bar chart of depth by sample_id, 3 bars, '
        'colored by status"' in page
    )
    assert '"passed"' in page  # the hue groups reached the figure's JSON
    assert '"failed"' in page
    # The placed diagnostics panel: the build's informational notes,
    # rendered in the tab the layout chose for them.
    assert '<section class="coda-diagnostics"' in page
    assert "no theme declared in the layout" in page
    # The channel census, end to end, from the settled model: the
    # framework stylesheet and one merged component block inline as
    # two <style> elements (core.chart declares no chrome), and four
    # <script tags in all — the tab wiring, the merged component
    # script, the inlined Plotly.js (bare tags), and the figure's own
    # bootstrap (its own tag shape).  The channel stamps each
    # contribution with its component id — /* id */ for css, // id
    # for js — once per report however many placements.  No figures,
    # so no Plotly.js — that was the census before charts shipped.
    assert page.count("<style>") == 2
    assert (
        page.count("<script>") == 4
    )  # bare tags: tab, component block, Plotly.js, plus the figure's own bootstrap tag
    assert page.count("/* core.kpi */") == 1
    assert page.count("/* core.table */") == 1
    assert page.count("// core.table") == 1
    assert ".coda-kpi__title {" in page
    # The icon census, both authors counted.  The svgs: the two
    # tables stamp 15 sort-state icons — three states × five columns
    # (2 where the columns policy selects, 3 in the default) — plus
    # 3 controls icons per table (filter, copy, check) × 2 tables,
    # and the healthy KPI adds its own core-check: 22.  The state
    # class names: 15 in the markup plus 4 in the stylesheet (three
    # in the visibility selector group, one in the opacity rule) —
    # so a missing stylesheet reads 15 and the pin teaches.
    assert page.count('class="coda-icon"') == 22
    assert page.count("coda-table__sort-icon--") == 19
    # The controls chrome census — the coda-table__ vocabulary is
    # table-owned, so every author is held.  The copy button's two
    # stamped faces: one span per table in the markup plus the two
    # stylesheet rules that swap them — 4.  The success-state class:
    # two stylesheet rules, two script sites — 4, absent from the
    # served markup because the script owns it at runtime.  The
    # screen-reader utility: one count span per table plus its one
    # stylesheet rule — 3.
    assert page.count("coda-table__copy-check") == 4
    assert page.count("coda-table__copy--copied") == 4
    assert page.count("coda-table__sr") == 3
