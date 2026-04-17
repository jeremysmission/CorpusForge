"""Regression tests for the Forge-to-V2 export metadata contract.

Plain-English summary for operators:
Forge produces exports that downstream V2 imports. That handoff has a
contract: certain fields must be present on every chunk and entity row,
manifest must carry specific keys, and the skip manifest must keep its
legacy alias keys. This file inspects a real export directory and
flags any contract gaps. If these tests fail, V2 import could reject a
freshly-shipped export — or worse, quietly accept it and hide missing
metadata.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from src.analysis.export_metadata_contract import analyze_export_metadata_contract


def _write_min_export(export_dir: Path) -> None:
    export_dir.mkdir(parents=True, exist_ok=True)

    chunks = [
        {
            "chunk_id": "c001",
            "text": "alpha text",
            "enriched_text": "",
            "source_path": "root/docs/a.pdf",
            "chunk_index": 0,
            "text_length": 10,
            "parse_quality": 0.97,
        },
        {
            "chunk_id": "c002",
            "text": "beta text",
            "enriched_text": None,
            "source_path": "root/docs/b.xlsx",
            "chunk_index": 1,
            "text_length": 9,
            "parse_quality": 0.82,
        },
    ]
    with open(export_dir / "chunks.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk) + "\n")

    np.save(str(export_dir / "vectors.npy"), np.zeros((2, 4), dtype=np.float16))
    (export_dir / "manifest.json").write_text(
        json.dumps({
            "chunk_count": 2,
            "vector_dim": 4,
            "vector_dtype": "float16",
            "entity_count": 1,
            "embedding_model": "nomic",
            "timestamp": "2026-04-12T23:00:00",
            "stats": {"chunks_created": 2},
        }),
        encoding="utf-8",
    )
    (export_dir / "skip_manifest.json").write_text(
        json.dumps({
            "total_skipped": 3,
            "counts_by_reason": {"Deferred by config for this run": 3},
            "files": [
                {"path": "root/raw/archive_1.dwf", "reason": "Deferred by config for this run"},
            ],
        }),
        encoding="utf-8",
    )
    with open(export_dir / "entities.jsonl", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({
            "chunk_id": "c001",
            "text": "SITE-1",
            "label": "SITE",
            "score": 0.91,
            "start": 0,
            "end": 6,
        }) + "\n")
    (export_dir / "run_report.txt").write_text("ok\n", encoding="utf-8")


def test_analyze_export_metadata_contract_flags_live_contract_gaps(tmp_path: Path):
    """Protects the V2 contract checker — missing fields (source_ext, authority_tier, entities.source_path, legacy skip aliases) must be reported as gaps."""
    export_dir = tmp_path / "export_20260412_2300"
    _write_min_export(export_dir)

    report = analyze_export_metadata_contract(export_dir)

    assert report["chunk_schema"]["rows"] == 2
    assert report["chunk_schema"]["unique_keys"] == [
        "chunk_id",
        "chunk_index",
        "enriched_text",
        "parse_quality",
        "source_path",
        "text",
        "text_length",
    ]

    field_presence = {row["field"]: row["present_rows"] for row in report["chunk_schema"]["field_presence"]}
    assert field_presence["source_path"] == 2
    assert field_presence["source_ext"] == 0
    assert field_presence["authority_tier"] == 0

    entity_presence = {row["field"]: row["present_rows"] for row in report["entities_artifact"]["field_presence"]}
    assert entity_presence["chunk_id"] == 1
    assert entity_presence["source_path"] == 0

    skip_summary = report["skip_manifest_summary"]
    assert skip_summary["legacy_aliases_present"] == {
        "count": False,
        "skipped_files": False,
        "deferred_formats": False,
    }
    assert "skip_manifest.json is missing one or more legacy V2 alias keys." in report["contract_gaps"]
    assert "entities.jsonl rows omit source_path and require chunk_id backfill." in report["contract_gaps"]
