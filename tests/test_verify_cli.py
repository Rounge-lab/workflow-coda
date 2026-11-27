"""Tests for the verify subcommand: the pipeline hand's door.

The command's contract, executable — black-box through :func:`main`:
the create/append/update lifecycle, the conflict and producer
teachings, the ``--on-failure`` toggle both ways, spec mode's
aggregation and atomicity, and the output lines byte-for-byte.
The suite writes every manifest through the command itself, so
every fixture is a real round trip by construction.
"""

import hashlib
import json
from pathlib import Path
from typing import Final

import pytest

from workflow_coda.cli import main
from workflow_coda.manifest import (
    MANIFEST_SCHEMA_VERSION,
    ArtifactStatus,
    load_manifest,
)

_PRODUCER_FLAGS: Final[tuple[str, ...]] = (
    "--producer-name",
    "fungifunk-pipeline",
    "--producer-version",
    "1.3",
)

_GOOD_SPEC: Final[str] = """\
producer:
  name: fungifunk-pipeline
  version: "1.3"
artifacts:
  - file: samples.tsv
    id: samples
    type: org.example.samples
    format: core.tabular
    schema_version: "1.0.0"
    criteria:
      columns: [sample_id, depth]
      min_rows: 4
  - file: stats.json
    id: stats
    type: org.example.stats
    format: json
    schema_version: "1.0.0"
    criteria:
      keys: [depth, rate]
"""


def _stats_json(tmp_path: Path) -> Path:
    """The stats artifact: the JSON shape core.kpi and core.markdown read."""
    file = tmp_path / "stats.json"
    file.write_text(json.dumps({"depth": 12.4, "rate": 98.2}), encoding="utf-8")
    return file


def _samples_tsv(tmp_path: Path) -> Path:
    """The samples artifact: headered, four data rows — real tabs, written
    as explicit escapes so the fixture's bytes are unambiguous."""
    rows = [
        "sample_id\tdepth\tstatus",
        "S1\t9\tpassed",
        "S2\t100\tfailed",
        "S3\t10\tpassed",
        "S4\t\tpending",
    ]
    file = tmp_path / "samples.tsv"
    file.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return file


def _identity(id_: str, type_: str, fmt: str) -> list[str]:
    """The flags-mode identity block for one artifact."""
    return [
        "--id",
        id_,
        "--type",
        type_,
        "--format",
        fmt,
        "--schema-version",
        "1.0.0",
    ]


def _verify(*args: str | Path) -> int:
    """One black-box verify invocation."""
    return main(["verify", *(str(arg) for arg in args)])


def _write_spec(tmp_path: Path, text: str) -> Path:
    spec = tmp_path / "spec.yaml"
    spec.write_text(text, encoding="utf-8")
    return spec


# ---------------------------------------------------------------------------
# The door
# ---------------------------------------------------------------------------


def test_verify_answers_help(capsys: pytest.CaptureFixture[str]) -> None:
    # The subcommand's existence, read through its own help: the
    # MANIFEST-first usage the two modes share.
    with pytest.raises(SystemExit) as excinfo:
        _verify("--help")
    assert excinfo.value.code == 0
    assert "MANIFEST" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Flags mode: the lifecycle
# ---------------------------------------------------------------------------


def test_flags_mode_creates_a_verified_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "manifest.json"
    stats = _stats_json(tmp_path)
    code = _verify(
        manifest,
        stats,
        *_identity("stats", "org.example.stats", "json"),
        "--criteria",
        "keys=depth,rate",
        *_PRODUCER_FLAGS,
    )
    assert code == 0
    assert capsys.readouterr().out == (
        f"created {manifest} (producer fungifunk-pipeline 1.3) "
        f"— verified and appended artifact stats\n"
    )
    loaded = load_manifest(manifest)
    assert loaded.schema_version == MANIFEST_SCHEMA_VERSION
    assert loaded.producer.name == "fungifunk-pipeline"
    assert loaded.producer.version == "1.3"
    artifact = loaded.artifacts[0]
    assert artifact.id == "stats"
    assert artifact.type == "org.example.stats"
    assert artifact.format == "json"
    assert artifact.schema_version == "1.0.0"
    assert artifact.path == "stats.json"
    assert artifact.status is ArtifactStatus.COMPLETE
    assert artifact.sha256 == hashlib.sha256(stats.read_bytes()).hexdigest()
    assert artifact.verification == {
        "format": "json",
        "status": "ok",
        "keys_checked": ["depth", "rate"],
    }


def test_created_line_carries_the_run_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "manifest.json"
    stats = _stats_json(tmp_path)
    code = _verify(
        manifest,
        stats,
        *_identity("stats", "org.example.stats", "json"),
        "--run-id",
        "run7",
        *_PRODUCER_FLAGS,
    )
    assert code == 0
    assert capsys.readouterr().out == (
        f"created {manifest} (producer fungifunk-pipeline 1.3, run run7) "
        f"— verified and appended artifact stats\n"
    )


