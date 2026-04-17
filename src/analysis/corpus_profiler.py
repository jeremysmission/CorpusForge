"""Corpus profiling helpers for source-tree adaptation work.

Plain-English role
------------------
Offline tool. An operator points this at a raw source folder (before a
pipeline run) and gets back a summary of what is in there: which file
extensions dominate, which folders are huge, how many OCR sidecars
there are, which folders look like duplicate extract-this-archive
trees, and a few plain-language recommendations for skip/defer policy.

Used to plan how to configure Forge for a new corpus, not during a
production run.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    ".tif", ".tiff", ".svg", ".wmf", ".emf",
}
ARCHIVE_EXTENSIONS = {
    ".zip", ".7z", ".rar", ".tar", ".tgz", ".gz", ".bz2", ".xz",
}
DRAWING_EXTENSIONS = {
    ".drawio", ".dia", ".dxf", ".dwg", ".vsdx", ".svg",
    ".stp", ".step", ".ste", ".igs", ".iges", ".stl",
}
STOP_TOKENS = {
    "and", "for", "the", "with", "from", "that", "this", "into",
    "scan", "copy", "draft", "final", "file", "page", "img",
}
TOKEN_RE = re.compile(r"[a-z]{3,}")


def _signal_names(file_name: str, ext: str, rel_posix: str) -> list[str]:
    """Classify one file into named signals (OCR sidecar, image asset, etc.)."""
    lower_name = file_name.lower()
    signals: list[str] = []
    if lower_name.endswith("_djvu.txt"):
        signals.append("ocr_sidecar_djvu_txt")
    if lower_name.endswith("_djvu.xml"):
        signals.append("ocr_sidecar_djvu_xml")
    if lower_name.endswith("_hocr.html"):
        signals.append("ocr_sidecar_hocr_html")
    if "spectrogram" in lower_name and ext in IMAGE_EXTENSIONS:
        signals.append("spectrogram_image")
    if "encrypted" in lower_name and ext == ".pdf":
        signals.append("encrypted_pdf_name")
    if "scan" in lower_name and ext in IMAGE_EXTENSIONS:
        signals.append("scan_named_image")
    if ".thumbs/" in rel_posix:
        signals.append("thumbnail_cache_asset")
    if ext in ARCHIVE_EXTENSIONS:
        signals.append("archive_container")
    if ext in DRAWING_EXTENSIONS:
        signals.append("drawing_or_diagram_asset")
    if ext in IMAGE_EXTENSIONS:
        signals.append("image_asset")
    return signals


def _tokenize_name(stem: str) -> list[str]:
    """Break a file stem into useful lowercase tokens, dropping stopwords."""
    tokens = TOKEN_RE.findall(stem.lower())
    return [token for token in tokens if token not in STOP_TOKENS]


def _folder_profile(
    folder: str,
    file_count: int,
    ext_counts: Counter,
    signal_counts: Counter,
    top_n: int,
) -> dict:
    """Summarize one top-level folder's extension mix and noise ratios."""
    image_count = sum(ext_counts[ext] for ext in IMAGE_EXTENSIONS)
    drawing_count = sum(ext_counts[ext] for ext in DRAWING_EXTENSIONS)
    archive_count = sum(ext_counts[ext] for ext in ARCHIVE_EXTENSIONS)
    sidecar_count = sum(
        signal_counts[key]
        for key in ("ocr_sidecar_djvu_txt", "ocr_sidecar_djvu_xml", "ocr_sidecar_hocr_html")
    )
    dominant = [
        {"extension": ext, "count": count}
        for ext, count in ext_counts.most_common(top_n)
    ]
    return {
        "folder": folder,
        "files": file_count,
        "dominant_extensions": dominant,
        "image_ratio": round(image_count / max(file_count, 1), 3),
        "drawing_ratio": round(drawing_count / max(file_count, 1), 3),
        "archive_ratio": round(archive_count / max(file_count, 1), 3),
        "ocr_sidecar_count": sidecar_count,
    }


