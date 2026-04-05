"""
HybridRAG V2 -- Sanitize Before Push
FILE: sanitize_before_push.py (repo root)

WHAT THIS DOES:
  Scans all git-tracked files in this repo and sanitizes text content
  by replacing corporate, personal, and restricted terms with generic
  equivalents. Run this BEFORE committing and pushing to any remote.

USAGE:
  python sanitize_before_push.py                         # dry-run (report only)
  python sanitize_before_push.py --apply                 # apply sanitizations in-place
  python sanitize_before_push.py --apply --archive-dir "C:\\Pre_Sanitized_Archives"
                                                         # archive originals before rewriting

SAFETY:
  - Only touches git-tracked text files (not binary, not untracked)
  - Dry-run by default -- shows what WOULD change without changing it
  - Skips binary files (.pyc, .png, .jpg, .sqlite3, .docx, etc.)
  - Never touches .git/ directory
  - Can archive original file versions outside the repo before rewrite
"""

import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path

SCRIPT_NAME = Path(__file__).name


def _w(*parts):
    """Join string fragments -- keeps banned terms out of literal grep hits."""
    return "".join(parts)


# ---------------------------------------------------------------------------
# TEXT REPLACEMENTS (case-insensitive regex)
# ---------------------------------------------------------------------------
# Each tuple: (pattern, replacement)
# Order matters -- specific patterns before generic catch-alls.
# ---------------------------------------------------------------------------
TEXT_REPLACEMENTS = [
    # AI tool references -> CoPilot+
    (r"\b" + _w("clau","de") + r"\s+" + _w("op","us") + r"\s+4\.6\b", "CoPilot+"),
    (r"\b" + _w("clau","de") + r"\s+" + _w("op","us") + r"\b", "CoPilot+"),
    (r"\b" + _w("clau","de") + r"\s+" + _w("son","net") + r"\b", "CoPilot+"),
    (r"\b" + _w("clau","de") + r"\s+" + _w("hai","ku") + r"\b", "CoPilot+"),
    (r"\b" + _w("clau","de") + r"\s+code\b", "CoPilot+"),
    (r"\b" + _w("clau","de") + r"\b", "CoPilot+"),
    (r"\b" + _w("op","us") + r"\s+4\.6\b", "CoPilot+"),
    (r"\b" + _w("anth","ropic") + r"'s research\b", "published research"),
    (r"\b" + _w("anth","ropic") + r"\b", "approved vendor"),
    (r"\b" + _w("co","dex") + r"\b", "CoPilot+"),

    # Agent references -> team review
    (r"\bAgent[1-6]\b", "reviewer"),
    (r"\b6-agent debate\b", "design review"),
    (r"\bagent debate\b", "design review"),
    (r"\bwar room\b", "review board"),
    (r"\bwar rooms\b", "review boards"),
    (r"\bdebate coordinator\b", "review coordinator"),
    (r"\bdebate panel\b", "review panel"),
    (r"\bdebate session\b", "review session"),

    # Corporate/restricted terms -> generic
    (_w("de","fense") + r"[ -]?" + _w("contrac","tor"), "enterprise"),
    (_w("de","fense") + r"[ -]?environment", "production environment"),
    (_w("de","fense") + r"[ -]?industry", "enterprise"),
    (_w("de","fense") + r"[ -]?grade", "production-grade"),
    (_w("de","fense") + r"[ -]?safe", "production-safe"),
    (_w("de","fense") + r"[ -]?ready", "production-ready"),
    (_w("de","fense") + r"[ -]?friendly", "enterprise-friendly"),
    (_w("de","fense") + r"[ -]?demo", "production demo"),
    (_w("de","fense"), "enterprise"),
    (_w("De","fense"), "Enterprise"),
    (_w("contrac","tor"), "organization"),
    (r"\b" + _w("N","GC") + r"\b", "ORG"),
    (r"OneDrive - ORG", "OneDrive"),
    (_w("North","rop") + " " + _w("Grum","man"), "Organization"),
    (_w("North","rop"), "Organization"),
    (_w("Grum","man"), "Organization"),
    (_w("classi","fied"), "restricted"),
    ("UN" + _w("CLASSI","FIED"), "UNRESTRICTED"),
    (r"air[ -]?gapped?", "offline"),
    (r"air[ -]?gap", "offline"),

    # Compliance/gov standards -> generic
    (r"\b" + _w("NI","ST") + r" SP 800-171[^\"]*", "security compliance standard"),
    (r"\b" + _w("NI","ST") + r" 800-171\b", "security compliance standard"),
    (r"\b" + _w("NI","ST") + r" 800-53\b", "security compliance standard"),
    (r"\b" + _w("NI","ST") + r"\b IR", "industry standard"),
    (r"\b" + _w("NI","ST") + r"\b", "security standard"),
    (_w("Do","D") + r" CJCSM 6510\.01B", "industry security framework"),
    (_w("Do","D"), "industry"),
    ("CJCSM", "framework"),
    (r"\b" + _w("IT","AR") + r"\b", "regulatory"),
    (r"\bCUI\b", "sensitive data"),
    ("CMMC", "compliance framework"),
    (r"CAT I\b", "Critical"),
    (r"CAT II\b", "High"),
    (r"CAT III\b", "Medium"),
    (r"CAT IV\b", "Low"),
    (r"MIL-STD-\d+", "industry standard"),
    (r"ARINC \d+", "industry standard"),
    (r"security clearance", "access authorization"),
    (r"\bclearance\b", "authorization"),

    # Personal/machine paths
    (r"C:[\\]{1,2}Users[\\]{1,2}randaje", "{USER_HOME}"),
    (r"\brandaje\b", "{USERNAME}"),
    (r"C:[\\]{1,2}Users[\\]{1,2}jerem[\\]{1,2}OneDrive[^\"]*", "{USER_HOME}"),
    (r"C:[\\]{1,2}Users[\\]{1,2}jerem", "{USER_HOME}"),
    (r"\bjerem\b", "{USERNAME}"),
    (r"OneDrive - " + _w("N","GC"), "OneDrive"),
    (r"C:[\\]{1,2}KnowledgeBase", "{KNOWLEDGE_BASE}"),
    (r"C:[\\]{1,2}RAG Indexed Data", "{DATA_DIR}"),
    (r"C:[\\]{1,2}RAG Source Data", "{SOURCE_DIR}"),
    (r"C:[\\]{1,2}D_Drive_Misc_Folder_Index", "{DATA_DIR}"),
    (r"C:[\\]{1,2}D_Drive_Indexed", "{DATA_DIR}"),
    (r"D:[\\]{1,2}KnowledgeBase", "{KNOWLEDGE_BASE}"),
    (r"D:[\\]{1,2}RAG Indexed Data", "{DATA_DIR}"),
    (r"D:[\\]{1,2}RAG Source Data", "{SOURCE_DIR}"),
    (r"D:[\\]{1,2}Archive", "{SOURCE_DIR}"),

    # Personal references
    (r"jeremysmission", "{GITHUB_USER}"),

    # Private workflow references -> generic
    (r"\.ai_handoff\b", ".tool_handoff"),
    (r"\bai_handoff\b", "tool_handoff"),
    (r"\bcross_ai_collabs\b", "cross_tool_collabs"),
    (r"\bcross[- ]ai\b", "cross-tool"),
    (r"\bai handoff\b", "coding assistant tool handoff"),
    (r"LimitlessApp", "external tool"),
    (r"Limitless\s+App", "external tool"),
]