def test_append_omitting_producer_flags(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Match-or-omit: one manifest, one producer — appending needs no
    # producer flags at all.
    manifest = tmp_path / "manifest.json"
    _stats_json(tmp_path)
    assert (
        _verify(
            manifest,
            tmp_path / "stats.json",
            *_identity("stats", "org.example.stats", "json"),
            *_PRODUCER_FLAGS,
        )
        == 0
    )
    capsys.readouterr()  # drain the created line
    counts = tmp_path / "counts.json"
    counts.write_text(json.dumps({"n": 2}), encoding="utf-8")
    code = _verify(manifest, counts, *_identity("counts", "org.example.counts", "json"))
    assert code == 0
    assert capsys.readouterr().out == (
        f"verified {counts} — appended artifact counts to {manifest}\n"
    )
    loaded = load_manifest(manifest)
    assert [a.id for a in loaded.artifacts] == ["stats", "counts"]


def test_update_replaces_bytes_and_keeps_position(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The rerun story: same id, same type — new bytes, new checksum,
    # new record, and the declaration keeps its place in the list.
    manifest = tmp_path / "manifest.json"
    stats = _stats_json(tmp_path)
    assert (
        _verify(
            manifest,
            stats,
            *_identity("stats", "org.example.stats", "json"),
            *_PRODUCER_FLAGS,
        )
        == 0
    )
    old_sha = load_manifest(manifest).artifacts[0].sha256
    counts = tmp_path / "counts.json"
    counts.write_text(json.dumps({"n": 2}), encoding="utf-8")
    assert (
        _verify(manifest, counts, *_identity("counts", "org.example.counts", "json"))
        == 0
    )
    capsys.readouterr()
    stats.write_text(json.dumps({"depth": 99, "rate": 1}), encoding="utf-8")
    code = _verify(manifest, stats, *_identity("stats", "org.example.stats", "json"))
    assert code == 0
    assert capsys.readouterr().out == (
        f"verified {stats} — updated artifact stats in {manifest}\n"
    )
    loaded = load_manifest(manifest)
    assert [a.id for a in loaded.artifacts] == ["stats", "counts"]
    assert loaded.artifacts[0].sha256 == hashlib.sha256(stats.read_bytes()).hexdigest()
    assert loaded.artifacts[0].sha256 != old_sha


def test_same_id_different_type_teaches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "manifest.json"
    _stats_json(tmp_path)
    assert (
        _verify(
            manifest,
            tmp_path / "stats.json",
            *_identity("stats", "org.example.stats", "json"),
            *_PRODUCER_FLAGS,
        )
        == 0
    )
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"x": 1}), encoding="utf-8")
    code = _verify(manifest, other, *_identity("stats", "org.example.other", "json"))
    assert code == 1
    assert "already declared" in capsys.readouterr().err


def test_new_id_colliding_type_teaches_both_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The store resolves by type, so two artifacts may not share one —
    # the teaching names the type, the resident id, and the newcomer.
    manifest = tmp_path / "manifest.json"
    _stats_json(tmp_path)
    assert (
        _verify(
            manifest,
            tmp_path / "stats.json",
            *_identity("stats", "org.example.stats", "json"),
            *_PRODUCER_FLAGS,
        )
        == 0
    )
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"x": 1}), encoding="utf-8")
    code = _verify(manifest, other, *_identity("stats2", "org.example.stats", "json"))
    assert code == 1
    err = capsys.readouterr().err
    assert "resolves artifacts by type" in err
    assert "'stats2'" in err
    assert "'stats'" in err


def test_producer_mismatch_teaches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "manifest.json"
    _stats_json(tmp_path)
    assert (
        _verify(
            manifest,
            tmp_path / "stats.json",
            *_identity("stats", "org.example.stats", "json"),
            *_PRODUCER_FLAGS,
        )
        == 0
    )
    code = _verify(
        manifest,
        tmp_path / "stats.json",
        *_identity("stats", "org.example.stats", "json"),
        "--producer-name",
        "other-pipeline",
        "--producer-version",
        "9.9",
    )
    assert code == 1
    assert "one producer" in capsys.readouterr().err


def test_run_id_mismatch_teaches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "manifest.json"
    _stats_json(tmp_path)
    assert (
        _verify(
            manifest,
            tmp_path / "stats.json",
            *_identity("stats", "org.example.stats", "json"),
            "--run-id",
            "run7",
            *_PRODUCER_FLAGS,
        )
        == 0
    )
    code = _verify(
        manifest,
        tmp_path / "stats.json",
        *_identity("stats", "org.example.stats", "json"),
        "--run-id",
        "run8",
    )
    assert code == 1
    assert "one run" in capsys.readouterr().err


@pytest.mark.parametrize("old_version", ["0.2.0", "0.3.0"])
def test_old_schema_manifest_teaches_regeneration(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    old_version: str,
) -> None:
    # Earlier manifest envelopes are not appended to: the loader
    # names the rejected version and teaches regeneration.
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": old_version,
                "producer": {"name": "p", "version": "1"},
                "artifacts": [],
            }
        ),
        encoding="utf-8",
    )
    stats = _stats_json(tmp_path)
    code = _verify(manifest, stats, *_identity("stats", "org.example.stats", "json"))
    assert code == 1
    err = capsys.readouterr().err
    assert old_version in err
    assert "regenerate" in err


