"""The workflow-coda command line interface.

One command today: ``build`` runs the whole pipeline — the manifest's
artifact store, the report builder with the installed plugins, the
renderer — and writes one self-contained HTML page.  The CLI is a
thin edge over the library: it validates its own invocation, then
hands everything to code that already knows how to fail with
teaching messages.

The boundary contract this module owns:

* **Usage errors** are argparse's, per the POSIX/GNU convention:
  wrong flags, missing arguments, an input path that does not exist
  or cannot be read — the usage line on stderr, exit code ``2``,
  before the pipeline starts.
* **Framework errors** — anything the framework diagnosed about the
  manifest, the layout, the theme, or rendering — print their
  teaching message on stderr and exit ``1``: the correction clock is
  the input files or the environment, never the CLI.
* **Write failures** — the destination refused the page, whether the
  pre-flight caught it before the pipeline ran or the write itself
  raised it — print a clean message and exit ``1``; the report
  itself succeeded.
* Anything else is a CLI bug and fails loudly with a traceback.

The console-script entry point calls :func:`main`; the test suite
drives ``main`` in process with argument lists, so no behavior hides
behind the process boundary.  The reusable pieces of the interface
live in :mod:`workflow_coda.cli_toolkit`.
"""

import argparse
import importlib.metadata
import sys
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import cast

from .artifact_store import ArtifactStore
from .builder import build_report
from .cli_toolkit import (
    CliParser,
    check_output_file,
    check_readable_file,
    check_writable_destination,
)
from .errors import WorkflowCodaError
from .render import render_report


def _version() -> str:
    """The ``--version`` line, from installation metadata — unknown
    only when running from an uninstalled source tree."""
    try:
        version = importlib.metadata.version("workflow-coda")
    except importlib.metadata.PackageNotFoundError:
        return "workflow-coda (version unknown: not installed)"
    return f"workflow-coda v{version}"


def _destination_refused(output: Path, error: OSError) -> int:
    """One reporting shape for destination failures — the pre-flight's
    early warning and the write's own refusal read identically."""
    print(
        f"could not write the report to '{output}': {error}",
        file=sys.stderr,
    )
    return 1


def _build_report(args: argparse.Namespace) -> int:
    """The build subcommand: manifest + layout -> one HTML page.

    The destination is pre-flighted before the pipeline runs, so an
    unwritable destination costs a usage error's worth of nothing
    instead of a full pipeline's work — the same exit-1 failure,
    discovered early.
    """
    try:
        check_writable_destination(args.output)
    except OSError as error:
        return _destination_refused(args.output, error)
    store = ArtifactStore.from_manifest_file(args.manifest)
    document = build_report(args.layout, store)
    page = render_report(document)
    try:
        args.output.write_text(page, encoding="utf-8")
    except OSError as error:
        return _destination_refused(args.output, error)
    return 0


def _build_parser() -> CliParser:
    """The whole CLI — root command, one subcommand today — built
    fresh per call, so tests drive :func:`main` with argument lists."""
    parser = CliParser(
        prog="workflow-coda",
        version=_version(),
        description=(
            "A plugin-based composable static HTML report generator for"
            " integration with pipeline workflows through stable manifests."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    build = subparsers.add_parser(
        "build",
        help="Build a report from a manifest and a layout.",
        description=(
            "Run the whole pipeline: load the manifest's artifact store, "
            "build the report document from the layout with the installed "
            "plugins, render it, and write one self-contained HTML page."
        ),
    )
    build.add_argument(
        "manifest",
        type=partial(check_readable_file, extensions=(".json",)),
        metavar="MANIFEST",
        help="Path to the report manifest the pipeline wrote (JSON).",
    )
    build.add_argument(
        "layout",
        type=partial(check_readable_file, extensions=(".yaml", ".yml")),
        metavar="LAYOUT",
        help="Path to the report layout declaring the report (YAML).",
    )
    build.add_argument(
        "-o",
        "--output",
        type=partial(check_output_file, extensions=(".html",)),
        metavar="OUTPUT",
        default=Path("report.html"),
        help="Path of the HTML page to write.",
    )
    build.set_defaults(func=_build_report)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI against *argv* (``None`` means ``sys.argv``) and
    return the process exit code.

    ``0`` on success; ``1`` for any error the framework or the write
    destination diagnosed, with the message on stderr.  Usage errors
    exit ``2`` through argparse (``SystemExit``) before this function
    returns.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    command = cast("Callable[[argparse.Namespace], int]", args.func)
    try:
        return command(args)
    except WorkflowCodaError as error:
        print(error, file=sys.stderr)
        return 1
