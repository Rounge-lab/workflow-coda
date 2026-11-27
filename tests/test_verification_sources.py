from pathlib import Path

import pytest

from workflow_coda.errors import SpecError
from workflow_coda.verification.sources import (
    values_from_glob,
    values_from_list,
    values_from_samplesheet,
)


def test_values_from_list_preserves_declared_order() -> None:
    values = values_from_list(
        ["batch-2", "batch-10", "batch-1"],
        dimension="batch",
        path=Path("spec.yaml"),
    )
    assert values == ("batch-2", "batch-10", "batch-1")


def test_values_from_list_requires_a_list() -> None:
    with pytest.raises(SpecError, match="must be a list of strings"):
        values_from_list("batch-1", dimension="batch", path=Path("spec.yaml"))


def test_values_from_list_requires_strings_and_teaches_yaml_traps() -> None:
    with pytest.raises(SpecError, match="must be strings"):
        values_from_list([1], dimension="batch", path=Path("spec.yaml"))


def test_values_from_list_rejects_blank_items() -> None:
    with pytest.raises(SpecError, match="item 2 is blank"):
        values_from_list(
            ["batch-1", "   "],
            dimension="batch",
            path=Path("spec.yaml"),
        )


def test_values_from_list_rejects_empty_lists() -> None:
    with pytest.raises(SpecError, match="discovered no values"):
        values_from_list([], dimension="batch", path=Path("spec.yaml"))


def test_values_from_samplesheet_reads_first_appearance_order(
    tmp_path: Path,
) -> None:
    sheet = tmp_path / "samples.tsv"
    sheet.write_text(
        "sample_id\tdepth\nS2\t9\nS10\t10\nS1\t11\n",
        encoding="utf-8",
    )

    values = values_from_samplesheet(
        {"file": "samples.tsv", "column": "sample_id"},
        dimension="sample_id",
        spec_dir=tmp_path,
        path=tmp_path / "spec.yaml",
    )

    assert values == ("S2", "S10", "S1")


def test_values_from_samplesheet_rejects_unknown_keys(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="unknown key 'columns'"):
        values_from_samplesheet(
            {"file": "samples.tsv", "column": "sample_id", "columns": "extra"},
            dimension="sample_id",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )


def test_values_from_samplesheet_requires_mapping(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="must be a mapping"):
        values_from_samplesheet(
            ["samples.tsv"],
            dimension="sample_id",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )


def test_values_from_samplesheet_requires_file_and_column(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="requires a 'file'"):
        values_from_samplesheet(
            {"column": "sample_id"},
            dimension="sample_id",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )
    with pytest.raises(SpecError, match="requires a 'column'"):
        values_from_samplesheet(
            {"file": "samples.tsv"},
            dimension="sample_id",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )


def test_values_from_samplesheet_requires_single_character_sep(
    tmp_path: Path,
) -> None:
    with pytest.raises(SpecError, match="'sep' must be a single character"):
        values_from_samplesheet(
            {"file": "samples.tsv", "column": "sample_id", "sep": ",,"},
            dimension="sample_id",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )


def test_values_from_samplesheet_teaches_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="could not read the samplesheet 'samples.tsv'"):
        values_from_samplesheet(
            {"file": "samples.tsv", "column": "sample_id"},
            dimension="sample_id",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )


def test_values_from_samplesheet_teaches_invalid_utf8(tmp_path: Path) -> None:
    sheet = tmp_path / "samples.tsv"
    sheet.write_bytes(b"\xff\xfe")

    with pytest.raises(SpecError, match="is not valid UTF-8"):
        values_from_samplesheet(
            {"file": "samples.tsv", "column": "sample_id"},
            dimension="sample_id",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )


def test_values_from_samplesheet_teaches_missing_named_column(tmp_path: Path) -> None:
    sheet = tmp_path / "samples.tsv"
    sheet.write_text("other\tdepth\nS1\t9\n", encoding="utf-8")

    with pytest.raises(SpecError, match="names column 'sample_id'"):
        values_from_samplesheet(
            {"file": "samples.tsv", "column": "sample_id"},
            dimension="sample_id",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )


def test_values_from_samplesheet_rejects_no_rows(tmp_path: Path) -> None:
    sheet = tmp_path / "samples.tsv"
    sheet.write_text("sample_id\tdepth\n", encoding="utf-8")

    with pytest.raises(SpecError, match="carries no rows"):
        values_from_samplesheet(
            {"file": "samples.tsv", "column": "sample_id"},
            dimension="sample_id",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )


def test_values_from_samplesheet_collects_blank_cells_and_duplicates(
    tmp_path: Path,
) -> None:
    sheet = tmp_path / "samples.tsv"
    sheet.write_text(
        "sample_id\tdepth\nS1\t9\n\t10\nS1\t11\n",
        encoding="utf-8",
    )

    with pytest.raises(SpecError) as excinfo:
        values_from_samplesheet(
            {"file": "samples.tsv", "column": "sample_id"},
            dimension="sample_id",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )

    message = str(excinfo.value)
    assert "a blank cell" in message
    assert "already appeared on line 2" in message


