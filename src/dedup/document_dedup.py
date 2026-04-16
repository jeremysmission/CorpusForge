"""Recovery-stage document deduplication.

This module decides which file to keep when several files appear to be
versions of the same document. It normalizes extracted text, compares
candidate copies, keeps the strongest canonical file, and writes an
audit trail so an operator can understand the decision later.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from src.parse.dispatcher import ParseDispatcher


WORD_RE = re.compile(r"[A-Za-z0-9]+")
COPY_SUFFIX_RE = re.compile(r"(?:[\s_\-]copy|[\s_\-]final|[\s_\-]signed|[\s_\-]scan(?:ned)?|[\s_\-]ocr)+$", re.IGNORECASE)
TRAILING_INDEX_RE = re.compile(r"(?:[_\-\s]|\()(\d{1,3})\)?$")
PAGE_PATTERNS = (
    re.compile(r"^page \d+ of \d+$"),
    re.compile(r"^page \d+$"),
    re.compile(r"^\d+/\d+$"),
    re.compile(r"^\d+$"),
    re.compile(r"^printed on .+$"),
    re.compile(r"^generated on .+$"),
    re.compile(r"^created on .+$"),
)


@dataclass
class FingerprintedDocument:
    path: Path
    ext: str
    stem_key: str
    parse_quality: float
    raw_chars: int
    normalized_chars: int
    normalized_hash: str
    normalized_text: str


@dataclass
class DedupDecision:
    path: str
    status: str
    canonical_path: str
    dedup_reason: str
    similarity: float
    ext: str
    stem_key: str
    parse_quality: float
    raw_chars: int
    normalized_chars: int
    normalized_hash: str


@dataclass
class DedupRunStats:
    files_seen: int
    candidate_groups: int
    singleton_files: int
    groups_processed: int
    canonical_files: int
    duplicate_files: int
    elapsed_seconds: float
    stopped: bool
    current_group: str = ""
    current_group_size: int = 0


def build_stem_key(path: Path) -> str:
    """Normalize a filename stem into a loose document family key."""
    stem = unicodedata.normalize("NFKC", path.stem.lower())
    stem = stem.replace("&", " and ")
    stem = TRAILING_INDEX_RE.sub("", stem)
    stem = COPY_SUFFIX_RE.sub("", stem)
    stem = re.sub(r"[\[\]\(\)]", " ", stem)
    stem = re.sub(r"[_\-\s]+", " ", stem)
    tokens = WORD_RE.findall(stem)
    return " ".join(tokens) or path.stem.lower()


def normalize_extracted_text(text: str) -> str:
    """Collapse layout-only differences so cross-format copies line up."""
    if not text:
        return ""

    # Normalize Unicode and line endings first so comparison focuses on
    # content rather than formatting quirks from different file sources.
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)

    cleaned_lines: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        # Page counters and print stamps often change between copies, so
        # they are treated as noise instead of real document content.
        if any(pattern.match(lowered) for pattern in PAGE_PATTERNS):
            continue
        cleaned_lines.append(lowered)

    if not cleaned_lines:
        return ""

    counts = Counter(cleaned_lines)
    filtered_lines = [
        line for line in cleaned_lines
        # Repeated short lines are usually headers or footers repeated on
        # every page. Removing them makes duplicate checks more accurate.
        if not (counts[line] >= 3 and len(line) <= 120)
    ]
    return "\n".join(filtered_lines or cleaned_lines)


def hash_normalized_text(text: str) -> str:
    """Stable hash of normalized extracted text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _word_shingles(text: str, size: int = 5) -> set[str]:
    tokens = WORD_RE.findall(text)
    if not tokens:
        return set()
    if len(tokens) <= size:
        return {" ".join(tokens)}
    return {
        " ".join(tokens[idx:idx + size])
        for idx in range(len(tokens) - size + 1)
    }


def _line_units(text: str) -> set[str]:
    return {line for line in text.splitlines() if line}


def _containment(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, min(len(left), len(right)))


def score_similarity(left: str, right: str) -> float:
    """Containment score that tolerates one-sided appendices/signatures."""
    line_score = _containment(_line_units(left), _line_units(right))
    shingle_score = _containment(_word_shingles(left), _word_shingles(right))
    return round(max(line_score, shingle_score), 4)


def parse_document(path: Path, dispatcher: ParseDispatcher) -> FingerprintedDocument:
    """Parse and fingerprint a single supported document."""
    parsed = dispatcher.parse(path)
    normalized = normalize_extracted_text(parsed.text)
    return FingerprintedDocument(
        path=path,
        ext=path.suffix.lower(),
        stem_key=build_stem_key(path),
        parse_quality=float(parsed.parse_quality),
        raw_chars=len(parsed.text),
        normalized_chars=len(normalized),
        normalized_hash=hash_normalized_text(normalized) if normalized else "",
        normalized_text=normalized,
    )