def test_corrupt_manifest_teaches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{nope", encoding="utf-8")
    stats = _stats_json(tmp_path)
    code = _verify(manifest, stats, *_identity("stats", "org.example.stats", "json"))
    assert code == 1
    assert "not valid JSON" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Verification outcomes: the toggle
# ---------------------------------------------------------------------------


def test_verification_failure_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The default owner is the pipeline graph: a failing verification
    # exits 1 and the manifest is not created at all.
    manifest = tmp_path / "manifest.json"
    stats = tmp_path / "stats.json"
    stats.write_text(json.dumps({"depth": 12.4}), encoding="utf-8")
    code = _verify(
        manifest,
        stats,
        *_identity("stats", "org.example.stats", "json"),
        "--criteria",
        "keys=missing",
        *_PRODUCER_FLAGS,
    )
    assert code == 1
    assert "names 'missing'" in capsys.readouterr().err
    assert not manifest.exists()


def test_failure_under_write_is_recorded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The other owner: the report.  Under write, the failed
    # verification is the artifact's honest status, the teaching
    # rides the record, the warning rides stderr, and the exit
    # code reflects the write.
    manifest = tmp_path / "manifest.json"
    stats = tmp_path / "stats.json"
    stats.write_text(json.dumps({"depth": 12.4}), encoding="utf-8")
    code = _verify(
        manifest,
        stats,
        *_identity("stats", "org.example.stats", "json"),
        "--criteria",
        "keys=missing",
        "--on-failure",
        "write",
        *_PRODUCER_FLAGS,
    )
    assert code == 0
    captured = capsys.readouterr()
    assert captured.out == (
        f"created {manifest} (producer fungifunk-pipeline 1.3) "
        f"— recorded artifact stats as failed\n"
    )
    assert "recorded as failed" in captured.err
    assert "names 'missing'" in captured.err
    artifact = load_manifest(manifest).artifacts[0]
    assert artifact.status is ArtifactStatus.FAILED
    assert artifact.verification is not None
    assert artifact.verification["status"] == "failed"
    assert "names 'missing'" in str(artifact.verification["message"])


# ---------------------------------------------------------------------------
# The invocation grammar
# ---------------------------------------------------------------------------


def test_flags_identity_missing_teaches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "manifest.json"
    stats = _stats_json(tmp_path)
    code = _verify(manifest, stats, "--type", "org.example.stats", "--format", "json")
    assert code == 1
    assert "flags mode requires" in capsys.readouterr().err


def test_spec_and_file_positional_are_exclusive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # One mode per invocation: the FILE positional belongs to flags
    # mode, --spec to spec mode, and both at once is an authoring
    # mistake taught, not guessed.
    manifest = tmp_path / "manifest.json"
    stats = _stats_json(tmp_path)
    spec = _write_spec(tmp_path, _GOOD_SPEC)
    code = _verify(manifest, stats, "--spec", spec)
    assert code == 1
    assert "not both" in capsys.readouterr().err


def test_criteria_without_equals_teaches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "manifest.json"
    stats = _stats_json(tmp_path)
    code = _verify(
        manifest,
        stats,
        *_identity("stats", "org.example.stats", "json"),
        "--criteria",
        "noequals",
        *_PRODUCER_FLAGS,
    )
    assert code == 1
    assert "KEY=VALUE" in capsys.readouterr().err


def test_extension_contracts_are_usage_errors(tmp_path: Path) -> None:
    # The extension is the invocation's content contract — exit 2
    # before anything runs, for both the manifest and the spec.
    stats = _stats_json(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        _verify(tmp_path / "manifest.txt", stats, *_identity("s", "t", "json"))
    assert excinfo.value.code == 2
    bad_spec = tmp_path / "spec.txt"
    bad_spec.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit) as excinfo:
        _verify(tmp_path / "manifest.json", "--spec", bad_spec)
    assert excinfo.value.code == 2


def test_missing_file_is_a_usage_error(
    tmp_path: Path,
) -> None:
    # Flags mode's FILE positional is input-checked like build's
    # inputs — a missing artifact file is a bad invocation, exit 2
    # (spec mode's files resolve at runtime instead, and may be
    # recorded as failed under write — the asymmetry is the design).
    manifest = tmp_path / "manifest.json"
    with pytest.raises(SystemExit) as excinfo:
        _verify(
            manifest,
            tmp_path / "ghost.json",
            *_identity("stats", "org.example.stats", "json"),
        )
    assert excinfo.value.code == 2


def test_unknown_format_teaches_available_formats(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "manifest.json"
    stats = _stats_json(tmp_path)
    code = _verify(
        manifest, stats, *_identity("stats", "org.example.stats", "bio.newick")
    )
    assert code == 1
    err = capsys.readouterr().err
    assert "offers a verifier for format 'bio.newick'" in err
    assert "available:" in err


def test_flag_criteria_are_string_transport(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The CLI never splits a comma: 'columns=sample_id,depth' rides
    # as one string to the verifier, whose grammar accepts it —
    # and the record shows what was checked under which reading.
    manifest = tmp_path / "manifest.json"
    samples = _samples_tsv(tmp_path)
    code = _verify(
        manifest,
        samples,
        *_identity("samples", "org.example.samples", "core.tabular"),
        "--criteria",
        "columns=sample_id,depth",
        "--criteria",
        "min_rows=4",
        *_PRODUCER_FLAGS,
    )
    assert code == 0
    capsys.readouterr()
    artifact = load_manifest(manifest).artifacts[0]
    assert artifact.verification == {
        "format": "core.tabular",
        "status": "ok",
        "sep": "\t",
        "header": True,
        "rows": 4,
        "columns_checked": ["sample_id", "depth"],
        "min_rows": 4,
    }


# ---------------------------------------------------------------------------
# Spec mode
# ---------------------------------------------------------------------------


def test_spec_creates_and_summarizes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stats_json(tmp_path)
    _samples_tsv(tmp_path)
    manifest = tmp_path / "manifest.json"
    spec = _write_spec(tmp_path, _GOOD_SPEC)
    code = _verify(manifest, "--spec", spec)
    assert code == 0
    assert capsys.readouterr().out == (
        f"created {manifest} (producer fungifunk-pipeline 1.3) "
        f"— verified 2 artifacts — appended 2, updated 0\n"
    )
    loaded = load_manifest(manifest)
    assert [a.id for a in loaded.artifacts] == ["samples", "stats"]
    assert all(
        a.verification is not None and a.verification["status"] == "ok"
        for a in loaded.artifacts
    )


def test_spec_append_summary_counts_updates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Spec mode meets an existing manifest: new ids append, a known
    # id+type updates — the summary counts both.
    manifest = tmp_path / "manifest.json"
    _stats_json(tmp_path)
    assert (
        _verify(
            manifest,
            tmp_path / "stats.json",
            *_identity("stats", "org.example.stats", "json"),
            *_PRODUCER_FLAGS,
        )
        == 0
    )
    capsys.readouterr()
    _samples_tsv(tmp_path)
    spec = _write_spec(tmp_path, _GOOD_SPEC)
    code = _verify(manifest, "--spec", spec)
    assert code == 0
    assert capsys.readouterr().out == (
        f"verified 2 artifacts — appended 1, updated 1 in {manifest}\n"
    )


def test_spec_is_all_or_nothing_under_fail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # One bad artifact refuses the whole batch, and the existing
    # manifest is byte-identical after — no torn half-batches.
    manifest = tmp_path / "manifest.json"
    _stats_json(tmp_path)
    assert (
        _verify(
            manifest,
            tmp_path / "stats.json",
            *_identity("stats", "org.example.stats", "json"),
            *_PRODUCER_FLAGS,
        )
        == 0
    )
    capsys.readouterr()
    before = manifest.read_bytes()
    _samples_tsv(tmp_path)
    spec = _write_spec(
        tmp_path,
        _GOOD_SPEC
        + """\
  - file: ghost.tsv
    id: ghost
    type: org.example.ghost
    format: core.tabular
    schema_version: "1.0.0"
""",
    )
    code = _verify(manifest, "--spec", spec)
    assert code == 1
    assert "does not exist" in capsys.readouterr().err
    assert manifest.read_bytes() == before


def test_spec_aggregates_every_problem(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The merged-validator shape: every problem reported, one line
    # each, nothing written.
    manifest = tmp_path / "manifest.json"
    stats = tmp_path / "stats.json"
    stats.write_text(json.dumps({"depth": 12.4}), encoding="utf-8")
    samples = _samples_tsv(tmp_path)
    spec = _write_spec(
        tmp_path,
        f"""\
producer:
  name: fungifunk-pipeline
  version: "1.3"
artifacts:
  - file: {samples.name}
    id: samples
    type: org.example.samples
    format: core.tabular
    schema_version: "1.0.0"
    criteria:
      min_rows: 99
  - file: {stats.name}
    id: stats
    type: org.example.stats
    format: json
    schema_version: "1.0.0"
    criteria:
      keys: [missing1]
""",
    )
    code = _verify(manifest, "--spec", spec)
    assert code == 1
    err = capsys.readouterr().err
    assert "requires at least 99" in err
    assert "names 'missing1'" in err


def test_spec_write_records_mixed_outcomes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _samples_tsv(tmp_path)
    stats = tmp_path / "stats.json"
    stats.write_text(json.dumps({"depth": 12.4}), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    spec = _write_spec(
        tmp_path,
        """\
producer:
  name: fungifunk-pipeline
  version: "1.3"
artifacts:
  - file: samples.tsv
    id: samples
    type: org.example.samples
    format: core.tabular
    schema_version: "1.0.0"
    criteria:
      min_rows: 4
  - file: stats.json
    id: stats
    type: org.example.stats
    format: json
    schema_version: "1.0.0"
    criteria:
      keys: [missing]
""",
    )
    code = _verify(manifest, "--spec", spec, "--on-failure", "write")
    assert code == 0
    captured = capsys.readouterr()
    assert captured.out == (
        f"verified 1 artifact — appended 1, updated 0, "
        f"1 recorded as failed in {manifest}\n"
    )
    assert "recorded as failed" in captured.err
    assert "names 'missing'" in captured.err
    loaded = load_manifest(manifest)
    assert [a.status for a in loaded.artifacts] == [
        ArtifactStatus.COMPLETE,
        ArtifactStatus.FAILED,
    ]


def test_spec_missing_file_under_write_is_recorded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A missing output is the run's honest fact: under write it is
    # recorded as failed (exit 0, the write happened); under fail it
    # is the teaching (exit 1, nothing written).
    manifest = tmp_path / "manifest.json"
    spec = _write_spec(
        tmp_path,
        """\
producer:
  name: fungifunk-pipeline
  version: "1.3"
artifacts:
  - file: ghost.tsv
    id: ghost
    type: org.example.ghost
    format: core.tabular
    schema_version: "1.0.0"
""",
    )
    code = _verify(manifest, "--spec", spec, "--on-failure", "write")
    assert code == 0
    captured = capsys.readouterr()
    assert "does not exist" in captured.err
    artifact = load_manifest(manifest).artifacts[0]
    assert artifact.status is ArtifactStatus.FAILED
    assert artifact.verification is not None
    assert "does not exist" in str(artifact.verification["message"])
    code = _verify(manifest, "--spec", spec)
    assert code == 1
    assert "does not exist" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# The spec loader's teachings
# ---------------------------------------------------------------------------


def test_spec_duplicate_key_teaches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "manifest.json"
    spec = _write_spec(
        tmp_path,
        """\
producer:
  name: p
  version: "1"
artifacts:
  - file: stats.json
    file: counts.json
    id: stats
    type: org.example.stats
    format: json
    schema_version: "1.0.0"
""",
    )
    code = _verify(manifest, "--spec", spec)
    assert code == 1
    assert "duplicate key 'file'" in capsys.readouterr().err


def test_spec_boolean_trap_teaches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The hand-authored-file law: bare yes/no are booleans in YAML —
    # the spec loader explains the quoting rule, not pydantic's
    # opaque type error.
    manifest = tmp_path / "manifest.json"
    _stats_json(tmp_path)
    spec = _write_spec(
        tmp_path,
        """\
producer:
  name: p
  version: "1"
artifacts:
  - file: stats.json
    id: yes
    type: org.example.stats
    format: json
    schema_version: "1.0.0"
""",
    )
    code = _verify(manifest, "--spec", spec)
    assert code == 1
    err = capsys.readouterr().err
    assert "booleans in YAML" in err
    assert "Quote the word" in err


def test_spec_invalid_yaml_teaches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "manifest.json"
    spec = _write_spec(tmp_path, "producer: {name: p\n  version: '1'\n")
    code = _verify(manifest, "--spec", spec)
    assert code == 1
    assert "not valid YAML" in capsys.readouterr().err


def test_spec_must_be_a_mapping(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "manifest.json"
    spec = _write_spec(tmp_path, "- a\n- b\n")
    code = _verify(manifest, "--spec", spec)
    assert code == 1
    assert "must be a mapping" in capsys.readouterr().err


def test_spec_requires_artifacts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A spec that verifies nothing is an authoring mistake.
    manifest = tmp_path / "manifest.json"
    spec = _write_spec(
        tmp_path,
        'producer:\n  name: p\n  version: "1"\nartifacts: []\n',
    )
    code = _verify(manifest, "--spec", spec)
    assert code == 1
    assert "at least one" in capsys.readouterr().err


def test_producerless_spec_create_requires_resolved_identity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "manifest.json"
    _stats_json(tmp_path)
    spec = _write_spec(
        tmp_path,
        """\
artifacts:
  - file: stats.json
    id: stats
    type: org.example.stats
    format: json
    schema_version: "1.0.0"
""",
    )
    code = _verify(manifest, "--spec", spec)
    assert code == 1
    assert "requires a producer identity" in capsys.readouterr().err
    assert not manifest.exists()


@pytest.mark.parametrize(
    ("producer", "flags"),
    [
        ("", _PRODUCER_FLAGS),
        (
            "producer:\n  name: fungifunk-pipeline\n",
            ("--producer-version", "1.3"),
        ),
        (
            'producer:\n  version: "1.3"\n',
            ("--producer-name", "fungifunk-pipeline"),
        ),
        (
            'producer:\n  name: fungifunk-pipeline\n  version: "1.3"\n',
            _PRODUCER_FLAGS,
        ),
    ],
)
def test_spec_create_merges_producer_claims(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    producer: str,
    flags: tuple[str, ...],
) -> None:
    manifest = tmp_path / "manifest.json"
    _stats_json(tmp_path)
    spec = _write_spec(
        tmp_path,
        producer
        + """\
artifacts:
  - file: stats.json
    id: stats
    type: org.example.stats
    format: json
    schema_version: "1"
""",
    )
    assert _verify(manifest, "--spec", spec, *flags) == 0
    capsys.readouterr()
    loaded = load_manifest(manifest)
    assert loaded.producer.name == "fungifunk-pipeline"
    assert loaded.producer.version == "1.3"


@pytest.mark.parametrize(
    "producer",
    [
        "",
        "producer: {}\n",
        "producer:\n  name: fungifunk-pipeline\n",
        'producer:\n  version: "1.3"\n',
    ],
)
def test_spec_update_retains_omitted_producer_claims(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    producer: str,
) -> None:
    manifest = tmp_path / "manifest.json"
    stats = _stats_json(tmp_path)
    assert (
        _verify(
            manifest,
            stats,
            *_identity("stats", "org.example.stats", "json"),
            *_PRODUCER_FLAGS,
            "--run-id",
            "run7",
        )
        == 0
    )
    capsys.readouterr()
    before = load_manifest(manifest).producer
    spec = _write_spec(
        tmp_path,
        producer
        + """\
artifacts:
  - file: stats.json
    id: stats
    type: org.example.stats
    format: json
    schema_version: "1"
""",
    )
    assert _verify(manifest, "--spec", spec) == 0
    capsys.readouterr()
    assert load_manifest(manifest).producer == before


@pytest.mark.parametrize("mode", ["flags", "spec"])
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("on_failure", ["fail", "write"])
@pytest.mark.parametrize(
    "flag",
    ["--producer-name", "--producer-version", "--run-id"],
)
def test_empty_producer_claim_refuses_before_verification(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    existing: bool,
    on_failure: str,
    flag: str,
) -> None:
    manifest = tmp_path / "manifest.json"
    stats = _stats_json(tmp_path)
    before: bytes | None = None
    if existing:
        assert (
            _verify(
                manifest,
                stats,
                *_identity("stats", "org.example.stats", "json"),
                *_PRODUCER_FLAGS,
            )
            == 0
        )
        capsys.readouterr()
        before = manifest.read_bytes()

    def unexpected_verification(*args: object, **kwargs: object) -> None:
        pytest.fail("invalid producer claim reached artifact verification")

    monkeypatch.setattr(
        "workflow_coda.verification.drivers.verify_artifact_file",
        unexpected_verification,
    )
    if mode == "flags":
        args: list[str | Path] = [
            stats,
            *_identity("stats", "org.example.stats", "json"),
        ]
    else:
        args = ["--spec", _write_spec(tmp_path, _GOOD_SPEC)]

    assert _verify(manifest, *args, flag, "", "--on-failure", on_failure) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert flag in captured.err
    assert "non-empty string" in captured.err
    if existing:
        assert manifest.read_bytes() == before
    else:
        assert not manifest.exists()


def test_spec_producer_must_match_on_append(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "manifest.json"
    _stats_json(tmp_path)
    assert (
        _verify(
            manifest,
            tmp_path / "stats.json",
            *_identity("stats", "org.example.stats", "json"),
            *_PRODUCER_FLAGS,
        )
        == 0
    )
    capsys.readouterr()
    spec = _write_spec(
        tmp_path,
        """\
producer:
  name: other-pipeline
  version: "9"
artifacts:
  - file: stats.json
    id: stats2
    type: org.example.stats2
    format: json
    schema_version: "1.0.0"
""",
    )
    code = _verify(manifest, "--spec", spec)
    assert code == 1
    assert "one producer" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# The writer
# ---------------------------------------------------------------------------


def test_writer_byte_discipline(tmp_path: Path) -> None:
    # Model-built, indent 2, field order preserved, exactly one
    # trailing newline, no BOM — the manifest the loader reads back
    # is the manifest the writer meant.
    manifest = tmp_path / "manifest.json"
    _stats_json(tmp_path)
    assert (
        _verify(
            manifest,
            tmp_path / "stats.json",
            *_identity("stats", "org.example.stats", "json"),
            *_PRODUCER_FLAGS,
        )
        == 0
    )
    text = manifest.read_text(encoding="utf-8")
    assert text.startswith(
        f'{{\n  "schema_version": "{MANIFEST_SCHEMA_VERSION}",\n  "producer": {{\n'
    )
    assert text.endswith("}\n")
    assert not text.endswith("\n\n")
    assert '"id": "stats"' in text


@pytest.mark.parametrize("failed", [False, True])
def test_flags_module_attribution_survives_recorded_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    failed: bool,
) -> None:
    manifest = tmp_path / "manifest.json"
    stats = _stats_json(tmp_path)
    if failed:
        stats.write_text("{invalid", encoding="utf-8")

    assert (
        _verify(
            manifest,
            stats,
            *_identity("stats", "org.example.stats", "json"),
            *_PRODUCER_FLAGS,
            "--module-id",
            "quality-control",
            "--on-failure",
            "write",
        )
        == 0
    )
    capsys.readouterr()
    loaded = load_manifest(manifest)
    artifact = loaded.artifacts[0]
    assert artifact.module_id == "quality-control"
    assert artifact.status is (
        ArtifactStatus.FAILED if failed else ArtifactStatus.COMPLETE
    )
    if failed:
        assert artifact.sha256 is None
    assert "module_id" not in loaded.producer.model_dump()


def test_different_modules_can_append_to_one_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = tmp_path / "manifest.json"
    stats = _stats_json(tmp_path)
    samples = _samples_tsv(tmp_path)

    assert (
        _verify(
            manifest,
            stats,
            *_identity("stats", "org.example.stats", "json"),
            *_PRODUCER_FLAGS,
            "--module-id",
            "quality-control",
        )
        == 0
    )
    assert (
        _verify(
            manifest,
            samples,
            *_identity("samples", "org.example.samples", "core.tabular"),
            "--module-id",
            "alignment",
        )
        == 0
    )
    capsys.readouterr()
    assert [a.module_id for a in load_manifest(manifest).artifacts] == [
        "quality-control",
        "alignment",
    ]


def test_spec_records_per_artifact_modules_and_invocation_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = tmp_path / "manifest.json"
    _samples_tsv(tmp_path)
    _stats_json(tmp_path).write_text("{invalid", encoding="utf-8")
    spec = _write_spec(
        tmp_path,
        _GOOD_SPEC.replace(
            "    id: samples\n",
            "    id: samples\n    module_id: alignment\n",
        ).replace(
            "    id: stats\n",
            "    id: stats\n    module_id: quality-control\n",
        ),
    )

    assert (
        _verify(
            manifest,
            "--spec",
            spec,
            *_PRODUCER_FLAGS,
            "--run-id",
            "run7",
            "--on-failure",
            "write",
        )
        == 0
    )
    capsys.readouterr()
    loaded = load_manifest(manifest)
    assert loaded.producer.run_id == "run7"
    assert [a.module_id for a in loaded.artifacts] == [
        "alignment",
        "quality-control",
    ]
    assert loaded.artifacts[1].status is ArtifactStatus.FAILED
    assert loaded.artifacts[1].sha256 is None

    before = manifest.read_bytes()
    assert (
        _verify(
            manifest,
            "--spec",
            spec,
            "--run-id",
            "run8",
            "--on-failure",
            "write",
        )
        == 1
    )
    assert "one run" in capsys.readouterr().err
    assert manifest.read_bytes() == before


@pytest.mark.parametrize(
    ("specified", "declared", "expected_code"),
    [
        (None, "alignment", 0),
        ("alignment", None, 0),
        ("alignment", "alignment", 0),
        ("alignment", "other", 1),
    ],
)
def test_spec_and_cli_module_claims_must_agree(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    specified: str | None,
    declared: str | None,
    expected_code: int,
) -> None:
    manifest = tmp_path / "manifest.json"
    _stats_json(tmp_path)
    _samples_tsv(tmp_path)
    text = _GOOD_SPEC
    if specified is not None:
        text = text.replace(
            "    id: samples\n",
            f"    id: samples\n    module_id: {specified}\n",
        )
    spec = _write_spec(tmp_path, text)
    flags = [] if declared is None else ["--module-id", declared]

    assert _verify(manifest, "--spec", spec, *flags) == expected_code
    captured = capsys.readouterr()
    if expected_code == 1:
        assert "must agree" in captured.err
        assert not manifest.exists()
    else:
        assert load_manifest(manifest).artifacts[0].module_id == (
            declared if declared is not None else specified
        )


def test_rerun_preserves_module_and_refuses_reassignment(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = tmp_path / "manifest.json"
    stats = _stats_json(tmp_path)
    identity = _identity("stats", "org.example.stats", "json")
    assert (
        _verify(
            manifest,
            stats,
            *identity,
            *_PRODUCER_FLAGS,
            "--module-id",
            "quality-control",
        )
        == 0
    )
    capsys.readouterr()

    stats.write_text("{invalid", encoding="utf-8")
    assert _verify(manifest, stats, *identity, "--on-failure", "write") == 0
    capsys.readouterr()
    artifact = load_manifest(manifest).artifacts[0]
    assert artifact.module_id == "quality-control"
    assert artifact.status is ArtifactStatus.FAILED
    assert artifact.sha256 is None

    _stats_json(tmp_path)
    assert _verify(manifest, stats, *identity) == 0
    capsys.readouterr()
    artifact = load_manifest(manifest).artifacts[0]
    assert artifact.module_id == "quality-control"
    assert artifact.status is ArtifactStatus.COMPLETE
    assert artifact.sha256 is not None

    before = manifest.read_bytes()
    assert _verify(manifest, stats, *identity, "--module-id", "other-module") == 1
    assert "preserve module attribution" in capsys.readouterr().err
    assert manifest.read_bytes() == before


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--producer-name", "other"),
        ("--producer-version", "9"),
    ],
)
def test_spec_checks_cli_producer_claims(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    flag: str,
    value: str,
) -> None:
    manifest = tmp_path / "manifest.json"
    spec = _write_spec(tmp_path, _GOOD_SPEC)
    assert _verify(manifest, "--spec", spec, flag, value) == 1
    assert "must agree" in capsys.readouterr().err
    assert not manifest.exists()


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--id", "stats"),
        ("--type", "org.example.stats"),
        ("--format", "json"),
        ("--schema-version", "1"),
        ("--criteria", "keys=depth"),
    ],
)
def test_spec_rejects_artifact_only_flags(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    flag: str,
    value: str,
) -> None:
    manifest = tmp_path / "manifest.json"
    spec = _write_spec(tmp_path, _GOOD_SPEC)
    assert _verify(manifest, "--spec", spec, flag, value) == 1
    assert flag in capsys.readouterr().err
    assert not manifest.exists()


def test_empty_cli_module_id_fails_cleanly(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = tmp_path / "manifest.json"
    stats = _stats_json(tmp_path)
    assert (
        _verify(
            manifest,
            stats,
            *_identity("stats", "org.example.stats", "json"),
            *_PRODUCER_FLAGS,
            "--module-id",
            "",
        )
        == 1
    )
    assert "non-empty string" in capsys.readouterr().err
    assert not manifest.exists()


def test_verify_write_error_names_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / "manifest.json"
    stats = _stats_json(tmp_path)

    def failing_write(*args: object, **kwargs: object) -> None:
        raise OSError("simulated manifest write failure")

    monkeypatch.setattr(
        "workflow_coda.verification.drivers.write_manifest_atomically",
        failing_write,
    )
    assert (
        _verify(
            manifest,
            stats,
            *_identity("stats", "org.example.stats", "json"),
            *_PRODUCER_FLAGS,
        )
        == 1
    )
    assert "could not write the manifest to" in capsys.readouterr().err
    assert not manifest.exists()


@pytest.mark.parametrize("on_failure", ["fail", "write"])
@pytest.mark.parametrize("existing", [False, True])
def test_duplicate_spec_refuses_before_verification_and_preserves_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    on_failure: str,
    existing: bool,
) -> None:
    manifest = tmp_path / "manifest.json"
    before: bytes | None = None
    if existing:
        stats = _stats_json(tmp_path)
        assert (
            _verify(
                manifest,
                stats,
                *_identity("stats", "org.example.stats", "json"),
                *_PRODUCER_FLAGS,
            )
            == 0
        )
        capsys.readouterr()
        before = manifest.read_bytes()

    def unexpected_verification(*args: object, **kwargs: object) -> None:
        pytest.fail("duplicate spec reached artifact verification")

    monkeypatch.setattr(
        "workflow_coda.verification.drivers.verify_artifact_file",
        unexpected_verification,
    )
    spec = _write_spec(
        tmp_path,
        """\
producer:
  name: fungifunk-pipeline
  version: "1.3"
artifacts:
  - file: missing-first.json
    id: duplicate
    type: org.example.duplicate
    module_id: first-module
    format: json
    schema_version: "1"
  - file: missing-second.json
    id: duplicate
    type: org.example.duplicate
    module_id: second-module
    format: json
    schema_version: "1"
""",
    )

    assert _verify(manifest, "--spec", spec, "--on-failure", on_failure) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "duplicate artifact id 'duplicate'" in captured.err
    assert "duplicate artifact type 'org.example.duplicate'" in captured.err
    assert "expanded blocks 1, 2" in captured.err
    if existing:
        assert manifest.read_bytes() == before
    else:
        assert not manifest.exists()


@pytest.mark.parametrize("on_failure", ["fail", "write"])
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--id", "Bad ID"),
        ("--type", "not-namespaced"),
        ("--format", "not-namespaced"),
        ("--schema-version", ""),
    ],
)
def test_invalid_flags_declaration_refuses_before_verification(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    on_failure: str,
    existing: bool,
    flag: str,
    value: str,
) -> None:
    manifest = tmp_path / "manifest.json"
    stats = _stats_json(tmp_path)
    before: bytes | None = None
    if existing:
        assert (
            _verify(
                manifest,
                stats,
                *_identity("stats", "org.example.stats", "json"),
                *_PRODUCER_FLAGS,
            )
            == 0
        )
        capsys.readouterr()
        before = manifest.read_bytes()

    def unexpected_verification(*args: object, **kwargs: object) -> None:
        pytest.fail("invalid declaration reached artifact verification")

    monkeypatch.setattr(
        "workflow_coda.verification.drivers.verify_artifact_file",
        unexpected_verification,
    )
    identity = _identity("stats", "org.example.stats", "json")
    identity[identity.index(flag) + 1] = value

    assert (
        _verify(
            manifest,
            stats,
            *identity,
            *_PRODUCER_FLAGS,
            "--on-failure",
            on_failure,
        )
        == 1
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "invalid flags-mode artifact declaration" in captured.err
    assert flag in captured.err
    if existing:
        assert manifest.read_bytes() == before
    else:
        assert not manifest.exists()


@pytest.mark.parametrize("on_failure", ["fail", "write"])
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("mode", ["flags", "spec"])
def test_geometry_preflight_refuses_before_any_verification(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    on_failure: str,
    existing: bool,
    mode: str,
) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    manifest = outputs / "manifest.json"
    inside = _stats_json(outputs)
    outside = _stats_json(tmp_path)
    before: bytes | None = None
    if existing:
        assert (
            _verify(
                manifest,
                inside,
                *_identity("stats", "org.example.stats", "json"),
                *_PRODUCER_FLAGS,
            )
            == 0
        )
        capsys.readouterr()
        before = manifest.read_bytes()

    def unexpected_verification(*args: object, **kwargs: object) -> None:
        pytest.fail("geometry refusal reached artifact verification")

    monkeypatch.setattr(
        "workflow_coda.verification.drivers.verify_artifact_file",
        unexpected_verification,
    )
    if mode == "flags":
        args: list[str | Path] = [
            outside,
            *_identity("outside", "org.example.outside", "json"),
            *_PRODUCER_FLAGS,
        ]
    else:
        # The first block is recordable; only the later block escapes.
        spec = _write_spec(
            outputs,
            """\
producer:
  name: fungifunk-pipeline
  version: "1.3"
artifacts:
  - file: stats.json
    id: stats
    type: org.example.stats
    format: json
    schema_version: "1"
  - file: ../stats.json
    id: outside
    type: org.example.outside
    format: json
    schema_version: "1"
""",
        )
        args = ["--spec", spec]

    assert _verify(manifest, *args, "--on-failure", on_failure) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "lives outside" in captured.err
    if existing:
        assert manifest.read_bytes() == before
    else:
        assert not manifest.exists()


# ---------------------------------------------------------------------------
# Expansion and discovery: CLI refusal boundaries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("on_failure", ["fail", "write"])
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize(
    ("case", "teaching"),
    [
        ("criteria-collision", "both expand to 's1'"),
        ("plain-key-placeholder", "declares no for_each"),
        ("blank-glob-capture", "blank capture"),
        ("directory-only-glob", "matches no files beside the spec"),
    ],
)
def test_spec_expansion_and_discovery_refuse_before_verification(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    on_failure: str,
    existing: bool,
    case: str,
    teaching: str,
) -> None:
    manifest = tmp_path / "manifest.json"
    stats = _stats_json(tmp_path)
    before: bytes | None = None
    if existing:
        assert (
            _verify(
                manifest,
                stats,
                *_identity("stats", "org.example.stats", "json"),
                *_PRODUCER_FLAGS,
            )
            == 0
        )
        capsys.readouterr()
        before = manifest.read_bytes()

    if case == "criteria-collision":
        invalid_block = """\
  - for_each:
      dimension: sample
      values: [s1]
    file: stats.json
    id: family-{sample}
    type: org.example.family-{sample}
    format: json
    schema_version: "1"
    criteria:
      nested:
        - "{sample}": 1
          s1: 1
"""
    elif case == "plain-key-placeholder":
        invalid_block = """\
  - file: stats.json
    id: plain
    type: org.example.plain
    format: json
    schema_version: "1"
    criteria:
      nested:
        - "{sample}": literal
"""
    else:
        discovered = tmp_path / "discovered"
        discovered.mkdir()
        if case == "blank-glob-capture":
            (discovered / "prefix-.json").write_text("{}", encoding="utf-8")
            (discovered / "prefix-valid.json").write_text("{}", encoding="utf-8")
        else:
            (discovered / "prefix-directory.json").mkdir()
        invalid_block = """\
  - for_each:
      dimension: sample
      glob: "discovered/prefix-{sample}.json"
    id: family-{sample}
    type: org.example.family-{sample}
    format: json
    schema_version: "1"
"""

    spec = _write_spec(
        tmp_path,
        """\
producer:
  name: fungifunk-pipeline
  version: "1.3"
artifacts:
  - file: stats.json
    id: stats
    type: org.example.stats
    format: json
    schema_version: "1"
"""
        + invalid_block,
    )

    def unexpected_verification(*args: object, **kwargs: object) -> None:
        pytest.fail("invalid spec reached artifact verification")

    monkeypatch.setattr(
        "workflow_coda.verification.drivers.verify_artifact_file",
        unexpected_verification,
    )

    assert _verify(manifest, "--spec", spec, "--on-failure", on_failure) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(spec) in captured.err
    assert teaching in captured.err
    if existing:
        assert manifest.read_bytes() == before
    else:
        assert not manifest.exists()


@pytest.mark.parametrize("reverse", [False, True])
def test_spec_glob_natural_ties_preserve_order_in_written_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    reverse: bool,
) -> None:
    manifest = tmp_path / "manifest.json"
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    matches = [
        "outputs/s1.json",
        "outputs/s10.json",
        "outputs/s01.json",
        "outputs/s2.json",
    ]
    for relative in matches:
        (tmp_path / relative).write_text('{"depth": 12}', encoding="utf-8")
    if reverse:
        matches.reverse()

    def discover(*args: object, **kwargs: object) -> list[str]:
        return matches

    monkeypatch.setattr(
        "workflow_coda.verification.sources.glob.glob",
        discover,
    )
    spec = _write_spec(
        tmp_path,
        """\
producer:
  name: fungifunk-pipeline
  version: "1.3"
artifacts:
  - for_each:
      dimension: sample
      glob: "outputs/{sample}.json"
    id: stats-{sample}
    type: org.example.stats-{sample}
    format: json
    schema_version: "1"
    criteria:
      keys: [depth]
""",
    )

    assert _verify(manifest, "--spec", spec) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == (
        f"created {manifest} (producer fungifunk-pipeline 1.3) "
        "— verified 4 artifacts — appended 4, updated 0\n"
    )

    loaded = load_manifest(manifest)
    expected = ["s01", "s1", "s2", "s10"]
    assert [artifact.id for artifact in loaded.artifacts] == [
        f"stats-{raw}" for raw in expected
    ]
    assert [artifact.type for artifact in loaded.artifacts] == [
        f"org.example.stats-{raw}" for raw in expected
    ]
    assert [artifact.path for artifact in loaded.artifacts] == [
        f"outputs/{raw}.json" for raw in expected
    ]
    for artifact in loaded.artifacts:
        assert artifact.status is ArtifactStatus.COMPLETE
        assert (
            artifact.sha256
            == hashlib.sha256((tmp_path / artifact.path).read_bytes()).hexdigest()
        )
        assert artifact.verification == {
            "format": "json",
            "status": "ok",
            "keys_checked": ["depth"],
        }
