"""Tests for the core plugin's asset loader: shipped chrome as real
files, read once at import.

The loader is the door between ``core/assets/`` and the plugin's
chrome constants — the same stdlib door a third-party plugin uses for
its own package data.  These pins hold the door honest.  The wiring
invariant: a read at test time returns exactly the constants the
declarations carry, so wrong-file wiring or a constant hardcoded
over a file that later changed reddens here first.  The byte
discipline: a file carries exactly what shipped — full content, one
trailing newline, no leading blank line — so the string-literal
mistakes cannot creep back in.  A missing asset teaches as a broken
installation: named, diagnosed, fix in the message, cause chained —
and inside the framework's one recovery boundary.  The css/js
vocabulary pins and the page-level census live in
test_core_plugin.py and test_core_seam.py; their unchanged state
through the asset swap was the transcription proof."""

import pytest

from workflow_coda.core.assets import read_core_asset
from workflow_coda.core.plugin import _KPI_CSS, _TABLE_CSS, _TABLE_JS
from workflow_coda.errors import PluginAssetError, WorkflowCodaError

_ASSETS = [
    ("kpi.css", _KPI_CSS),
    ("table.css", _TABLE_CSS),
    ("table.js", _TABLE_JS),
]


@pytest.mark.parametrize(("name", "constant"), _ASSETS)
def test_shipped_assets_read_back_as_the_plugin_constants(
    name: str, constant: str
) -> None:
    # The wiring invariant: the chrome constants are the files.  The
    # declarations' css and js were produced by this same read at
    # import, so a test-time read that disagrees names the drift —
    # wrong-file wiring today, or a stale hardcoded constant the day
    # a file changes underneath it.
    assert read_core_asset(name) == constant


@pytest.mark.parametrize("name", ["kpi.css", "table.css", "table.js"])
def test_asset_files_carry_exactly_what_shipped(name: str) -> None:
    # The extraction discipline, pinned: no leading blank line (the
    # classic literal-continuation mistake), exactly one trailing
    # newline — the files are the strings' bytes, nothing more.
    content = read_core_asset(name)
    assert content
    assert not content.startswith("\n")
    assert content == content.rstrip("\n") + "\n"


def test_a_missing_asset_teaches_a_broken_installation() -> None:
    # A missing or unreadable asset is an environment failure, taught
    # as one: the asset named, the installation diagnosed, the fix in
    # the message — and the cause chained, so what actually broke
    # survives into the error.
    with pytest.raises(PluginAssetError) as exc_info:
        read_core_asset("absent.css")
    message = str(exc_info.value)
    assert "the core plugin's asset 'absent.css' is missing or unreadable" in message
    assert "the workflow-coda installation is broken; reinstall it" in message
    assert exc_info.value.__cause__ is not None


def test_asset_errors_live_inside_the_recovery_boundary() -> None:
    # One root, one catch: a caller guards plugin-asset failures with
    # the same except clause as everything else this framework raises.
    assert issubclass(PluginAssetError, WorkflowCodaError)
