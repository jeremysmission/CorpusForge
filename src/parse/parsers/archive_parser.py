"""
Archive parser -- reads files packaged inside ZIP, TAR, or GZ archives.

Plain English: operators frequently drop zipped bundles of documents
into the corpus. This parser opens the archive, unpacks each member
into a scratch folder, hands each unpacked file back to the main
dispatcher (so a .pdf inside a zip is still parsed by the PDF parser),
and combines all the extracted text into one document. Each member's
block is tagged ``[ARCHIVE_MEMBER=<name>]`` so reviewers can trace
chunks back to the original file inside the zip.

Safety rails (important for operators to understand):
  * Zip-bomb guard: any single member larger than 500 MB is skipped.
  * Max 5000 members per archive.
  * Path-traversal guard: members with ``..`` in their name are skipped.
  * Nested archives are NOT re-extracted (no recursion loop).
  * The scratch folder is always cleaned up, even on crash.

Defer policy: if the archive itself or any member name matches the
"deferred" list in config/config.yaml (e.g., .SAO.zip bundles during
early ingest phases), it is skipped at extraction time.

Ported from V1 (src/parsers/archive_parser.py).
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

_MAX_EXTRACT_BYTES = 500 * 1024 * 1024  # 500 MB per file (zip-bomb guard)
_MAX_MEMBERS = 5000  # safety cap on archive member count
# Nested archives are not re-extracted to prevent recursion loops
_SKIP_EXTENSIONS = {".zip", ".7z", ".rar", ".tar", ".tgz", ".gz", ".bz2", ".xz"}


class ArchiveParser:
    """Extract text from files inside ZIP, TAR, and GZ archives.

    Defer policy (Sprint 6.6 fix):
        Both the archive's own basename and each extracted member's
        original basename are checked against ``deferred_exts``. Matching
        is segment-based: the lowercased basename is split on ``.`` and
        any segment equal to a deferred token (without the leading dot)
        causes the entry to be deferred.

        Production examples this catches:
            * archive ``AS00Q_2015309093000.SAO.zip``  → token ``sao`` is
              a dot-segment → entire archive is deferred, no extraction.
            * member ``AS00Q_2015309093000.SAO.XML``   → token ``sao`` is
              a dot-segment → member is dropped at extract time.

        Lookalikes that must NOT match:
            * ``report_sao.log``  → segments ['report_sao','log']
            * ``bigsao.txt``      → segments ['bigsao','txt']
    """

    def __init__(self, deferred_exts: set[str] | None = None) -> None:
        # Normalize: store both the dotted form (e.g. ".sao") and the
        # bare token form (e.g. "sao") so segment matching is cheap.
        normalized: set[str] = set()
        tokens: set[str] = set()
        for ext in deferred_exts or ():
            ext = ext.lower()
            if not ext.startswith("."):
                ext = f".{ext}"
            normalized.add(ext)
            tokens.add(ext.lstrip("."))
        self._deferred_exts = normalized
        self._deferred_tokens = tokens

    def _is_name_deferred(self, name: str) -> bool:
        """Return True if any dot-segment of the basename is a deferred token.

        Used for both the archive's own name and each member's name.
        Segment-based on purpose: ``foo.SAO.XML`` matches ``sao`` but
        ``report_sao.log`` does not (because ``report_sao`` is a single
        segment, not equal to ``sao``).
        """
        if not self._deferred_tokens:
            return False
        base = Path(name).name.lower()
        segments = base.split(".")
        return any(seg in self._deferred_tokens for seg in segments)

    def parse(self, file_path: Path) -> ParsedDocument:
        """Open an archive, parse each file inside, and return the combined text."""
        path = Path(file_path)
        text = ""
        quality = 0.0

        ext = path.suffix.lower()
        if path.name.lower().endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
            ext = ".tar" + ext

        # Whole-archive defer: if the archive's own basename contains a
        # deferred dot-segment (e.g. ``AS00Q_2015309093000.SAO.zip``),
        # do not extract anything. Returning an empty doc with quality 0
        # mirrors how a deferred top-level file would look downstream.
        if self._is_name_deferred(path.name):
            logger.debug(
                "Whole archive deferred by name policy: %s", path.name,
            )
            return ParsedDocument(
                source_path=str(path),
                text="",
                parse_quality=0.0,
                file_ext=ext,
                file_size=path.stat().st_size if path.exists() else 0,
            )

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

    def _extract_zip(
        self, archive_path: str, tmp_dir: str
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
                # Honor configured defer policy for archive members.
                if self._is_name_deferred(entry.filename):
                    logger.debug(
                        "Archive member deferred by policy: %s (in %s)",
                        entry.filename, archive_path,
                    )
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

    def _extract_tar(
        self, archive_path: str, tmp_dir: str
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
                # Honor configured defer policy for archive members.
                if self._is_name_deferred(entry.name):
                    logger.debug(
                        "Archive member deferred by policy: %s (in %s)",
                        entry.name, archive_path,
                    )
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
