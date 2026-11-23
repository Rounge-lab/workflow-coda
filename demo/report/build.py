"""Build the visual inspection report with the installed CLI."""

from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"


def write_text(path: str, content: str) -> None:
    destination = BUILD / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8", newline="\n")


def run(*args: str) -> None:
    command = ["workflow-coda", *args]
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=BUILD, check=True)


def main() -> None:
    if shutil.which("workflow-coda") is None:
        raise SystemExit("workflow-coda was not found; run this through pixi.")

    shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir()

    for filename in ("spec.yaml", "layout.yaml", "favicon.svg"):
        source = HERE / filename
        if not source.is_file():
            raise SystemExit(f"Required demo file is missing: {source}")
        shutil.copy2(source, BUILD / filename)

    write_text(
        "stats.json",
        json.dumps(
            {
                "depth": 42.345,
                "rate": 92.5,
                "low": 4,
                "verdict": "Review *literal stars* and <literal tags>.",
                "nested": {"count": 4},
            },
            indent=2,
        )
        + "\n",
    )

    write_text(
        "samples.tsv",
        "sample_id\tdepth\tbatch\tstatus\n"
        "S1\t9\tb1\tpassed\n"
        "S2\t100\tb2\tfailed\n"
        "S3\t10\tb1\tpassed\n"
        "S4\t40\tb3\tpending\n",
    )
    # Dedicated table-enhancement fixture: enough rows to scroll, numeric
    # values whose lexical and numeric orders differ, and varying text
    # lengths to exercise measured row heights at narrow widths.
    inspection_rows = (
        ("T01", "9", "keep", "Short note."),
        (
            "T02",
            "100",
            "keep",
            "A longer note that should wrap across multiple lines "
            "when the browser is narrow.",
        ),
        ("T03", "10", "keep", "Review *literal stars* and <literal tags>."),
        ("T04", "40", "drop", "Excluded by the group filter."),
        (
            "T05",
            "2",
            "keep",
            "Unbroken_identifier_abcdefghijklmnopqrstuvwxyz_0123456789"
            "_abcdefghijklmnopqrstuvwxyz",
        ),
        ("T06", "80", "keep", "A note with a tab\tinside the cell."),
        ("T07", "3", "drop", "Another excluded group row."),
        ("T08", "25", "keep", 'A note with "quoted text".'),
        ("T09", "60", "keep", "First line.\nSecond line inside the same cell."),
        (
            "T10",
            "7",
            "drop",
            "Another longer note for checking row heights after sorting "
            "changes which rows occupy the top of the viewport.",
        ),
        ("T11", "12", "keep", "Near the end of the table."),
        ("T12", "1", "keep", "Final row in original file order."),
    )
    inspection_buffer = io.StringIO(newline="")
    inspection_writer = csv.writer(
        inspection_buffer, delimiter="\t", lineterminator="\n"
    )
    inspection_writer.writerow(("sample_id", "depth", "group", "note"))
    inspection_writer.writerows(inspection_rows)
    write_text("table_inspection.tsv", inspection_buffer.getvalue())
    write_text(
        "counts.tsv",
        "\tA\tB\nS1\t9\t100\nS2\t10\t3\nS3\t2\t45\n",
    )
    write_text(
        "measurements.csv",
        "sample,value,group\nS1,1,alpha\nS2,10,beta\nS3,100,alpha\n",
    )
    write_text("headerless.csv", "red,1\nblue,2\ngreen,3\n")
    write_text("samplesheet.tsv", "sample_id\nSheet A\nSheet B\n")

    for name, value in (("List A", 11), ("List B", 22)):
        write_text(
            f"list/{name}.json",
            json.dumps({"value": value}) + "\n",
        )

    for name, value in (("Sheet A", 33), ("Sheet B", 44)):
        write_text(
            f"sheet/{name}.json",
            json.dumps({"value": value}) + "\n",
        )

    for name, value in (("sample2", 2), ("sample10", 10)):
        write_text(
            f"glob/{name}.json",
            json.dumps({"value": value}) + "\n",
        )

    write_text("note.txt", "A UTF-8 artifact verified in flags mode.\n")
    (BUILD / "payload.bin").write_bytes(bytes((0, 1, 127, 255)))

    # Create the manifest in flags mode. The spec has no run_id field,
    # so the run identity is established here.
    run(
        "verify",
        "manifest.json",
        "stats.json",
        "--id",
        "stats",
        "--type",
        "org.example.stats",
        "--format",
        "json",
        "--schema-version",
        "1.0",
        "--producer-name",
        "visual-demo",
        "--producer-version",
        "1.0",
        "--run-id",
        "visual-demo",
        "--criteria",
        "keys=depth,rate,verdict",
    )

    # Exercise the other two framework verifiers through flags mode.
    for filename, artifact_id, artifact_type, fmt in (
        ("note.txt", "note", "org.example.note", "txt"),
        ("payload.bin", "payload", "org.example.payload", "bytes"),
    ):
        run(
            "verify",
            "manifest.json",
            filename,
            "--id",
            artifact_id,
            "--type",
            artifact_type,
            "--format",
            fmt,
            "--schema-version",
            "1.0",
        )

    # The spec intentionally names one missing artifact. Its warning and
    # failed manifest declaration are part of the visual fixture.
    run(
        "verify",
        "manifest.json",
        "--spec",
        "spec.yaml",
        "--on-failure",
        "write",
    )

    run("build", "manifest.json", "layout.yaml", "-o", "report.html")
    print(f"\nOpen: {(BUILD / 'report.html').as_uri()}")
    print(f"Inspect verification records: {BUILD / 'manifest.json'}")


if __name__ == "__main__":
    main()