def profile_source_tree(
    root: str | Path,
    *,
    top_n: int = 20,
    min_duplicate_dir_files: int = 3,
    max_files: int | None = None,
) -> dict:
    """Profile a source tree using metadata-only heuristics."""
    root_path = Path(root).resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"Source root not found: {root_path}")

    extension_counts: Counter[str] = Counter()
    top_level_counts: Counter[str] = Counter()
    signal_counts: Counter[str] = Counter()
    signal_examples: dict[str, list[str]] = defaultdict(list)
    token_counts: Counter[str] = Counter()
    dir_name_counts: Counter[str] = Counter()
    top_level_ext_counts: dict[str, Counter[str]] = defaultdict(Counter)
    top_level_signal_counts: dict[str, Counter[str]] = defaultdict(Counter)
    dir_manifests: dict[str, list[str]] = defaultdict(list)

    total_files = 0
    total_bytes = 0

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames.sort()
        filenames.sort()
        for dirname in dirnames:
            dir_name_counts[dirname.lower()] += 1

        for filename in filenames:
            if max_files is not None and total_files >= max_files:
                break

            file_path = Path(dirpath) / filename
            try:
                stat = file_path.stat()
            except OSError:
                continue

            rel = file_path.relative_to(root_path)
            rel_posix = rel.as_posix().lower()
            ext = file_path.suffix.lower() or "[no_ext]"
            top_level = rel.parts[0] if len(rel.parts) > 1 else "[root]"

            total_files += 1
            total_bytes += stat.st_size
            extension_counts[ext] += 1
            top_level_counts[top_level] += 1
            top_level_ext_counts[top_level][ext] += 1

            for signal in _signal_names(filename, ext, rel_posix):
                signal_counts[signal] += 1
                top_level_signal_counts[top_level][signal] += 1
                if len(signal_examples[signal]) < 5:
                    signal_examples[signal].append(rel.as_posix())

            for token in _tokenize_name(file_path.stem):
                token_counts[token] += 1

            parts = rel.parts
            for depth in range(1, len(parts)):
                folder_key = Path(*parts[:depth]).as_posix()
                relative_item = Path(*parts[depth:]).as_posix()
                manifest_item = f"{relative_item}|{ext}|{stat.st_size}"
                dir_manifests[folder_key].append(manifest_item)

        if max_files is not None and total_files >= max_files:
            break

    folder_profiles = [
        _folder_profile(
            folder=folder,
            file_count=count,
            ext_counts=top_level_ext_counts[folder],
            signal_counts=top_level_signal_counts[folder],
            top_n=min(5, top_n),
        )
        for folder, count in top_level_counts.most_common(top_n)
    ]

    repeated_dir_names = [
        {"directory_name": name, "count": count}
        for name, count in dir_name_counts.most_common(top_n)
        if count > 1
    ]

    duplicate_groups: dict[str, list[dict]] = defaultdict(list)
    for folder_key, items in dir_manifests.items():
        if len(items) < min_duplicate_dir_files:
            continue
        digest = hashlib.sha256("\n".join(sorted(items)).encode("utf-8")).hexdigest()[:16]
        duplicate_groups[digest].append(
            {
                "path": folder_key,
                "descendant_files": len(items),
            }
        )

    duplicate_folder_signatures = []
    for digest, group in duplicate_groups.items():
        if len(group) < 2:
            continue
        sample = sorted(group, key=lambda row: row["path"])
        duplicate_folder_signatures.append(
            {
                "signature": digest,
                "folder_count": len(group),
                "descendant_files": sample[0]["descendant_files"],
                "folders": [row["path"] for row in sample[:10]],
            }
        )
    duplicate_folder_signatures.sort(
        key=lambda row: (-row["folder_count"], -row["descendant_files"], row["signature"])
    )

    recommendations: list[str] = []
    ocr_sidecars = sum(
        signal_counts[key]
        for key in ("ocr_sidecar_djvu_txt", "ocr_sidecar_djvu_xml", "ocr_sidecar_hocr_html")
    )
    if ocr_sidecars:
        recommendations.append(
            "Promote OCR sidecar suffixes to explicit hash/defer rules so derivative text/XML/HTML does not compete with the parent document."
        )
    if signal_counts["encrypted_pdf_name"]:
        recommendations.append(
            "Track encrypted-PDF naming cues separately from generic PDF failures so they can be surfaced as a visible skip class."
        )
    if duplicate_folder_signatures:
        recommendations.append(
            "Add recursive folder-signature auditing for repeated extracted-archive trees before parse to avoid reprocessing duplicate bundles."
        )
    image_assets = signal_counts["image_asset"]
    if image_assets and image_assets > total_files * 0.2:
        recommendations.append(
            "Treat image-heavy families as a separate lane with stricter OCR gates or default defer settings."
        )
    if not recommendations:
        recommendations.append(
            "No strong skip/defer signals were detected from metadata alone; inspect parsed outputs and failure logs next."
        )

    return {
        "generated_at": datetime.now().isoformat(),
        "source_root_name": root_path.name,
        "total_files": total_files,
        "total_bytes": total_bytes,
        "extension_counts": dict(extension_counts.most_common()),
        "top_level_folder_counts": dict(top_level_counts.most_common()),
        "folder_profiles": folder_profiles,
        "signal_counts": dict(signal_counts.most_common()),
        "signal_examples": dict(signal_examples),
        "top_filename_tokens": [
            {"token": token, "count": count}
            for token, count in token_counts.most_common(top_n)
        ],
        "repeated_directory_names": repeated_dir_names,
        "duplicate_folder_signatures": duplicate_folder_signatures[:top_n],
        "recommendations": recommendations,
    }


