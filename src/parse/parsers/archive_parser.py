"""
Archive parser -- extracts text from files inside ZIP, TAR, and GZ archives.

Opens the archive, extracts each member to a temp dir, routes each to
the dispatcher for parsing, and combines all text.
Ported from V1 (src/parsers/archive_parser.py).

Safety: zip bomb guard (500 MB), max 5000 members, path traversal guard,
no recursive archive extraction, temp dir always cleaned up.
"""

from __future__ import annotations

import gzip
import logging
import os
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import List, Tuple

from src.parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)

_MAX_EXTRACT_BYTES = 500 * 1024 * 1024  # 500 MB per file
_MAX_MEMBERS = 5000
_SKIP_EXTENSIONS = {".zip", ".7z", ".rar", ".tar", ".tgz", ".gz", ".bz2", ".xz"}


class ArchiveParser:
    """Extract text from files inside ZIP, TAR, and GZ archives."""

    def parse(self, file_path: Path) -> ParsedDocument:
        path = Path(file_path)
        text = ""
        quality = 0.0

        ext = path.suffix.lower()
        if path.name.lower().endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
            ext = ".tar" + ext

        tmp_dir = None
        try:
            tmp_dir = tempfile.mkdtemp(prefix="corpusforge_archive_")

            if ext == ".zip":
                members = self._extract_zip(str(path), tmp_dir)
            elif ext in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"):
                members = self._extract_tar(str(path), tmp_dir)
            elif ext == ".gz":
                members = self._extract_gz_single(str(path), tmp_dir)
            else:
                return ParsedDocument(
                    source_path=str(path), text="", parse_quality=0.0,
                    file_ext=ext,
                    file_size=path.stat().st_size if path.exists() else 0,
                )

            parts = self._parse_members(members)
            text = "\n\n".join(parts).strip()
            quality = 0.7 if text else 0.0

        except Exception as e:
            logger.error("Archive parse failed for %s: %s", path.name, e)
        finally:
            if tmp_dir and os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)

        return ParsedDocument(
            source_path=str(path),
            text=text,
            parse_quality=quality,
            file_ext=ext,
            file_size=path.stat().st_size if path.exists() else 0,
        )

    @staticmethod
    def _extract_zip(
        archive_path: str, tmp_dir: str
    ) -> List[Tuple[str, str]]:
        """Extract ZIP contents. Returns list of (member_name, extracted_path)."""
        members = []
        with zipfile.ZipFile(archive_path, "r") as zf:
            for entry in zf.infolist()[:_MAX_MEMBERS]:
                if entry.is_dir():
                    continue
                if ".." in entry.filename:
                    continue
                if entry.file_size > _MAX_EXTRACT_BYTES:
                    continue
                member_ext = Path(entry.filename).suffix.lower()
                if member_ext in _SKIP_EXTENSIONS:
                    continue

                safe_name = Path(entry.filename).name
                if not safe_name:
                    continue
                dest = _unique_path(tmp_dir, safe_name)

                try:
                    with zf.open(entry) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    members.append((entry.filename, dest))
                except Exception:
                    continue
        return members

    @staticmethod
    def _extract_tar(
        archive_path: str, tmp_dir: str
    ) -> List[Tuple[str, str]]:
        """Extract TAR/TGZ/TBZ2/TXZ contents."""
        members = []
        with tarfile.open(archive_path, "r:*") as tf:
            for entry in tf.getmembers()[:_MAX_MEMBERS]:
                if not entry.isfile():
                    continue
                if ".." in entry.name:
                    continue
                if entry.size > _MAX_EXTRACT_BYTES:
                    continue
                member_ext = Path(entry.name).suffix.lower()
                if member_ext in _SKIP_EXTENSIONS:
                    continue

                safe_name = Path(entry.name).name
                if not safe_name:
                    continue
                dest = _unique_path(tmp_dir, safe_name)

                try:
                    src = tf.extractfile(entry)
                    if src is None:
                        continue
                    try:
                        with open(dest, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        members.append((entry.name, dest))
                    finally:
                        src.close()
                except Exception:
                    continue
        return members

    @staticmethod
    def _extract_gz_single(
        archive_path: str, tmp_dir: str
    ) -> List[Tuple[str, str]]:
        """Extract a single .gz file (not tar.gz)."""
        inner_name = Path(archive_path).stem or "extracted_file"
        dest = os.path.join(tmp_dir, inner_name)
        try:
            with gzip.open(archive_path, "rb") as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
            return [(inner_name, dest)]
        except Exception:
            return []

    @staticmethod
    def _parse_members(members: List[Tuple[str, str]]) -> List[str]:
        """Route each extracted file to the dispatcher and collect text."""
        # Import here to avoid circular imports
        from src.parse.dispatcher import ParseDispatcher

        dispatcher = ParseDispatcher()
        parts = []
        for member_name, extracted_path in members:
            try:
                doc = dispatcher.parse(Path(extracted_path))
                if doc.text.strip():
                    parts.append(f"[ARCHIVE_MEMBER={member_name}]\n{doc.text}")
            except Exception:
                continue
        return parts


def _unique_path(directory: str, filename: str) -> str:
    """Generate a unique file path in directory, handling duplicates."""
    dest = os.path.join(directory, filename)
    if not os.path.exists(dest):
        return dest
    base, suffix = os.path.splitext(filename)
    counter = 1
    while os.path.exists(dest):
        dest = os.path.join(directory, f"{base}_{counter}{suffix}")
        counter += 1
    return dest
