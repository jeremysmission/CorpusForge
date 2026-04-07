from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class ReviewMember:
    path: str
    status: str
    ext: str
    parse_quality: float
    raw_chars: int
    normalized_chars: int
    similarity: float
    dedup_reason: str
    normalized_hash: str


@dataclass
class ReviewFamily:
    family_id: str
    canonical_path: str
    canonical_ext: str
    canonical_parse_quality: float
    members: list[ReviewMember]
    review_flags: list[str]
    recommendation: str

    @property
    def duplicate_count(self) -> int:
        return sum(1 for member in self.members if member.status == "duplicate")

    @property
    def family_size(self) -> int:
        return len(self.members)

    @property
    def max_similarity(self) -> float:
        if not self.members:
            return 1.0
        return max(member.similarity for member in self.members)

    @property
    def min_similarity(self) -> float:
        if not self.members:
            return 1.0
        return min(member.similarity for member in self.members)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review dedup samples from existing recovery outputs.")
    parser.add_argument(
        "--dedup-dir",
        required=True,
        help="Directory containing dedup_report.json plus either duplicate_files.jsonl or chunks.jsonl.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Optional output directory. Defaults to <dedup-dir>/review_<timestamp>.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum families to include in the review report.",
    )
    parser.add_argument(
        "--sort",
        choices=("largest", "similarity", "path"),
        default="largest",
        help="Sort order for sampled families.",
    )
    return parser.parse_args()