def test_values_from_samplesheet_accepts_index_column_convention(
    tmp_path: Path,
) -> None:
    sheet = tmp_path / "samples.tsv"
    sheet.write_text(
        "\tsample_id\tdepth\nrow1\tS1\t9\nrow2\tS2\t10\n",
        encoding="utf-8",
    )

    values = values_from_samplesheet(
        {"file": "samples.tsv", "column": "sample_id"},
        dimension="sample_id",
        spec_dir=tmp_path,
        path=tmp_path / "spec.yaml",
    )

    assert values == ("S1", "S2")


def test_values_from_glob_discovers_natural_sorted_values(tmp_path: Path) -> None:
    tables = tmp_path / "tables"
    tables.mkdir()
    for name in ("sample-10.tsv", "sample-2.tsv", "sample-1.tsv"):
        (tables / name).write_text("ok\n", encoding="utf-8")

    values = values_from_glob(
        "tables/{sample}.tsv",
        dimension="sample",
        spec_dir=tmp_path,
        path=tmp_path / "spec.yaml",
    )

    assert values == ("sample-1", "sample-2", "sample-10")


def test_values_from_glob_requires_non_empty_string(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="must be a non-empty pattern string"):
        values_from_glob(
            "",
            dimension="sample",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )


def test_values_from_glob_requires_exactly_one_placeholder(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="must carry exactly one placeholder"):
        values_from_glob(
            "tables/sample.tsv",
            dimension="sample",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )
    with pytest.raises(SpecError, match="must carry exactly one placeholder"):
        values_from_glob(
            "tables/{sample}-{sample}.tsv",
            dimension="sample",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )


def test_values_from_glob_requires_its_own_dimension_name(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="but the block's dimension is 'sample'"):
        values_from_glob(
            "tables/{batch}.tsv",
            dimension="sample",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )


def test_values_from_glob_rejects_malformed_placeholders(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="malformed placeholder"):
        values_from_glob(
            "tables/{sample.tsv",
            dimension="sample",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )


def test_values_from_glob_rejects_absolute_patterns(tmp_path: Path) -> None:
    pattern = str((tmp_path / "tables" / "{sample}.tsv").resolve())
    with pytest.raises(SpecError, match="must be relative"):
        values_from_glob(
            pattern,
            dimension="sample",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )


def test_values_from_glob_rejects_other_wildcards(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="may vary only at its capture"):
        values_from_glob(
            "tables/pre*/{sample}.tsv",
            dimension="sample",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )
    with pytest.raises(SpecError, match="may vary only at its capture"):
        values_from_glob(
            "tables/{sample}-?.tsv",
            dimension="sample",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )


def test_values_from_glob_rejects_no_matches(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="matches no files beside the spec"):
        values_from_glob(
            "tables/{sample}.tsv",
            dimension="sample",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )


def test_values_from_glob_ignores_hidden_files_by_glob_law(tmp_path: Path) -> None:
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / ".sample-1.tsv").write_text("ok\n", encoding="utf-8")
    (tables / "sample-2.tsv").write_text("ok\n", encoding="utf-8")

    values = values_from_glob(
        "tables/{sample}.tsv",
        dimension="sample",
        spec_dir=tmp_path,
        path=tmp_path / "spec.yaml",
    )

    assert values == ("sample-2",)


def test_values_from_glob_ignores_matching_directories(tmp_path: Path) -> None:
    (tmp_path / "directory.tsv").mkdir()
    (tmp_path / "sample.tsv").write_text("ok\n", encoding="utf-8")

    assert values_from_glob(
        "{sample}.tsv",
        dimension="sample",
        spec_dir=tmp_path,
        path=tmp_path / "spec.yaml",
    ) == ("sample",)


def test_values_from_glob_directory_only_is_no_files(tmp_path: Path) -> None:
    (tmp_path / "directory.tsv").mkdir()

    with pytest.raises(SpecError, match="matches no files beside the spec"):
        values_from_glob(
            "{sample}.tsv",
            dimension="sample",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )


@pytest.mark.parametrize("capture", ["", "   "])
def test_values_from_glob_rejects_blank_file_captures(
    tmp_path: Path,
    capture: str,
) -> None:
    filename = f"prefix-{capture}.tsv"
    (tmp_path / filename).write_text("ok\n", encoding="utf-8")
    (tmp_path / "prefix-valid.tsv").write_text("ok\n", encoding="utf-8")

    with pytest.raises(SpecError) as excinfo:
        values_from_glob(
            "prefix-{sample}.tsv",
            dimension="sample",
            spec_dir=tmp_path,
            path=tmp_path / "spec.yaml",
        )
    message = str(excinfo.value)
    assert filename in message
    assert "blank capture" in message


@pytest.mark.parametrize("reverse", [False, True])
def test_values_from_glob_natural_ties_do_not_follow_discovery_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reverse: bool,
) -> None:
    matches = ["s1.tsv", "s01.tsv", "s2.tsv", "s10.tsv"]
    for filename in matches:
        (tmp_path / filename).write_text("ok\n", encoding="utf-8")
    if reverse:
        matches.reverse()

    def discover(*args: object, **kwargs: object) -> list[str]:
        return matches

    monkeypatch.setattr(
        "workflow_coda.verification.sources.glob.glob",
        discover,
    )
    assert values_from_glob(
        "{sample}.tsv",
        dimension="sample",
        spec_dir=tmp_path,
        path=tmp_path / "spec.yaml",
    ) == ("s01", "s1", "s2", "s10")
