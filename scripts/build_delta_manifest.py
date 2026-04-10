"""
Build an explicit nightly delta manifest by comparing the source tree to the local mirror.

Usage:
  python scripts/build_delta_manifest.py --source-root "X:\\igs" --mirror-root "data/nightly_delta/source_mirror"
  python scripts/build_delta_manifest.py --source-root "X:\\igs" --mirror-root "data/nightly_delta/source_mirror" --output data/nightly_delta/manifests/manifest.json
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _sha256_file(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(131072)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()


def _iter_files(root: Path, max_files: int | None = None) -> Iterable[Path]:
    count = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        yield path
        count += 1
        if max_files and count >= max_files:
            break


def _matches_canary(relative_path: Path, patterns: list[str]) -> bool:
    rel_text = relative_path.as_posix().lower()
    name_text = relative_path.name.lower()
    lowered = [pattern.lower() for pattern in patterns]
    return any(
        fnmatch.fnmatch(rel_text, pattern) or fnmatch.fnmatch(name_text, pattern)
        for pattern in lowered
    )


def _classify_delta(source_file: Path, mirror_file: Path) -> tuple[str | None, str | None]:
    if not mirror_file.exists():
        return "new", None

    try:
        if source_file.stat().st_size != mirror_file.stat().st_size:
            return "changed", "size_mismatch"
    except OSError:
        return "changed", "stat_failed"

    source_hash = _sha256_file(source_file)
    mirror_hash = _sha256_file(mirror_file)
    if source_hash == mirror_hash:
        return None, source_hash
    return "changed", source_hash


def build_delta_manifest(
    source_root: Path | str,
    mirror_root: Path | str,
    *,
    canary_globs: list[str] | None = None,
    max_files: int | None = None,
) -> dict:
    source_root = Path(source_root).resolve()
    mirror_root = Path(mirror_root).resolve()
    canary_globs = canary_globs or ["*nightly_canary*", "*canary*"]

    if not source_root.exists():
        raise FileNotFoundError(f"Source root not found: {source_root}")

    created_at = datetime.now().isoformat(timespec="seconds")
    entries: list[dict] = []
    scanned_files = 0
    unchanged_files = 0
    new_files = 0
    changed_files = 0
    canary_matches = 0

    for source_file in _iter_files(source_root, max_files=max_files):
        scanned_files += 1
        relative_path = source_file.relative_to(source_root)
        mirror_file = mirror_root / relative_path
        reason, known_hash = _classify_delta(source_file, mirror_file)
        if reason is None:
            unchanged_files += 1
            continue

        is_canary = _matches_canary(relative_path, canary_globs)
        if is_canary:
            canary_matches += 1
        if reason == "new":
            new_files += 1
        else:
            changed_files += 1

        entry = {
            "relative_path": relative_path.as_posix(),
            "source_path": str(source_file),
            "mirror_path": str(mirror_file),
            "reason": reason,
            "size_bytes": source_file.stat().st_size,
            "canary": is_canary,
        }
        if known_hash:
            entry["source_sha256"] = known_hash
        entries.append(entry)

    return {
        "created_at": created_at,
        "source_root": str(source_root),
        "mirror_root": str(mirror_root),
        "canary_globs": canary_globs,
        "summary": {
            "scanned_files": scanned_files,
            "delta_files": len(entries),
            "new_files": new_files,
            "changed_files": changed_files,
            "unchanged_files": unchanged_files,
            "canary_matches": canary_matches,
            "max_files_applied": max_files,
        },
        "entries": entries,
    }


def write_manifest(manifest: dict, output_path: Path | str) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a nightly delta manifest")
    parser.add_argument("--source-root", required=True, help="Upstream source root to scan")
    parser.add_argument("--mirror-root", required=True, help="Local mirror root to compare against")
    parser.add_argument("--output", help="Write manifest JSON to this path")
    parser.add_argument(
        "--canary-glob",
        action="append",
        dest="canary_globs",
        help="Glob that marks a file as a canary hit. Repeat for multiple patterns.",
    )
    parser.add_argument("--max-files", type=int, help="Optional scan limit for proof runs")
    args = parser.parse_args()

    manifest = build_delta_manifest(
        args.source_root,
        args.mirror_root,
        canary_globs=args.canary_globs,
        max_files=args.max_files,
    )
    if args.output:
        output_path = write_manifest(manifest, args.output)
        print(f"Manifest written: {output_path}")

    summary = manifest["summary"]
    print(
        "Nightly delta manifest: "
        f"scanned={summary['scanned_files']} "
        f"delta={summary['delta_files']} "
        f"new={summary['new_files']} "
        f"changed={summary['changed_files']} "
        f"canary={summary['canary_matches']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
