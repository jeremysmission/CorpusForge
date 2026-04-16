"""Regression tests for export artifact inspection logic."""

import json
from pathlib import Path

from src.analysis.export_artifact_analyzer import analyze_export_artifacts


def test_analyze_export_artifacts_summarizes_export_and_failure_inputs(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    export_dir.mkdir()

    manifest = {
        "stats": {
            "files_found": 4,
            "files_after_dedup": 3,
            "files_skipped": 1,
            "files_parsed": 2,
            "files_failed": 1,
            "chunks_created": 3,
        }
    }
    (export_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (export_dir / "run_report.txt").write_text("report", encoding="utf-8")
    skip_manifest = {
        "counts_by_reason": {"Deferred by config for this run": 2},
        "files": [
            {"path": r"root\telemetry\alpha.SAO", "reason": "Deferred by config for this run"},
            {"path": r"root\telemetry\beta.RSF", "reason": "Deferred by config for this run"},
        ],
    }
    (export_dir / "skip_manifest.json").write_text(json.dumps(skip_manifest), encoding="utf-8")

    chunks = [
        {
            "source_path": r"root\Packing List\travel.xlsx",
            "text_length": 900,
            "parse_quality": 0.92,
        },
        {
            "source_path": r"root\Packing List\travel.xlsx",
            "text_length": 875,
            "parse_quality": 0.99,
        },
        {
            "source_path": r"root\Archive\Desktop_Log.txt",
            "text_length": 650,
            "parse_quality": 0.65,
        },
    ]
    with open(export_dir / "chunks.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for row in chunks:
            handle.write(json.dumps(row) + "\n")

    failure_artifact = tmp_path / "failures.txt"
    failure_artifact.write_text(
        "\n".join(
            [
                "### .xml (3 files)",
                "Likely cause: XML sensor outputs with empty extracted text.",
                "",
                "[xml] Empty parse: A.XML",
                "[xml] Empty parse: B.XML",
                "[pdf] Empty parse: C.pdf",
            ]
        ),
        encoding="utf-8",
    )

    sample_profile = tmp_path / "sample_profile.json"
    sample_profile.write_text("{}", encoding="utf-8")

    payload = analyze_export_artifacts(
        export_dir,
        failure_artifact=failure_artifact,
        sample_profile_json=sample_profile,
    )

    assert payload["sample_profile_json"] == str(sample_profile.resolve())
    assert payload["export_dir"] == str(export_dir.resolve())
    assert payload["manifest_stats"]["files_found"] == 4
    assert payload["chunk_ext_top"][0] == (".xlsx", 2)
    assert payload["distinct_source_docs_in_chunks"] == 2
    assert payload["family_doc_counts"]["travel_admin"] == 1
    assert payload["family_chunk_counts"]["travel_admin"] == 2
    assert payload["family_doc_counts"]["archive_derived"] == 1
    assert payload["archive_path_chunks"] == 1
    assert payload["parse_quality_buckets"]["0.85-0.94"] == 1
    assert payload["parse_quality_buckets"]["0.95-1.00"] == 1
    assert payload["parse_quality_buckets"]["<0.70"] == 1
    assert payload["skip_reason_counts"]["Deferred by config for this run"] == 2
    assert payload["skip_ext_top"][0] == (".sao", 1)
    assert payload["failure_summary"][0]["extension"] == ".xml"
    assert payload["failure_summary"][0]["count"] == 3
    assert payload["raw_failure_counts"][".xml"] == 2
    assert payload["raw_failure_counts"][".pdf"] == 1