def _canonical_sort_key(doc: FingerprintedDocument) -> tuple[float, int, int, str]:
    ext_rank = {".docx": 3, ".doc": 2, ".pdf": 1}.get(doc.ext, 0)
    return (doc.parse_quality, ext_rank, doc.normalized_chars, str(doc.path).lower())


def classify_same_stem_group(
    docs: list[FingerprintedDocument],
    *,
    similarity_threshold: float,
    min_chars: int,
) -> list[DedupDecision]:
    """Classify documents in one filename family into canonical vs duplicate."""
    if not docs:
        return []

    # Put the strongest candidates first so later files are compared
    # against the best available version of the document.
    docs = sorted(docs, key=_canonical_sort_key, reverse=True)
    canonical_docs: list[FingerprintedDocument] = []
    duplicate_pairs: dict[str, tuple[FingerprintedDocument, str, float]] = {}

    exact_hash_map: dict[str, FingerprintedDocument] = {}

    for doc in docs:
        # Weak parses are kept by default because there is not enough text
        # to make a safe duplicate decision.
        if doc.normalized_chars < min_chars or not doc.normalized_hash:
            canonical_docs.append(doc)
            continue

        # Exact normalized hashes are the most trustworthy duplicate signal.
        exact_match = exact_hash_map.get(doc.normalized_hash)
        if exact_match is not None:
            duplicate_pairs[str(doc.path)] = (
                exact_match,
                "exact_normalized_text",
                1.0,
            )
            continue

        matched = False
        for canonical in canonical_docs:
            if canonical.normalized_chars < min_chars or not canonical.normalized_hash:
                continue
            # Near-duplicate matching handles cases like an extra signature
            # page or the same document saved in a different format.
            similarity = score_similarity(doc.normalized_text, canonical.normalized_text)
            if similarity >= similarity_threshold:
                duplicate_pairs[str(doc.path)] = (
                    canonical,
                    "near_duplicate_same_stem",
                    similarity,
                )
                matched = True
                break

        if matched:
            continue

        canonical_docs.append(doc)
        exact_hash_map[doc.normalized_hash] = doc

    decisions: list[DedupDecision] = []
    canonical_paths = {str(doc.path) for doc in canonical_docs}

    for doc in docs:
        if str(doc.path) in canonical_paths:
            decisions.append(
                DedupDecision(
                    path=str(doc.path),
                    status="canonical",
                    canonical_path=str(doc.path),
                    dedup_reason="kept_best_in_family",
                    similarity=1.0,
                    ext=doc.ext,
                    stem_key=doc.stem_key,
                    parse_quality=doc.parse_quality,
                    raw_chars=doc.raw_chars,
                    normalized_chars=doc.normalized_chars,
                    normalized_hash=doc.normalized_hash,
                )
            )
            continue

        canonical, reason, similarity = duplicate_pairs[str(doc.path)]
        decisions.append(
            DedupDecision(
                path=str(doc.path),
                status="duplicate",
                canonical_path=str(canonical.path),
                dedup_reason=reason,
                similarity=similarity,
                ext=doc.ext,
                stem_key=doc.stem_key,
                parse_quality=doc.parse_quality,
                raw_chars=doc.raw_chars,
                normalized_chars=doc.normalized_chars,
                normalized_hash=doc.normalized_hash,
            )
        )

    return sorted(decisions, key=lambda item: item.path.lower())


def group_paths_by_stem(paths: Iterable[Path]) -> dict[str, list[Path]]:
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in paths:
        grouped[build_stem_key(path)].append(path)
    return dict(grouped)


def discover_files(input_path: Path, extensions: set[str]) -> list[Path]:
    """Find files for the dedup pass."""
    if input_path.is_file():
        return [input_path] if input_path.suffix.lower() in extensions else []
    if not input_path.is_dir():
        raise FileNotFoundError(f"{input_path} not found")
    return sorted(
        path for path in input_path.rglob("*")
        if path.is_file() and path.suffix.lower() in extensions
    )


def make_singleton_decision(path: Path) -> DedupDecision:
    """Canonical placeholder for files skipped from same-stem parsing."""
    return DedupDecision(
        path=str(path),
        status="canonical",
        canonical_path=str(path),
        dedup_reason="singleton_skipped",
        similarity=1.0,
        ext=path.suffix.lower(),
        stem_key=build_stem_key(path),
        parse_quality=0.0,
        raw_chars=0,
        normalized_chars=0,
        normalized_hash="",
    )