def clean_preview(text: str, limit: int = 180) -> str:
    if not text:
        return ""
    text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def markdown_escape(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if raw:
                rows.append(json.loads(raw))
    return rows


def load_sqlite_rows(db_path: Path, canonical_paths: Iterable[str]) -> dict[str, list[dict]]:
    family_map: dict[str, list[dict]] = defaultdict(list)
    if not db_path.exists():
        return family_map

    canonical_paths = list(dict.fromkeys(canonical_paths))
    if not canonical_paths:
        return family_map

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" for _ in canonical_paths)
        query = f"""
            SELECT path, status, canonical_path, dedup_reason, similarity, ext, stem_key,
                   parse_quality, raw_chars, normalized_chars, normalized_hash
            FROM document_dedup
            WHERE canonical_path IN ({placeholders})
            ORDER BY canonical_path, status DESC, similarity DESC, path
        """
        for row in conn.execute(query, canonical_paths):
            family_map[row["canonical_path"]].append(dict(row))
    finally:
        conn.close()
    return family_map


def recommend_family(canonical_ext: str, members: list[ReviewMember]) -> tuple[str, list[str]]:
    flags: list[str] = []
    ext_set = {member.ext.lower() for member in members if member.ext}
    if ".docx" in ext_set and canonical_ext != ".docx":
        flags.append("prefer_docx_if_parse_quality_is_close")
    if ".doc" in ext_set and canonical_ext == ".pdf":
        flags.append("prefer_editable_source_over_pdf")
    if ".pdf" in ext_set and (".docx" in ext_set or ".doc" in ext_set):
        flags.append("mixed_format_family")
    if any(member.dedup_reason == "near_duplicate_same_stem" and member.similarity < 0.95 for member in members if member.status == "duplicate"):
        flags.append("review_near_duplicate_threshold")

    if flags:
        return "review_canonical_choice", flags
    return "keep_canonical_choice", ["low_risk_family"]


def build_document_review_families(dedup_dir: Path) -> list[ReviewFamily]:
    sqlite_path = dedup_dir / "document_dedup.sqlite3"
    dup_path = dedup_dir / "duplicate_files.jsonl"
    if not dup_path.exists():
        raise FileNotFoundError(f"Missing duplicate_files.jsonl in {dedup_dir}")

    duplicate_rows = load_jsonl(dup_path)
    by_canonical: dict[str, list[dict]] = defaultdict(list)
    for row in duplicate_rows:
        by_canonical[row["canonical_path"]].append(row)

    sqlite_rows = load_sqlite_rows(sqlite_path, by_canonical.keys())
    families: list[ReviewFamily] = []

    for canonical_path, duplicates in sorted(by_canonical.items(), key=lambda item: (-len(item[1]), item[0].lower())):
        rows = sqlite_rows.get(canonical_path, [])
        row_map = {row["path"]: row for row in rows}
        members: list[ReviewMember] = []

        canonical_row = next((row for row in rows if row["status"] == "canonical"), None)
        if canonical_row is None:
            canonical_row = {
                "path": canonical_path,
                "status": "canonical",
                "ext": Path(canonical_path).suffix.lower(),
                "parse_quality": 0.0,
                "raw_chars": 0,
                "normalized_chars": 0,
                "similarity": 1.0,
                "dedup_reason": "kept_best_in_family",
                "normalized_hash": "",
            }

        members.append(
            ReviewMember(
                path=canonical_row["path"],
                status=canonical_row["status"],
                ext=canonical_row["ext"],
                parse_quality=float(canonical_row["parse_quality"]),
                raw_chars=int(canonical_row["raw_chars"]),
                normalized_chars=int(canonical_row["normalized_chars"]),
                similarity=float(canonical_row["similarity"]),
                dedup_reason=canonical_row["dedup_reason"],
                normalized_hash=canonical_row["normalized_hash"],
            )
        )

        for row in duplicates:
            sqlite_row = row_map.get(row["path"], row)
            members.append(
                ReviewMember(
                    path=sqlite_row["path"],
                    status=sqlite_row["status"],
                    ext=sqlite_row["ext"],
                    parse_quality=float(sqlite_row["parse_quality"]),
                    raw_chars=int(sqlite_row["raw_chars"]),
                    normalized_chars=int(sqlite_row["normalized_chars"]),
                    similarity=float(sqlite_row["similarity"]),
                    dedup_reason=sqlite_row["dedup_reason"],
                    normalized_hash=sqlite_row["normalized_hash"],
                )
            )

        recommendation, flags = recommend_family(members[0].ext, members)
        families.append(
            ReviewFamily(
                family_id=canonical_path,
                canonical_path=canonical_path,
                canonical_ext=members[0].ext,
                canonical_parse_quality=members[0].parse_quality,
                members=members,
                review_flags=flags,
                recommendation=recommendation,
            )
        )

    return families


def load_chunk_map(chunks_path: Path) -> dict[str, dict]:
    chunk_map: dict[str, dict] = {}
    with chunks_path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            row = json.loads(raw)
            chunk_map[row["chunk_id"]] = row
    return chunk_map


def build_chunk_review_families(dedup_report_path: Path, chunks_path: Path) -> list[ReviewFamily]:
    report = load_json(dedup_report_path)
    sample_clusters = report.get("sample_clusters", [])
    chunk_map = load_chunk_map(chunks_path)
    families: list[ReviewFamily] = []

    for cluster in sample_clusters:
        canonical_id = cluster["canonical_chunk_id"]
        canonical_chunk = chunk_map.get(canonical_id, {})
        canonical_source = cluster.get("canonical_source") or canonical_chunk.get("source_path", canonical_id)
        members: list[ReviewMember] = []

        members.append(
            ReviewMember(
                path=canonical_source,
                status="canonical",
                ext=Path(canonical_source).suffix.lower(),
                parse_quality=float(canonical_chunk.get("parse_quality", 0.0)),
                raw_chars=int(canonical_chunk.get("text_length", len(canonical_chunk.get("text", "")))),
                normalized_chars=int(canonical_chunk.get("text_length", len(canonical_chunk.get("text", "")))),
                similarity=1.0,
                dedup_reason="cluster_canonical",
                normalized_hash=canonical_id,
            )
        )

        duplicate_chunk_ids = cluster.get("duplicate_chunk_ids", [])
        similarities = cluster.get("similarity_to_canonical", [])
        for idx, dup_id in enumerate(duplicate_chunk_ids):
            dup_chunk = chunk_map.get(dup_id, {})
            source_path = dup_chunk.get("source_path", dup_id)
            preview = clean_preview(dup_chunk.get("text", ""), 180)
            members.append(
                ReviewMember(
                    path=f"{source_path} :: {preview}" if preview else source_path,
                    status="duplicate",
                    ext=Path(source_path).suffix.lower(),
                    parse_quality=float(dup_chunk.get("parse_quality", 0.0)),
                    raw_chars=int(dup_chunk.get("text_length", len(dup_chunk.get("text", "")))),
                    normalized_chars=int(dup_chunk.get("text_length", len(dup_chunk.get("text", "")))),
                    similarity=float(similarities[idx]) if idx < len(similarities) else 0.0,
                    dedup_reason="chunk_cluster_member",
                    normalized_hash=dup_id,
                )
            )

        recommendation, flags = recommend_family(members[0].ext, members)
        families.append(
            ReviewFamily(
                family_id=canonical_id,
                canonical_path=canonical_source,
                canonical_ext=members[0].ext,
                canonical_parse_quality=members[0].parse_quality,
                members=members,
                review_flags=flags,
                recommendation=recommendation,
            )
        )

    return families


def sort_families(families: list[ReviewFamily], mode: str) -> list[ReviewFamily]:
    if mode == "path":
        return sorted(families, key=lambda item: item.canonical_path.lower())
    if mode == "similarity":
        return sorted(families, key=lambda item: (-item.max_similarity, -item.duplicate_count, item.canonical_path.lower()))
    return sorted(families, key=lambda item: (-item.duplicate_count, -item.family_size, item.canonical_path.lower()))


def write_outputs(output_dir: Path, families: list[ReviewFamily], source_label: str) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "dedup_review_report.md"
    jsonl_path = output_dir / "dedup_review_rows.jsonl"
    csv_path = output_dir / "dedup_review_rows.csv"

    report_lines = [
        "# Dedup Review Report",
        "",
        f"**Source:** {source_label}",
        f"**Generated:** {datetime.now().isoformat(timespec='seconds')}",
        f"**Families:** {len(families)}",
        "",
        "## Summary",
        "",
        "| Family | Canonical | Ext | Size | Duplicates | Max Similarity | Recommendation | Flags |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]

    with jsonl_path.open("w", encoding="utf-8", newline="\n") as jsonl_handle, csv_path.open("w", encoding="utf-8", newline="") as csv_handle:
        writer = csv.DictWriter(
            csv_handle,
            fieldnames=[
                "family_id",
                "canonical_path",
                "canonical_ext",
                "family_size",
                "duplicate_count",
                "max_similarity",
                "min_similarity",
                "recommendation",
                "review_flags",
                "member_path",
                "member_status",
                "member_ext",
                "member_parse_quality",
                "member_similarity",
                "member_reason",
            ],
        )
        writer.writeheader()

        for family in families:
            report_lines.append(
                f"| `{markdown_escape(family.family_id)}` | `{markdown_escape(family.canonical_path)}` | `{family.canonical_ext}` | "
                f"{family.family_size} | {family.duplicate_count} | {family.max_similarity:.3f} | {family.recommendation} | "
                f"{', '.join(family.review_flags)} |"
            )
            report_lines.extend(
                [
                    "",
                    f"### {markdown_escape(family.canonical_path)}",
                    "",
                    f"- Canonical: `{markdown_escape(family.canonical_path)}`",
                    f"- Recommendation: `{family.recommendation}`",
                    f"- Flags: {', '.join(family.review_flags)}",
                    "",
                    "| Status | Path | Ext | Parse Quality | Similarity | Reason |",
                    "| --- | --- | --- | ---: | ---: | --- |",
                ]
            )
            for member in family.members:
                report_lines.append(
                    f"| {member.status} | `{markdown_escape(member.path)}` | `{member.ext}` | "
                    f"{member.parse_quality:.3f} | {member.similarity:.3f} | {member.dedup_reason} |"
                )
                row = {
                    "family_id": family.family_id,
                    "canonical_path": family.canonical_path,
                    "canonical_ext": family.canonical_ext,
                    "family_size": family.family_size,
                    "duplicate_count": family.duplicate_count,
                    "max_similarity": round(family.max_similarity, 4),
                    "min_similarity": round(family.min_similarity, 4),
                    "recommendation": family.recommendation,
                    "review_flags": family.review_flags,
                    "member_path": member.path,
                    "member_status": member.status,
                    "member_ext": member.ext,
                    "member_parse_quality": member.parse_quality,
                    "member_similarity": member.similarity,
                    "member_reason": member.dedup_reason,
                }
                jsonl_handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                writer.writerow({k: row.get(k) for k in writer.fieldnames})

            report_lines.append("")

    md_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8", newline="\n")
    return md_path, jsonl_path, csv_path


def main() -> None:
    args = parse_args()
    dedup_dir = Path(args.dedup_dir).resolve()
    if not dedup_dir.exists():
        raise FileNotFoundError(dedup_dir)

    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        output_dir = dedup_dir / f"review_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if (dedup_dir / "duplicate_files.jsonl").exists():
        families = build_document_review_families(dedup_dir)
        source_label = f"document dedup output: {dedup_dir}"
    elif (dedup_dir / "dedup_report.json").exists() and (dedup_dir / "chunks.jsonl").exists():
        families = build_chunk_review_families(dedup_dir / "dedup_report.json", dedup_dir / "chunks.jsonl")
        source_label = f"chunk dedup output: {dedup_dir}"
    else:
        raise FileNotFoundError(
            f"{dedup_dir} does not contain duplicate_files.jsonl or dedup_report.json + chunks.jsonl"
        )

    families = sort_families(families, args.sort)[: max(1, args.limit)]
    md_path, jsonl_path, csv_path = write_outputs(output_dir, families, source_label)

    print(f"Review report written: {md_path}")
    print(f"Review rows written:   {jsonl_path}")
    print(f"Review CSV written:    {csv_path}")
    print(f"Families included:      {len(families)}")


if __name__ == "__main__":
    main()
