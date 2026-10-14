"""Tests for the CLI: the boundary between the library and the shell.

The parser surface first — version, help, usage errors, extension
enforcement — all pinned without touching the pipeline: none of
these tests needs a plugin, a manifest's content, or a layout.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from factories import make_layout_payload, make_manifest_payload

from workflow_coda import cli
from workflow_coda.cli import main
from workflow_coda.errors import RenderError

# ---------------------------------------------------------------------------
# Version and help: stdout, exit 0
# ---------------------------------------------------------------------------


def test_version_prints_on_stdout_and_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--version"])
    assert raised.value.code == 0
    out, err = capsys.readouterr()
    assert out.startswith("workflow-coda v")
    assert err == ""


def test_help_prints_usage_and_titled_sections(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--help"])
    assert raised.value.code == 0
    out, err = capsys.readouterr()
    # The house help style: capitalized usage, titled sections, the
    # COMMAND metavar for the required subcommand.
    assert "Usage: workflow-coda" in out
    assert "COMMAND" in out
    assert "Positional arguments" in out
    assert "Options" in out
    assert "build" in out  # the subcommand is listed with its help line
    assert err == ""


def test_build_help_pins_metavars_and_defaults(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["build", "--help"])
    assert raised.value.code == 0
    out, _ = capsys.readouterr()
    assert "Usage: workflow-coda build" in out
    assert "MANIFEST" in out
    assert "LAYOUT" in out
    assert "[-o OUTPUT]" in out
    # The house default annotation, capitalized by the formatter.
    assert "(Default: report.html)" in out


# ---------------------------------------------------------------------------
# Usage errors: exit 2, stderr
# ---------------------------------------------------------------------------


def test_no_command_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main([])
    assert raised.value.code == 2
    _, err = capsys.readouterr()
    # Even the error-path usage carries the capitalized prefix.
    assert "Usage: workflow-coda" in err


def test_unknown_command_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["explode"])
    assert raised.value.code == 2
    _, err = capsys.readouterr()
    assert "invalid choice" in err


def test_missing_manifest_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    layout = tmp_path / "report_layout.yaml"
    layout.write_text("title: Metagenomic analysis\n")
    with pytest.raises(SystemExit) as raised:
        main(["build", str(tmp_path / "absent.json"), str(layout)])
    assert raised.value.code == 2
    _, err = capsys.readouterr()
    assert "not found" in err


def test_directory_as_input_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    layout = tmp_path / "report_layout.yaml"
    layout.write_text("title: Metagenomic analysis\n")
    with pytest.raises(SystemExit) as raised:
        main(["build", str(tmp_path), str(layout)])
    assert raised.value.code == 2
    _, err = capsys.readouterr()
    assert "is a directory" in err


def test_swapped_positionals_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The extension contract catches the swapped-arguments mistake in
    # one clear usage error — the reason it exists.
    layout = tmp_path / "report_layout.yaml"
    layout.write_text("title: Metagenomic analysis\n")
    manifest = tmp_path / "report_manifest.json"
    manifest.write_text("{}")
    with pytest.raises(SystemExit) as raised:
        main(["build", str(layout), str(manifest), "-o", str(tmp_path / "out.html")])
    assert raised.value.code == 2
    _, err = capsys.readouterr()
    assert "unexpected extension '.yaml'" in err
    assert "expected one of: .json" in err


def test_wrong_output_extension_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "report_manifest.json"
    manifest.write_text("{}")
    layout = tmp_path / "report_layout.yaml"
    layout.write_text("title: Metagenomic analysis\n")
    with pytest.raises(SystemExit) as raised:
        main(["build", str(manifest), str(layout), "-o", str(tmp_path / "out.txt")])
    assert raised.value.code == 2
    _, err = capsys.readouterr()
    assert "expected one of: .html" in err


# ---------------------------------------------------------------------------
# Orchestration pins
# ---------------------------------------------------------------------------


def _patched_pipeline(monkeypatch: pytest.MonkeyPatch, page: str) -> dict[str, object]:
    """Patch the CLI module's three pipeline callables with fakes
    that record what they were called with and thread one sentinel
    each — the store into the build, the document into the render —
    returning the record for assertions.

    The seam is the CLI module's *own* names, not the stages'
    internals: the composition is the subject here; the stages are
    pinned by their own suites.
    """
    seen: dict[str, object] = {}
    the_store = object()
    the_document = object()
    seen["the_store"] = the_store
    seen["the_document"] = the_document

    def fake_from_manifest_file(path: Path) -> object:
        seen["manifest_path"] = path
        return the_store

    def fake_build_report(layout_path: Path, store: object) -> object:
        seen["layout_path"] = layout_path
        seen["store"] = store
        return the_document

    def fake_render_report(document: object) -> str:
        seen["document"] = document
        return page

    monkeypatch.setattr(
        cli,
        "ArtifactStore",
        SimpleNamespace(from_manifest_file=fake_from_manifest_file),
    )
    monkeypatch.setattr(cli, "build_report", fake_build_report)
    monkeypatch.setattr(cli, "render_report", fake_render_report)
    return seen


def test_build_threads_the_pipeline_and_writes_the_page(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The files' content is irrelevant here — the parse-time checks
    # need real paths, and the pipeline is patched before it runs.
    manifest = tmp_path / "report_manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    layout = tmp_path / "report_layout.yaml"
    layout.write_text("title: Metagenomic analysis\n", encoding="utf-8")
    output = tmp_path / "report.html"
    seen = _patched_pipeline(monkeypatch, "<!doctype html>the page")

    code = main(["build", str(manifest), str(layout), "-o", str(output)])

    assert code == 0
    # Each stage received exactly its predecessor's product.
    assert seen["manifest_path"] == manifest
    assert seen["layout_path"] == layout
    assert seen["store"] is seen["the_store"]
    assert seen["document"] is seen["the_document"]
    assert output.read_text(encoding="utf-8") == "<!doctype html>the page"
    # Silent-good-citizen: success prints nothing, on either stream.
    out, err = capsys.readouterr()
    assert out == ""
    assert err == ""


def test_build_writes_to_the_default_path_in_the_cwd(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / "report_manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    layout = tmp_path / "report_layout.yaml"
    layout.write_text("title: Metagenomic analysis\n", encoding="utf-8")
    _patched_pipeline(monkeypatch, "<!doctype html>default page")
    monkeypatch.chdir(tmp_path)

    code = main(["build", str(manifest), str(layout)])

    assert code == 0
    assert (tmp_path / "report.html").read_text(encoding="utf-8") == (
        "<!doctype html>default page"
    )
    out, err = capsys.readouterr()
    assert out == ""
    assert err == ""


# ---------------------------------------------------------------------------
# The success path: end to end, no plugins needed
# ---------------------------------------------------------------------------


def _write_empty_manifest(tmp_path: Path) -> Path:
    """A valid manifest file with zero artifacts: the pasted envelope
    allows ``artifacts: []`` for a partial run — and zero artifacts
    means the store resolves nothing from disk."""
    payload = make_manifest_payload()
    payload["artifacts"] = []
    manifest = tmp_path / "report_manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    return manifest


def _write_pluginless_layout(tmp_path: Path) -> Path:
    """The suite's factory layout, serialized with every placement
    set to ``on_missing: notice`` — the layout's own declared tolerance
    for a component whose plugin is not installed, so the end-to-end
    test stays plugin-independent while the component's absence still
    reaches the document."""
    payload = make_layout_payload()
    sections = payload["sections"]
    assert isinstance(sections, list)
    for section in sections:
        assert isinstance(section, dict)
        components = section["components"]
        assert isinstance(components, list)
        for placement in components:
            assert isinstance(placement, dict)  # loud on shape surprises
            placement["on_missing"] = "notice"
    layout = tmp_path / "report_layout.yaml"
    layout.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return layout


def test_build_end_to_end_through_the_real_pipeline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The real pipeline through the real CLI: manifest file and layout
    # file to written page, with the genuine store, builder, and
    # renderer.  The dev environment installs no plugins, so this
    # exercises the layout's declared tolerance — every placement set
    # to ``on_missing: notice`` — which is the plugin-independent
    # success path: the build succeeds and the missing component is
    # honestly visible in the page as a notice card.  (The default
    # without the declaration is a fail-fast refusal — pinned in the
    # exit-1 family.)  This test also pins the CLI's assumed call
    # shapes against the real signatures.
    manifest = _write_empty_manifest(tmp_path)
    layout = _write_pluginless_layout(tmp_path)
    output = tmp_path / "report.html"

    code = main(["build", str(manifest), str(layout), "-o", str(output)])

    assert code == 0
    page = output.read_text(encoding="utf-8")
    assert page.lstrip().startswith("<!doctype html>")
    # The page carries the layout's own title, read from the payload
    # rather than hardcoded.
    title = make_layout_payload()["title"]
    assert isinstance(title, str)
    assert f"<title>{title}</title>" in page
    # The missing component reached the document: its notice card is
    # the honest-report vocabulary for a placed-but-absent component.
    assert "coda-card--notice" in page
    assert "This report was generated by workflow-coda" in page
    out, err = capsys.readouterr()
    assert out == ""
    assert err == ""


# ---------------------------------------------------------------------------
# The exit-1 family: the framework and the destination speak on
# stderr; stdout stays silent
# ---------------------------------------------------------------------------


def _clean_failure(capsys: pytest.CaptureFixture[str]) -> str:
    """Drain the streams after a failed command and return stderr:
    nothing on stdout, a message on stderr, never a traceback — the
    boundary contract asserted once, here."""
    out, err = capsys.readouterr()
    assert out == ""
    assert err.strip() != ""
    assert "Traceback" not in err
    return err


def _write_factory_layout(tmp_path: Path) -> Path:
    """The suite's factory layout serialized untouched: places its
    component with the *default* missing-component tolerance —
    refusal."""
    layout = tmp_path / "report_layout.yaml"
    layout.write_text(yaml.safe_dump(make_layout_payload()), encoding="utf-8")
    return layout


def _tiny_inputs(tmp_path: Path) -> tuple[Path, Path]:
    """Two parse-valid input files whose content is never read: the
    destination pre-flight refuses before the pipeline runs, so these
    tests need no valid manifest or layout content at all."""
    manifest = tmp_path / "report_manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    layout = tmp_path / "report_layout.yaml"
    layout.write_text("title: x\n", encoding="utf-8")
    return manifest, layout


@pytest.mark.parametrize("content", ["{}", "{ not json"])
def test_broken_manifest_content_fails_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str
) -> None:
    # Both cases are boundary pins: a valid-JSON-but-invalid manifest,
    # and a file that is not JSON at all — the loader is expected to
    # wrap each in its teaching message, which names the file.
    manifest = tmp_path / "report_manifest.json"
    manifest.write_text(content, encoding="utf-8")
    layout = _write_factory_layout(tmp_path)
    code = main(["build", str(manifest), str(layout), "-o", str(tmp_path / "out.html")])
    assert code == 1
    err = _clean_failure(capsys)
    assert "report_manifest.json" in err


@pytest.mark.parametrize(
    ("content", "pin"),
    [
        ("title: Metagenomic analysis\n", "is not a valid report layout"),
        ("{ not yaml", "report_layout.yaml"),
    ],
)
def test_broken_layout_content_fails_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str, pin: str
) -> None:
    # The incomplete layout's message shape is pinned verbatim from a
    # real failure; the non-YAML case is a boundary pin — the loader is
    # expected to wrap the decoder error, and this test says so.
    manifest = _write_empty_manifest(tmp_path)
    layout = tmp_path / "report_layout.yaml"
    layout.write_text(content, encoding="utf-8")
    code = main(["build", str(manifest), str(layout), "-o", str(tmp_path / "out.html")])
    assert code == 1
    err = _clean_failure(capsys)
    assert pin in err


def test_missing_plugin_fails_fast_without_on_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The earned pin: the default tolerance is refusal — the placed
    # component's plugin is not installed (the dev environment has
    # none), and the build fails with the teaching message naming all
    # three fixes.  Pins today's plugin-less dev environment; the
    # example-plugin milestone will revisit this seam.
    manifest = _write_empty_manifest(tmp_path)
    layout = _write_factory_layout(tmp_path)
    code = main(["build", str(manifest), str(layout), "-o", str(tmp_path / "out.html")])
    assert code == 1
    err = _clean_failure(capsys)
    assert "no loaded plugin supporting manifest schema version" in err
    assert "set on_missing: notice or skip" in err


# ---------------------------------------------------------------------------
# The destination pre-flight: fail fast, not finally
# ---------------------------------------------------------------------------


def test_missing_parent_directory_is_refused_before_the_pipeline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Ordering pin: the manifest is deliberately broken ({} never
    # validates), so if stderr carries the destination's refusal, the
    # pre-flight ran first — the cheap check saved the pipeline's work.
    manifest, layout = _tiny_inputs(tmp_path)
    output = tmp_path / "missing_dir" / "report.html"
    code = main(["build", str(manifest), str(layout), "-o", str(output)])
    assert code == 1
    err = _clean_failure(capsys)
    assert "could not write the report to" in err
    assert "does not exist" in err


def test_parent_is_a_file_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest, layout = _tiny_inputs(tmp_path)
    blocker = tmp_path / "blocker"
    blocker.write_text("occupied\n", encoding="utf-8")
    code = main(
        ["build", str(manifest), str(layout), "-o", str(blocker / "report.html")]
    )
    assert code == 1
    err = _clean_failure(capsys)
    assert "is not a directory" in err


def test_output_is_a_directory_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A directory can carry any name — even report.html, whose suffix
    # passes the parse-time extension check.  The pre-flight's
    # file-level branch is what refuses it.
    manifest, layout = _tiny_inputs(tmp_path)
    output = tmp_path / "report.html"
    output.mkdir()
    code = main(["build", str(manifest), str(layout), "-o", str(output)])
    assert code == 1
    err = _clean_failure(capsys)
    assert "is a directory" in err


def _deny_writes_for(monkeypatch: pytest.MonkeyPatch, target: Path) -> None:
    """Deny ``os.access`` write checks (W_OK) for exactly *target*,
    delegating every other check untouched — each pre-flight branch is
    reached with the earlier checks genuinely passing, and no platform
    permission games: the wrapper makes POSIX and Windows behave
    identically for the test.  The path is normalized through
    ``os.fsdecode`` because ``os.access`` accepts bytes-shaped paths
    that ``Path`` alone does not."""
    real_access = os.access

    def fake_access(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes], mode: int
    ) -> bool:
        if mode == os.W_OK and Path(os.fsdecode(path)) == target:
            return False
        return real_access(path, mode)

    monkeypatch.setattr(os, "access", fake_access)


def test_unwritable_parent_directory_is_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_writes_for(monkeypatch, tmp_path)
    manifest, layout = _tiny_inputs(tmp_path)
    code = main(
        ["build", str(manifest), str(layout), "-o", str(tmp_path / "report.html")]
    )
    assert code == 1
    err = _clean_failure(capsys)
    assert "could not write the report to" in err
    assert "is not writable" in err


def test_read_only_output_file_is_refused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The branch with real teeth on Windows: an existing read-only
    # file at the destination (W_OK honors the read-only attribute
    # there).  The parent's checks pass untouched — only the file is
    # denied.
    manifest, layout = _tiny_inputs(tmp_path)
    output = tmp_path / "report.html"
    output.write_text("previous report\n", encoding="utf-8")
    _deny_writes_for(monkeypatch, output)
    code = main(["build", str(manifest), str(layout), "-o", str(output)])
    assert code == 1
    err = _clean_failure(capsys)
    assert "not writable" in err


# ---------------------------------------------------------------------------
# The write itself: the report succeeded, the destination refused
# ---------------------------------------------------------------------------


def test_write_failure_at_the_write_fails_clean(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The pre-flight passed and the page rendered; the write itself
    # refused (disk full is the classic check-proof failure).  The
    # same clean exit-1 message covers both moments of truth.
    manifest, layout = _tiny_inputs(tmp_path)
    _patched_pipeline(monkeypatch, "the page")
    output = tmp_path / "report.html"

    def refuse(*_args: object, **_kwargs: object) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", refuse)
    code = main(["build", str(manifest), str(layout), "-o", str(output)])
    assert code == 1
    err = _clean_failure(capsys)
    assert "could not write the report to" in err
    assert "disk full" in err


def test_render_error_fails_clean(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The render family rides the same boundary: a document whose
    # figures the environment cannot inline.  The pipeline is patched
    # because the CLI's job here is only the routing; the real message
    # is pinned in the renderer suite.
    manifest, layout = _tiny_inputs(tmp_path)
    _patched_pipeline(monkeypatch, "unused")

    def refusing_render(_document: object) -> str:
        raise RenderError("Install plotly to inline figures into the report.")

    monkeypatch.setattr(cli, "render_report", refusing_render)
    code = main(
        ["build", str(manifest), str(layout), "-o", str(tmp_path / "report.html")]
    )
    assert code == 1
    err = _clean_failure(capsys)
    assert "Install plotly" in err


# ---------------------------------------------------------------------------
# Version placement: a root-parser convention
# ---------------------------------------------------------------------------


def test_version_flag_on_root_parser_only(capsys: pytest.CaptureFixture[str]) -> None:
    # The confirmed convention: --version is a root-parser feature
    # (git, pip).  `build -v` is a usage error, not a version print —
    # were the version action inherited, it would print to stdout and
    # exit 0.  Pinned as properties, not wording: exit 2, nothing on
    # stdout, an error on stderr.  (With the required positionals
    # absent, argparse reports those; with them present, it reports
    # the unrecognized flag — either way the boundary is the exit
    # code and the silent stdout, and neither spelling is ours to
    # contract.)
    with pytest.raises(SystemExit) as raised:
        main(["build", "-v"])
    assert raised.value.code == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert err.strip() != ""
