"""The workflow-coda command line interface.

Two commands today: ``build`` runs the whole pipeline — the manifest's artifact store,
the report builder with the installed plugins, the renderer — and writes one
self-contained HTML page; ``verify`` turns real pipeline outputs into a verified report
manifest, the stable interface build reads.  The CLI is a thin edge over the library: it
validates its own invocation, then hands everything to code that already knows how to
fail with teaching messages.

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
from .verification import run_verify


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


def _verify_report(args: argparse.Namespace) -> int:
    """The verify subcommand: real files in, a verified manifest out.

    The destination is pre-flighted like build's: an unwritable
    manifest destination refuses before a single artifact is read,
    and a write that fails mid-run reports the same way — one
    shape for destination failures.  The drivers return outcomes;
    this edge is the CLI's only printer for them: the summary to
    stdout, each recorded-failure warning to stderr, the exit code
    last.
    """
    try:
        check_writable_destination(args.manifest)
    except OSError as error:
        return _destination_refused(args.manifest, error)
    try:
        outcome = run_verify(
            file=args.file,
            spec_path=args.spec,
            manifest_path=args.manifest,
            id=args.id,
            type=args.type,
            fmt=args.format,
            schema_version=args.schema_version,
            producer_name=args.producer_name,
            producer_version=args.producer_version,
            run_id=args.run_id,
            criteria_pairs=args.criteria or (),
            on_failure=args.on_failure,
        )
    except OSError as error:
        return _destination_refused(args.manifest, error)
    print(outcome.out, end="")
    for warning in outcome.warnings:
        print(warning, file=sys.stderr)
    return outcome.exit_code


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
    verify = subparsers.add_parser(
        "verify",
        help="Verify pipeline outputs into a report manifest.",
        description=(
            "Turn real output files into a verified report manifest — "
            "the stable interface 'workflow-coda build' reads.  Flags "
            "mode verifies the one FILE, its identity declared by "
            "flags; spec mode verifies every artifact a YAML spec "
            "declares.  One mode per invocation: pass either FILE or "
            "--spec."
        ),
    )
    verify.add_argument(
        "manifest",
        type=partial(check_output_file, extensions=(".json",)),
        metavar="MANIFEST",
        help="Path of the manifest to create or update (JSON).",
    )
    verify.add_argument(
        "file",
        nargs="?",
        type=check_readable_file,
        metavar="FILE",
        help=(
            "Flags mode: the artifact file to verify, its identity "
            "declared by --id, --type, --format, and --schema-version."
        ),
    )
    verify.add_argument(
        "--spec",
        type=partial(check_readable_file, extensions=(".yaml", ".yml")),
        metavar="SPEC",
        help=(
            "Spec mode: a YAML spec declaring the run's producer and "
            "every artifact to verify."
        ),
    )
    verify.add_argument(
        "--id",
        metavar="ID",
        help="The artifact's id within the manifest (flags mode).",
    )
    verify.add_argument(
        "--type",
        metavar="TYPE",
        help="The artifact's namespaced type, e.g. org.example.samples (flags mode).",
    )
    verify.add_argument(
        "--format",
        metavar="FORMAT",
        help="The artifact's format: json, txt, bytes, or namespaced (flags mode).",
    )
    verify.add_argument(
        "--schema-version",
        metavar="VERSION",
        help='The artifact\'s content schema version, e.g. "1.0" (flags mode).',
    )
    verify.add_argument(
        "--producer-name",
        metavar="NAME",
        help="The producing pipeline's name (required when creating a manifest).",
    )
    verify.add_argument(
        "--producer-version",
        metavar="VERSION",
        help="The producing pipeline's version (required when creating a manifest).",
    )
    verify.add_argument(
        "--run-id",
        metavar="RUN",
        help="The producing run's identifier (recorded when creating a manifest).",
    )
    verify.add_argument(
        "--criteria",
        action="append",
        metavar="KEY=VALUE",
        help=(
            "One verification criterion, e.g. --criteria keys=depth — "
            "repeatable; the format's verifier owns the grammar."
        ),
    )
    verify.add_argument(
        "--on-failure",
        choices=("fail", "write"),
        default="fail",
        help=(
            "What an artifact's failed verification does: 'fail' aborts "
            "the run with the teaching and writes nothing (the "
            "default); 'write' records the failed artifact on the "
            "manifest and exits 0."
        ),
    )
    verify.set_defaults(func=_verify_report)
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