def run_document_dedup(
    *,
    input_path: Path,
    dispatcher: ParseDispatcher,
    extensions: set[str],
    similarity_threshold: float,
    min_chars: int,
    workers: int,
    on_group=None,
    should_stop=None,
) -> tuple[list[DedupDecision], DedupRunStats]:
    """Run the focused recovery-stage dedup pass for same-stem document families."""
    start_time = time.time()
    files = discover_files(input_path, extensions)
    groups = group_paths_by_stem(files)
    # Single-file families do not need comparison work.
    candidate_groups = {
        stem: paths for stem, paths in groups.items()
        if len(paths) > 1
    }
    singleton_paths = [
        paths[0] for paths in groups.values()
        if len(paths) == 1
    ]

    decisions: list[DedupDecision] = []
    # A group with only one file is automatically the canonical copy.
    decisions.extend(make_singleton_decision(path) for path in singleton_paths)

    processed_groups = 0
    stopped = False
    total_groups = len(candidate_groups)

    for stem_key, group_paths in sorted(candidate_groups.items()):
        if should_stop and should_stop():
            stopped = True
            break

        processed_groups += 1
        if on_group:
            on_group(
                stem_key=stem_key,
                group_index=processed_groups,
                total_groups=total_groups,
                group_size=len(group_paths),
            )

        docs = []
        with ThreadPoolExecutor(max_workers=min(workers, len(group_paths))) as pool:
            futures = [pool.submit(parse_document, path, dispatcher) for path in group_paths]
            for future in as_completed(futures):
                docs.append(future.result())

        decisions.extend(
            classify_same_stem_group(
                docs,
                similarity_threshold=similarity_threshold,
                min_chars=min_chars,
            )
        )

    canonical_files = sum(1 for row in decisions if row.status == "canonical")
    duplicate_files = sum(1 for row in decisions if row.status == "duplicate")
    current_group = ""
    current_group_size = 0
    # FIXME: These fields are only filled when `on_group` is provided,
    # which means callback-free runs can return blank progress metadata
    # even after successfully processing groups.
    if on_group and total_groups > 0 and processed_groups > 0:
        current_group = stem_key
        current_group_size = len(group_paths)

    stats = DedupRunStats(
        files_seen=len(files),
        candidate_groups=total_groups,
        singleton_files=len(singleton_paths),
        groups_processed=processed_groups,
        canonical_files=canonical_files,
        duplicate_files=duplicate_files,
        elapsed_seconds=time.time() - start_time,
        stopped=stopped,
        current_group=current_group,
        current_group_size=current_group_size,
    )
    return decisions, stats


def write_index(
    decisions: Iterable[DedupDecision],
    *,
    db_path: Path,
    canonical_list_path: Path,
    duplicate_jsonl_path: Path,
    report_path: Path,
    source_root: Path,
    extensions: list[str],
    similarity_threshold: float,
    min_chars: int,
) -> None:
    """Write sqlite index plus manifest files for pipeline reuse."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("DROP TABLE IF EXISTS document_dedup")
    conn.execute(
        """
        CREATE TABLE document_dedup (
            path TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            canonical_path TEXT NOT NULL,
            dedup_reason TEXT NOT NULL,
            similarity REAL NOT NULL,
            ext TEXT NOT NULL,
            stem_key TEXT NOT NULL,
            parse_quality REAL NOT NULL,
            raw_chars INTEGER NOT NULL,
            normalized_chars INTEGER NOT NULL,
            normalized_hash TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX idx_document_dedup_status ON document_dedup(status)")
    conn.execute("CREATE INDEX idx_document_dedup_stem ON document_dedup(stem_key)")

    rows = list(decisions)
    conn.executemany(
        """
        INSERT INTO document_dedup (
            path, status, canonical_path, dedup_reason, similarity, ext,
            stem_key, parse_quality, raw_chars, normalized_chars, normalized_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row.path,
                row.status,
                row.canonical_path,
                row.dedup_reason,
                row.similarity,
                row.ext,
                row.stem_key,
                row.parse_quality,
                row.raw_chars,
                row.normalized_chars,
                row.normalized_hash,
            )
            for row in rows
        ],
    )
    conn.commit()
    conn.close()

    canonical_paths = sorted(
        row.path for row in rows if row.status == "canonical"
    )
    duplicate_rows = [
        row for row in rows if row.status == "duplicate"
    ]

    # This plain text list is the simplest output for downstream steps:
    # it tells later tooling exactly which files survived dedup.
    with open(canonical_list_path, "w", encoding="utf-8", newline="\n") as handle:
        for path in canonical_paths:
            handle.write(path + "\n")

    with open(duplicate_jsonl_path, "w", encoding="utf-8", newline="\n") as handle:
        for row in duplicate_rows:
            handle.write(json.dumps(row.__dict__, ensure_ascii=False) + "\n")

    report = {
        "source_root": str(source_root),
        "extensions": extensions,
        "files_seen": len(rows),
        "canonical_files": len(canonical_paths),
        "duplicate_files": len(duplicate_rows),
        "dedup_reduction_pct": round(
            (len(duplicate_rows) / max(1, len(rows))) * 100.0, 2
        ),
        "similarity_threshold": similarity_threshold,
        "min_chars": min_chars,
        "canonical_list_path": str(canonical_list_path),
        "duplicate_jsonl_path": str(duplicate_jsonl_path),
        "sqlite_index_path": str(db_path),
        "dedup_reasons": dict(Counter(row.dedup_reason for row in rows)),
    }
    with open(report_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