def build_markdown_report(report: dict, *, top_n: int = 12) -> str:
    """Render a generic markdown report from a profile payload."""
    lines = [
        "# Source Corpus Profile",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Source root label: `{report['source_root_name']}`",
        f"- Files scanned: `{report['total_files']}`",
        f"- Total bytes: `{report['total_bytes']}`",
        "",
        "## Top Extensions",
        "",
        "| Extension | Count |",
        "|---|---:|",
    ]
    for ext, count in list(report["extension_counts"].items())[:top_n]:
        lines.append(f"| `{ext}` | {count} |")

    lines.extend([
        "",
        "## Top-Level Folders",
        "",
        "| Folder | Files |",
        "|---|---:|",
    ])
    for folder, count in list(report["top_level_folder_counts"].items())[:top_n]:
        lines.append(f"| `{folder}` | {count} |")

    lines.extend([
        "",
        "## Signal Families",
        "",
        "| Signal | Count | Example |",
        "|---|---:|---|",
    ])
    for signal, count in list(report["signal_counts"].items())[:top_n]:
        examples = report["signal_examples"].get(signal, [])
        example = examples[0] if examples else ""
        lines.append(f"| `{signal}` | {count} | `{example}` |")

    lines.extend([
        "",
        "## Duplicate Recursive Folder Signatures",
        "",
        "| Signature | Folder Count | Descendant Files | Example Folders |",
        "|---|---:|---:|---|",
    ])
    if report["duplicate_folder_signatures"]:
        for group in report["duplicate_folder_signatures"][:top_n]:
            example_folders = ", ".join(f"`{folder}`" for folder in group["folders"][:3])
            lines.append(
                f"| `{group['signature']}` | {group['folder_count']} | "
                f"{group['descendant_files']} | {example_folders} |"
            )
    else:
        lines.append("| `(none)` | 0 | 0 | |")

    lines.extend([
        "",
        "## Recommendations",
        "",
    ])
    for item in report["recommendations"]:
        lines.append(f"- {item}")

    return "\n".join(lines) + "\n"
