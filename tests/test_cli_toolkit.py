"""Tests for the CLI toolkit: the liftable argparse components.

The toolkit is framework-agnostic — it imports nothing from the rest
of the package — and this file keeps the same property: only the
toolkit under test is imported, so the file travels with the module
it pins.  The CLI's *use* of the toolkit is pinned in test_cli.py;
this file pins the toolkit itself.
"""

import argparse
from pathlib import Path

import pytest

from workflow_coda.cli_toolkit import (
    CliParser,
    check_output_file,
    check_readable_file,
    check_writable_destination,
)

# ---------------------------------------------------------------------------
# The help style: the formatter's two properties
# ---------------------------------------------------------------------------


def test_formatter_capitalizes_the_usage_prefix() -> None:
    # The house style, pinned as a property through the public path:
    # format_usage() renders the usage line, and the formatter's own
    # override supplies the capitalized prefix.  Not an exact string —
    # the rest of the line (options, metavars) is argparse's to spell,
    # and hand-computing it is the brittleness the house rule exists
    # to avoid.
    parser = CliParser(prog="example", description="An example.")
    assert parser.format_usage().startswith("Usage: example")


def test_formatter_capitalizes_default_annotations() -> None:
    # GNU coding standards: defaults documented in --help, in the
    # house spelling.  The fixture help is short by design: argparse
    # wraps option help at the terminal width *after* the formatter
    # appends the annotation, so a long help line would wrap between
    # "(Default:" and its value and split the pin across lines.
    parser = CliParser(prog="example", description="An example.")
    parser.add_argument("--flag", default="value", help="One flag.")
    assert "(Default: value)" in parser.format_help()


# ---------------------------------------------------------------------------
# The path types: refusals in argparse's own vocabulary
# ---------------------------------------------------------------------------


def test_check_readable_file_refuses_the_wrong_extension_directly(
    tmp_path: Path,
) -> None:
    # The refusal is an ArgumentTypeError — argparse's exit-2
    # vocabulary — raised by the type function itself, not only
    # surfaced through a parse.  The candidate exists, so the checks
    # run in their documented order: existence first, extension after.
    candidate = tmp_path / "report_manifest.yaml"
    candidate.write_text("{}", encoding="utf-8")
    with pytest.raises(
        argparse.ArgumentTypeError, match="unexpected extension '.yaml'"
    ):
        check_readable_file(str(candidate), extensions=(".json",))


def test_check_output_file_refuses_wrong_and_missing_extensions_directly() -> None:
    # The output type's only job is the extension contract, so both of
    # its refusals pin without any filesystem at all: a wrong
    # extension, and none — the refusal a directory-shaped output
    # hits in real invocations.
    with pytest.raises(argparse.ArgumentTypeError, match="unexpected extension '.txt'"):
        check_output_file("report.html.txt", extensions=(".html",))
    with pytest.raises(argparse.ArgumentTypeError, match="has no extension"):
        check_output_file("build", extensions=(".html",))


def test_check_writable_destination_accepts_a_clean_target(tmp_path: Path) -> None:
    # The pre-flight's positive pin: a not-yet-existing file in an
    # existing writable directory passes — the common case must not
    # refuse.  Every refusal is pinned through the CLI in
    # test_cli.py; this is the acceptance path.
    check_writable_destination(tmp_path / "report.html")