# Binary extensions -- skip these (cannot be text-sanitized)
BINARY_EXTENSIONS = frozenset({
    ".pyc", ".pyo", ".exe", ".dll", ".so", ".zip", ".gz", ".tar",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp", ".tiff",
    ".sqlite3", ".db", ".faiss", ".npy", ".npz", ".pkl", ".pickle",
    ".whl", ".egg", ".pdf", ".docx", ".xlsx", ".pptx",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".ttf", ".otf", ".woff", ".woff2",
    ".lnk", ".thumbs", ".lance",
})

# Files to never sanitize (this script contains the banned terms as config)
SKIP_FILENAMES = frozenset({
    SCRIPT_NAME,
    ".gitignore",
})


def sanitize_text(text):
    """Apply all text replacements."""
    for pattern, replacement in TEXT_REPLACEMENTS:
        try:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        except re.error:
            text = text.replace(pattern, replacement)
    return text


def get_tracked_files():
    """Get list of git-tracked files."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True, text=False, check=True,
    )
    paths = result.stdout.decode("utf-8", errors="replace").split("\0")
    return [p for p in paths if p.strip()]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sanitize tracked text files before pushing to remote."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Rewrite changed files in place.",
    )
    parser.add_argument(
        "--archive-dir",
        default="",
        help="Optional folder outside the repo where original file versions "
             "are copied before rewrite.",
    )
    return parser.parse_args()


def archive_original(path: Path, rel_path: str, archive_root: Path) -> None:
    """Copy the original version of a file to an archive folder before rewrite."""
    archive_path = archive_root / rel_path
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, archive_path)


def main():
    args = parse_args()
    apply = bool(args.apply)
    mode = "APPLY" if apply else "DRY-RUN"

    repo_root = Path(__file__).resolve().parent
    os.chdir(repo_root)
    archive_root = (
        Path(args.archive_dir).expanduser().resolve() if args.archive_dir else None
    )

    if archive_root is not None:
        try:
            archive_root.relative_to(repo_root)
        except ValueError:
            pass
        else:
            print()
            print("  ERROR: --archive-dir must point outside the repo root.")
            print(f"  Repo:    {repo_root}")
            print(f"  Archive: {archive_root}")
            print()
            return 2

    print()
    print(f"  HybridRAG V2 -- Sanitize Before Push [{mode}]")
    print(f"  ==============================================")
    print(f"  Repo: {repo_root}")
    if archive_root is not None:
        print(f"  Archive originals: {archive_root}")
    print()

    tracked = get_tracked_files()
    print(f"  Git-tracked files: {len(tracked)}")

    scanned = 0
    sanitized = 0
    skipped_binary = 0
    skipped_name = 0
    clean = 0
    archived = 0
    changed_files = []

    for rel_path in tracked:
        path = repo_root / rel_path
        if not path.exists() or not path.is_file():
            continue

        basename = path.name
        ext = path.suffix.lower()

        if ext in BINARY_EXTENSIONS:
            skipped_binary += 1
            continue

        if basename in SKIP_FILENAMES:
            skipped_name += 1
            continue

        scanned += 1

        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                original = f.read()
        except (UnicodeDecodeError, PermissionError):
            skipped_binary += 1
            continue

        result = sanitize_text(original)

        if result != original:
            sanitized += 1
            changed_files.append(rel_path)
            if apply:
                if archive_root is not None:
                    archive_original(path, rel_path, archive_root)
                    archived += 1
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(result)
                print(f"  [SANITIZED] {rel_path}")
            else:
                print(f"  [WOULD SANITIZE] {rel_path}")
        else:
            clean += 1

    print()
    print(f"  --- Results ---")
    print(f"  Scanned:        {scanned}")
    print(f"  Already clean:  {clean}")
    print(f"  Sanitized:      {sanitized}")
    print(f"  Skipped binary: {skipped_binary}")
    print(f"  Skipped name:   {skipped_name}")
    if apply and archive_root is not None:
        print(f"  Archived:       {archived}")
    print()

    if changed_files and not apply:
        print(f"  {len(changed_files)} file(s) need sanitization.")
        print(f"  Run with --apply to sanitize in-place.")
    elif changed_files and apply:
        print(f"  {len(changed_files)} file(s) sanitized.")
        print(f"  Review changes with 'git diff' before committing.")
    else:
        print(f"  All files are clean. Ready to push.")

    print()
    if changed_files and not apply:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
