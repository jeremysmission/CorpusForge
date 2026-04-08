"""
CorpusForge Corpus Audit Tool (Sprint 4, Slice 4.3)

Generates reports on the latest export:
  - Corpus summary (files, chunks, entities, vectors)
  - Format coverage breakdown
  - Duplicate detection summary
  - Quality score distribution
  - Entity type distribution
  - Skip/failure analysis

Usage:
  python scripts/audit_corpus.py                    # Audit latest export
  python scripts/audit_corpus.py --export-dir data/output/export_20260407_2141
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def find_latest_export(output_dir: Path) -> Path | None:
    """Find the most recent export directory."""
    exports = sorted(output_dir.glob("export_*"), key=lambda p: p.name, reverse=True)
    return exports[0] if exports else None


def audit(export_dir: Path) -> dict:
    """Run full audit on an export directory."""
    results = {"export_dir": str(export_dir), "errors": []}

    # 1. Chunks
    chunks_path = export_dir / "chunks.jsonl"
    chunks = []
    if chunks_path.exists():
        with open(chunks_path, encoding="utf-8") as f:
            for line in f:
                chunks.append(json.loads(line))
    results["chunk_count"] = len(chunks)

    # 2. Vectors
    vectors_path = export_dir / "vectors.npy"
    if vectors_path.exists():
        import numpy as np
        vectors = np.load(vectors_path)
        results["vector_shape"] = list(vectors.shape)
        results["vector_dtype"] = str(vectors.dtype)
        results["vectors_match_chunks"] = vectors.shape[0] == len(chunks)
    else:
        results["vector_shape"] = None
        results["vectors_match_chunks"] = None

    # 3. Entities
    entities_path = export_dir / "entities.jsonl"
    entities = []
    if entities_path.exists():
        with open(entities_path, encoding="utf-8") as f:
            for line in f:
                entities.append(json.loads(line))
    results["entity_count"] = len(entities)

    # Entity type distribution
    entity_types = Counter(e.get("label", "UNKNOWN") for e in entities)
    results["entity_types"] = dict(entity_types.most_common())

    # Entity confidence distribution
    if entities:
        scores = [e.get("score", 0) for e in entities]
        results["entity_score_avg"] = round(sum(scores) / len(scores), 3)
        results["entity_score_min"] = round(min(scores), 3)
        results["entity_score_max"] = round(max(scores), 3)

    # 4. Format coverage
    format_counts = Counter()
    for chunk in chunks:
        src = chunk.get("source_path", "")
        ext = Path(src).suffix.lower() or "(no ext)"
        format_counts[ext] += 1
    results["format_coverage"] = dict(format_counts.most_common())

    # 5. Quality distribution
    qualities = [chunk.get("parse_quality", 0) for chunk in chunks]
    if qualities:
        results["quality_avg"] = round(sum(qualities) / len(qualities), 3)
        results["quality_min"] = round(min(qualities), 3)
        results["quality_max"] = round(max(qualities), 3)
        # Buckets
        buckets = {"excellent (0.9-1.0)": 0, "good (0.7-0.9)": 0, "fair (0.5-0.7)": 0, "poor (<0.5)": 0}
        for q in qualities:
            if q >= 0.9:
                buckets["excellent (0.9-1.0)"] += 1
            elif q >= 0.7:
                buckets["good (0.7-0.9)"] += 1
            elif q >= 0.5:
                buckets["fair (0.5-0.7)"] += 1
            else:
                buckets["poor (<0.5)"] += 1
        results["quality_distribution"] = buckets

    # 6. Chunk size distribution
    sizes = [chunk.get("text_length", 0) for chunk in chunks]
    if sizes:
        results["chunk_size_avg"] = round(sum(sizes) / len(sizes))
        results["chunk_size_min"] = min(sizes)
        results["chunk_size_max"] = max(sizes)

    # 7. Enrichment coverage
    enriched = sum(1 for c in chunks if c.get("enriched_text") is not None)
    results["enrichment_coverage"] = f"{enriched}/{len(chunks)}"

    # 8. Duplicate text detection (exact chunk text matches)
    text_hashes = Counter()
    for chunk in chunks:
        text_hashes[hash(chunk.get("text", ""))] += 1
    dupes = {k: v for k, v in text_hashes.items() if v > 1}
    results["duplicate_chunks"] = sum(v - 1 for v in dupes.values())
    results["unique_chunks"] = len(text_hashes)

    # 9. Manifest
    manifest_path = export_dir / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8") as f:
            results["manifest"] = json.load(f)

    # 10. Skip manifest
    skip_path = export_dir / "skip_manifest.json"
    if skip_path.exists():
        with open(skip_path, encoding="utf-8") as f:
            skip_data = json.load(f)
        if isinstance(skip_data, list):
            results["skipped_files"] = len(skip_data)
        elif isinstance(skip_data, dict):
            results["skipped_files"] = skip_data.get("count", 0)

    return results


def print_report(results: dict) -> None:
    """Print a human-readable audit report."""
    print()
    print("=" * 60)
    print("  CorpusForge Corpus Audit Report")
    print("=" * 60)
    print(f"  Export: {results['export_dir']}")
    print()

    print("  Corpus Summary")
    print(f"    Chunks:        {results['chunk_count']}")
    print(f"    Vectors:       {results.get('vector_shape', 'N/A')}")
    print(f"    Match:         {results.get('vectors_match_chunks', 'N/A')}")
    print(f"    Entities:      {results['entity_count']}")
    print(f"    Enriched:      {results.get('enrichment_coverage', 'N/A')}")
    print(f"    Unique chunks: {results.get('unique_chunks', 'N/A')}")
    print(f"    Duplicates:    {results.get('duplicate_chunks', 0)}")
    print()

    if results.get("format_coverage"):
        print("  Format Coverage (chunks per format)")
        for ext, count in results["format_coverage"].items():
            print(f"    {ext:12s}  {count}")
        print()

    if results.get("quality_distribution"):
        print("  Parse Quality Distribution")
        for bucket, count in results["quality_distribution"].items():
            print(f"    {bucket:20s}  {count}")
        print(f"    Average: {results.get('quality_avg', 'N/A')}")
        print()

    if results.get("entity_types"):
        print("  Entity Type Distribution")
        for label, count in results["entity_types"].items():
            print(f"    {label:20s}  {count}")
        if "entity_score_avg" in results:
            print(f"    Avg confidence: {results['entity_score_avg']}")
        print()

    if results.get("chunk_size_avg"):
        print("  Chunk Size Stats")
        print(f"    Avg: {results['chunk_size_avg']} chars")
        print(f"    Min: {results['chunk_size_min']} chars")
        print(f"    Max: {results['chunk_size_max']} chars")
        print()

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="CorpusForge Corpus Audit")
    parser.add_argument(
        "--export-dir",
        help="Path to export directory. Default: latest export.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of human-readable.",
    )
    args = parser.parse_args()

    if args.export_dir:
        export_dir = Path(args.export_dir)
    else:
        output_dir = PROJECT_ROOT / "data" / "output"
        export_dir = find_latest_export(output_dir)
        if not export_dir:
            print("No exports found in data/output/", file=sys.stderr)
            return 1

    if not export_dir.exists():
        print(f"Export directory not found: {export_dir}", file=sys.stderr)
        return 1

    results = audit(export_dir)

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        print_report(results)

    return 0


if __name__ == "__main__":
    sys.exit(main())
