"""The CLI toolkit: reusable argparse components with the house UX.

Deliberately framework-agnostic — this module imports nothing from
the rest of the package — so other projects can lift it wholesale
or depend on it as-is.  It carries the pieces every well-behaved
command-line program wants:

* :class:`CustomHelpFormatter` — the help style: capitalized
  ``Usage:`` prefix, option defaults annotated;
* :class:`CliParser` — an ``ArgumentParser`` base with titled
  sections, an explicit ``-h/--help``, and ``-v/--version`` when
  constructed with a version line;
* :func:`check_readable_file` — the argument *type* for input paths:
  refuses directories, missing and unreadable files, and — when
  *extensions* is given — files whose extension is not expected;
* :func:`check_output_file` — the argument *type* for output paths:
  the same extension contract, and nothing else; writability is left
  to the moment of writing, where the truth lives.
* :func:check_writable_destination — the pre-flight for output
  destinations: everything cheaply knowable before work starts,
  raising the matching OSError; the write remains the truth.

The exit-code convention implemented here follows POSIX and GNU
practice: ``0`` success, ``2`` misuse of the command line (argparse's
own exit code for bad invocations, as across GNU coreutils and
grep), ``1`` runtime failure.  Errors go to stderr; help and version
go to stdout and exit ``0``.  BSD's ``sysexits.h`` defines finer
codes — ``EX_USAGE`` is 64 — but the GNU convention is what argparse
implements, and consistency with one's own toolchain beats
consistency with a second standard.
"""

import argparse
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

__all__ = [
    "CliParser",
    "CustomHelpFormatter",
    "check_output_file",
    "check_readable_file",
    "check_writable_destination",
]


class CustomHelpFormatter(argparse.ArgumentDefaultsHelpFormatter):
    """The house help style.

    ``Usage:`` capitalized, as GNU tools print it; option defaults
    annotated — GNU's coding standards ask for defaults in ``--help``
    — in the house ``(Default: ...)`` spelling.  The two overridden
    methods are the stdlib formatter's own extension points, so the
    override is as stable as argparse gets.
    """

    def _format_usage(
        self,
        usage: Any,
        actions: Any,
        groups: Any,
        prefix: Any = None,
    ) -> Any:
        if prefix is None:
            prefix = "Usage: "
        return super()._format_usage(usage, actions, groups, prefix)

    def _get_help_string(self, action: argparse.Action) -> Any:
        help_text = super()._get_help_string(action)
        if help_text is None:
            return ""
        return help_text.replace("(default: ", "(Default: ")


class CliParser(argparse.ArgumentParser):
    """``ArgumentParser`` with the house style.

    Sections are titled, and ``-h/--help`` is added explicitly (help
    exits ``0``).  A *version* line adds ``-v/--version`` —
    conventionally passed to the root parser only, the way ``git`` and
    ``pip`` answer ``--version``; subcommand parsers, which inherit
    this class, answer ``-h`` alone.
    """

    def __init__(self, *args: Any, version: str | None = None, **kwargs: Any) -> None:
        kwargs["add_help"] = False
        kwargs.setdefault("formatter_class", CustomHelpFormatter)
        super().__init__(*args, **kwargs)
        self._positionals.title = "Positional arguments"
        self._optionals.title = "Options"
        self.add_argument(
            "-h",
            "--help",
            action="help",
            help="Show this help message and exit.",
        )
        if version is not None:
            self.add_argument(
                "-v",
                "--version",
                action="version",
                version=version,
                help="Show program's version number and exit.",
            )


def _normalize_extension(extension: str) -> str:
    """Lowercase and dot-prefix one expected extension: ``JSON`` and
    ``.json`` both normalize to ``.json``."""
    extension = extension.lower()
    return extension if extension.startswith(".") else f".{extension}"


def _check_extension(file: Path, extensions: Sequence[str]) -> None:
    """Refuse files whose extension is not one of *extensions*.

    The extension is the invocation's contract about content — the
    fastest way to catch, say, two positional paths given in the wrong
    order — so a mismatch is raised as a usage error
    (:class:`argparse.ArgumentTypeError`, exit ``2``) before the
    program starts, not a load-time failure buried in the pipeline.
    The check is case-insensitive (``.JSON`` is ``.json``) and never
    renames or repairs the path.
    """
    expected = tuple(_normalize_extension(extension) for extension in extensions)
    if file.suffix.lower() in expected:
        return
    listed = ", ".join(expected)
    if file.suffix:
        raise argparse.ArgumentTypeError(
            f"File '{file}' has unexpected extension '{file.suffix}'; "
            f"expected one of: {listed}."
        )
    raise argparse.ArgumentTypeError(
        f"File '{file}' has no extension; expected one of: {listed}."
    )


def check_readable_file(
    path_str: str, *, extensions: Sequence[str] | None = None
) -> Path:
    """The argument *type* for input paths.

    Refuses directories, missing files, and unreadable files as usage
    errors — a bad invocation is the caller's mistake, not a runtime
    failure.  With *extensions*, also refuses files whose extension
    is not one of the expected; the extension contract is checked
    after existence, so a missing file reports the more fundamental
    correction first.
    """
    file = Path(path_str)
    if file.is_dir():
        raise argparse.ArgumentTypeError(f"Specified file '{file}' is a directory.")
    if not file.is_file():
        raise argparse.ArgumentTypeError(f"File '{file}' not found.")
    if extensions is not None:
        _check_extension(file, extensions)
    if not os.access(file, os.R_OK):
        raise argparse.ArgumentTypeError(f"Could not read from file '{file}'.")
    return file


def check_output_file(path_str: str, *, extensions: Sequence[str]) -> Path:
    """The argument *type* for output paths.

    Refuses paths whose extension is not one of the expected — the
    same content contract as :func:`check_readable_file`.  Nothing
    else: writability can only be guessed at parse time, and the
    guess can be wrong (``access(2)`` is not the write), so the
    destination is trusted until the moment of writing proves
    otherwise.
    """
    file = Path(path_str)
    _check_extension(file, extensions)
    return file


def check_writable_destination(path: str | Path) -> None:
    """Pre-flight one output destination: fail fast, not finally.

    Checks everything cheaply knowable before work starts — the
    parent directory exists and is a directory, it is writable per
    ``access(2)``, and an existing file at the destination is not a
    directory and not read-only — raising the matching :class:`OSError`
    subclass with a teaching message.  A pre-flight, not a promise:
    ``access(2)`` is a guess that can be wrong in both directions
    (optimistic on Windows, blind to disk-full and file locks), so
    the moment of writing remains the source of truth; this function
    exists so the common authoring mistake costs nothing, not a full
    pipeline's work.
    """
    file = Path(path)
    parent = file.parent
    if not parent.exists():
        raise FileNotFoundError(f"directory '{parent}' does not exist")
    if not parent.is_dir():
        raise NotADirectoryError(f"'{parent}' is not a directory")
    if not os.access(parent, os.W_OK):
        raise PermissionError(f"directory '{parent}' is not writable")
    if file.is_dir():
        raise IsADirectoryError(f"'{file}' is a directory")
    if file.exists() and not os.access(file, os.W_OK):
        raise PermissionError(f"file '{file}' is not writable")
