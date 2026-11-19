from pathlib import Path

import pytest

from workflow_coda.errors import SpecError
from workflow_coda.verification.spec import load_verify_spec


def write_spec(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "spec.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_verify_spec_expands_values_source_in_declared_order(
    tmp_path: Path,
) -> None:
    spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - for_each:
      dimension: sample
      values: [s2, s10, s1]
    file: output/org.example.{sample}.json
    id: "example-{sample}"
    type: "org.example.samples-{sample}"
    format: json
    schema_version: "1.0"
""",
    )

    loaded = load_verify_spec(spec)

    assert [artifact.file for artifact in loaded.artifacts] == [
        "output/org.example.s2.json",
        "output/org.example.s10.json",
        "output/org.example.s1.json",
    ]


def test_load_verify_spec_substitutes_criteria_recursively(tmp_path: Path) -> None:
    spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - file: output/{sample}.json
    id: stats
    type: "{sample}"
    format: json
    schema_version: "1.0.0"
    criteria:
      expected:
        sample: "{sample}"
      labels:
        - "{sample}"
    for_each:
      dimension: sample
      values:
        - org.example.s1
""",
    )

    loaded = load_verify_spec(spec)

    assert loaded.artifacts[0].criteria == {
        "expected": {"sample": "org.example.s1"},
        "labels": ["org.example.s1"],
    }


def test_load_verify_spec_glob_source_provides_the_file_path(tmp_path: Path) -> None:
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "org.example.s1.tsv").write_text("ok\n", encoding="utf-8")
    (tables / "org.example.s2.tsv").write_text("ok\n", encoding="utf-8")

    spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - id: "sample-{sample_id}"
    type: "org.example.sample-{sample_id}"
    format: core.tabular
    schema_version: "1.0"
    for_each:
      dimension: sample_id
      glob: "tables/org.example.{sample_id}.tsv"
""",
    )

    loaded = load_verify_spec(spec)

    assert [artifact.file for artifact in loaded.artifacts] == [
        "tables/org.example.s1.tsv",
        "tables/org.example.s2.tsv",
    ]


def test_load_verify_spec_rejects_plain_block_placeholders(tmp_path: Path) -> None:
    spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - file: output/{sample}.json
    id: stats
    type: org.example.stats
    format: json
    schema_version: "1.0.0"
""",
    )

    with pytest.raises(SpecError, match="placeholder"):
        load_verify_spec(spec)


def test_load_verify_spec_requires_for_each_mapping(tmp_path: Path) -> None:
    spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - file: output/{sample}.json
    id: stats
    type: "{sample}"
    format: json
    schema_version: "1.0.0"
    for_each: sample
""",
    )

    with pytest.raises(SpecError, match="must be a mapping of 'dimension'"):
        load_verify_spec(spec)


def test_load_verify_spec_rejects_unknown_for_each_keys(tmp_path: Path) -> None:
    spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - file: output/{sample}.json
    id: stats
    type: "{sample}"
    format: json
    schema_version: "1.0.0"
    for_each:
      dimension: sample
      values:
        - org.example.s1
      surprise: true
""",
    )

    with pytest.raises(SpecError, match="unknown key 'surprise'"):
        load_verify_spec(spec)


def test_load_verify_spec_requires_dimension(tmp_path: Path) -> None:
    spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - file: output/{sample}.json
    id: stats
    type: "{sample}"
    format: json
    schema_version: "1.0.0"
    for_each:
      values:
        - org.example.s1
""",
    )

    with pytest.raises(SpecError, match="requires a 'dimension'"):
        load_verify_spec(spec)


def test_load_verify_spec_requires_exactly_one_source_key(tmp_path: Path) -> None:
    none_spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - file: output/{sample}.json
    id: stats
    type: "{sample}"
    format: json
    schema_version: "1.0.0"
    for_each:
      dimension: sample
""",
    )
    with pytest.raises(SpecError, match="carries no source"):
        load_verify_spec(none_spec)

    many_spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - file: output/{sample}.json
    id: stats
    type: "{sample}"
    format: json
    schema_version: "1.0.0"
    for_each:
      dimension: sample
      values:
        - org.example.s1
      glob: "tables/{sample}.tsv"
""",
    )
    with pytest.raises(SpecError, match="carries multiple sources"):
        load_verify_spec(many_spec)


def test_load_verify_spec_glob_forbids_file_key(tmp_path: Path) -> None:
    spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - file: output/{sample}.json
    id: stats
    type: "{sample}"
    format: json
    schema_version: "1.0.0"
    for_each:
      dimension: sample
      glob: "tables/{sample}.tsv"
""",
    )

    with pytest.raises(SpecError, match="carries both 'file:' and 'glob:'"):
        load_verify_spec(spec)


def test_load_verify_spec_non_glob_requires_file_template(tmp_path: Path) -> None:
    spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - id: stats
    type: "{sample}"
    format: json
    schema_version: "1.0.0"
    for_each:
      dimension: sample
      values:
        - org.example.s1
""",
    )

    with pytest.raises(SpecError, match="requires a 'file' template"):
        load_verify_spec(spec)


def test_load_verify_spec_requires_boolean_sanitize(tmp_path: Path) -> None:
    spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - file: output/{sample}.json
    id: stats
    type: "{sample}"
    format: json
    schema_version: "1.0.0"
    sanitize: "yes"
    for_each:
      dimension: sample
      values:
        - org.example.s1
""",
    )

    with pytest.raises(SpecError, match="'sanitize' must be a boolean"):
        load_verify_spec(spec)


