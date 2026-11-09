"""Assemble the tutorial report's files into a scratch directory and
build the report there — the reader's finished directory,
reconstructed from the shipped examples without duplicating them.

Run through pixi (``pixi run tutorial-report``); the built page lands
at ``docs/examples/tutorial-build/report.html``.
"""

import shutil
import sys
from pathlib import Path

from workflow_coda.errors import WorkflowCodaError

EXAMPLES = Path(__file__).resolve().parent
"""The shipped tutorial examples — the source of every staged file."""

BUILD = EXAMPLES / "build"
"""The scratch directory the report is assembled and built in."""

STAGED = (
    "hello-report/depth.json",
    "hello-report/theme.yaml",
    "waterfall-plugin/steps.json",
    "waterfall-plugin/manifest.json",
    "waterfall-plugin/layout.yaml",
)
"""Every file the finished tutorial's working directory holds."""


def build() -> Path:
    """Stage the files, build the report, and return the page's path."""
    shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    for source in STAGED:
        shutil.copy(EXAMPLES / source, BUILD / Path(source).name)
    # The example plugin is not installed in this environment, so the
    # registry is assembled explicitly — the pipeline behind the CLI,
    # with the reader's directory.
    sys.path.insert(0, str(EXAMPLES / "waterfall-plugin"))
    from waterfall_reports.plugin import get_plugin

    from workflow_coda.artifact_store import ArtifactStore
    from workflow_coda.builder import build_report
    from workflow_coda.core.plugin import get_plugin as get_core_plugin
    from workflow_coda.registry import PluginRegistry
    from workflow_coda.render import render_report

    document = build_report(
        BUILD / "layout.yaml",
        ArtifactStore.from_manifest_file(BUILD / "manifest.json"),
        PluginRegistry((get_core_plugin(), get_plugin())),
    )
    page = BUILD / "report.html"
    page.write_text(render_report(document), encoding="utf-8")
    return page


def main() -> int:
    try:
        page = build()
    except WorkflowCodaError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"report written to {page}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
