"""Stage and build the tutorial examples for browser inspection.

Run through the existing pixi task (``pixi run tutorial``).
The waterfall report lands at ``docs/examples/build/report.html``;
the states report lands at
``docs/examples/build/states-report/report.html``.
"""

import shutil
import sys
from pathlib import Path

from workflow_coda.errors import WorkflowCodaError

EXAMPLES = Path(__file__).resolve().parent
"""The shipped tutorial examples — the source of every staged file."""

BUILD = EXAMPLES / "build"
"""The scratch directory the reports are assembled and built in."""

STAGED = (
    "hello-report/depth.json",
    "hello-report/theme.yaml",
    "waterfall-plugin/steps.json",
    "waterfall-plugin/manifest.json",
    "waterfall-plugin/layout.yaml",
)
"""Every file the waterfall tutorial's working directory holds."""

STATES_STAGED = (
    "depth-a.json",
    "depth-b.json",
    "manifest.json",
    "layout.yaml",
)
"""Every file the states tutorial's working directory holds."""


def build() -> Path:
    """Stage the waterfall files, build that report, and return its path.

    This recreates the scratch root. Build additional examples only
    after this call, so their output is not removed.
    """
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


def build_states() -> Path:
    """Stage and build the small states example with the real core plugin."""
    from workflow_coda.artifact_store import ArtifactStore
    from workflow_coda.builder import build_report
    from workflow_coda.core.plugin import get_plugin
    from workflow_coda.registry import PluginRegistry
    from workflow_coda.render import render_report

    destination = BUILD / "states-report"
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True, exist_ok=True)
    for name in STATES_STAGED:
        shutil.copy(EXAMPLES / "states-report" / name, destination / name)

    document = build_report(
        destination / "layout.yaml",
        ArtifactStore.from_manifest_file(destination / "manifest.json"),
        PluginRegistry((get_plugin(),)),
    )
    page = destination / "report.html"
    page.write_text(render_report(document), encoding="utf-8")
    return page


def main() -> int:
    try:
        page = build()
        states_page = build_states()
    except WorkflowCodaError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"report written to {page}")
    print(f"report written to {states_page}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