def test_load_verify_spec_requires_criteria_mapping(tmp_path: Path) -> None:
    spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - file: output/{sample}.json
    id: stats
    type: "{sample}"
    format: json
    schema_version: "1.0.0"
    criteria: [bad]
    for_each:
      dimension: sample
      values:
        - org.example.s1
""",
    )

    with pytest.raises(SpecError, match="'criteria' must be a mapping"):
        load_verify_spec(spec)


def test_load_verify_spec_family_collisions_teach_both_raws(tmp_path: Path) -> None:
    spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - file: output/{sample}.json
    id: sample
    type: org.example.sample
    format: json
    schema_version: "1.0.0"
    sanitize: true
    for_each:
      dimension: sample
      values: [S1, S2]
""",
    )

    with pytest.raises(SpecError) as excinfo:
        load_verify_spec(spec)

    message = str(excinfo.value)
    assert "S1" in message
    assert "S2" in message
    assert "id" in message


def test_load_verify_spec_values_source_respects_sanitize_for_identity(
    tmp_path: Path,
) -> None:
    spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - file: output/{sample}.json
    id: sample-{sample}
    type: org.example.sample-{sample}
    format: json
    schema_version: "1.0.0"
    sanitize: true
    criteria:
      raw_value: "{sample}"
    for_each:
      dimension: sample
      values: ["Sample A"]
""",
    )

    loaded = load_verify_spec(spec)

    artifact = loaded.artifacts[0]
    assert artifact.file == "output/Sample A.json"
    assert artifact.id == "sample-sample-a"
    assert artifact.type == "org.example.sample-sample-a"
    assert artifact.criteria == {"raw_value": "Sample A"}


def test_load_verify_spec_unsanitized_bad_identity_teaches_fix(tmp_path: Path) -> None:
    spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - file: output/{sample}.json
    id: sample-{sample}
    type: org.example.sample-{sample}
    format: json
    schema_version: "1.0.0"
    for_each:
      dimension: sample
      values: ["Sample A"]
""",
    )

    with pytest.raises(SpecError, match="sanitize"):
        load_verify_spec(spec)


def test_load_verify_spec_samplesheet_source_expands_values(
    tmp_path: Path,
) -> None:
    sheet = tmp_path / "samples.tsv"
    sheet.write_text(
        "sample_id\tdepth\norg.example.s2\t9\norg.example.s1\t10\n",
        encoding="utf-8",
    )

    spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - file: output/{sample_id}.json
    id: stats-{sample_id}
    type: "{sample_id}"
    format: json
    schema_version: "1.0.0"
    for_each:
      dimension: sample_id
      samplesheet:
        file: samples.tsv
        column: sample_id
""",
    )

    loaded = load_verify_spec(spec)

    assert [artifact.file for artifact in loaded.artifacts] == [
        "output/org.example.s2.json",
        "output/org.example.s1.json",
    ]


def test_load_verify_spec_wraps_model_validation_with_file_context(
    tmp_path: Path,
) -> None:
    spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - file: output/stats.json
    id: stats
    type: not-a-namespaced-type
    format: json
    schema_version: "1.0.0"
""",
    )

    with pytest.raises(SpecError) as excinfo:
        load_verify_spec(spec)

    message = str(excinfo.value)
    assert str(spec) in message
    assert "not a valid verification spec" in message


def test_load_verify_spec_rejects_non_mapping_top_level(tmp_path: Path) -> None:
    spec = write_spec(tmp_path, "- file: stats.json\n")

    with pytest.raises(SpecError, match="must be a mapping"):
        load_verify_spec(spec)


def test_load_verify_spec_rejects_empty_file(tmp_path: Path) -> None:
    spec = write_spec(tmp_path, "")

    with pytest.raises(SpecError, match="the spec file must be a mapping"):
        load_verify_spec(spec)


def test_load_verify_spec_requires_producer_block(tmp_path: Path) -> None:
    spec = write_spec(
        tmp_path,
        """\
artifacts:
  - file: output/stats.json
    id: stats
    type: org.example.stats
    format: json
    schema_version: "1.0.0"
""",
    )

    with pytest.raises(SpecError, match="requires a producer block"):
        load_verify_spec(spec)


def test_load_verify_spec_requires_artifacts(tmp_path: Path) -> None:
    spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts: []
""",
    )

    with pytest.raises(SpecError, match="must declare at least one artifact"):
        load_verify_spec(spec)


def test_load_verify_spec_rejects_duplicate_keys(tmp_path: Path) -> None:
    spec = write_spec(
        tmp_path,
        """\
producer:
  name: pipeline
  version: "1.0"
artifacts:
  - file: stats.json
    file: other.json
    id: stats
    type: org.example.stats
    format: json
    schema_version: "1.0.0"
""",
    )

    with pytest.raises(SpecError, match="duplicate key 'file'"):
        load_verify_spec(spec)


def test_load_verify_spec_rejects_invalid_yaml(tmp_path: Path) -> None:
    spec = write_spec(tmp_path, "producer: {name: p\n  version: '1'\n")

    with pytest.raises(SpecError, match="not valid YAML"):
        load_verify_spec(spec)


def test_load_verify_spec_rejects_invalid_utf8(tmp_path: Path) -> None:
    spec = tmp_path / "spec.yaml"
    spec.write_bytes(b"\xff\xfe")

    with pytest.raises(SpecError, match="is not valid UTF-8"):
        load_verify_spec(spec)


def test_load_verify_spec_rejects_unreadable_file(tmp_path: Path) -> None:
    spec = tmp_path / "missing.yaml"

    with pytest.raises(SpecError, match="could not read the spec file"):
        load_verify_spec(spec)
