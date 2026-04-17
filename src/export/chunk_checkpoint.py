"""
Durable chunk checkpointing for long-running Forge pipeline runs.

Plain-English role
------------------
Cross-cutting crash safety for stages 4-7 of the pipeline.

As soon as a file is parsed and chunked, this module writes the
resulting chunks (and the document text) into an append-only
``_checkpoint_active`` folder inside the export directory. If the run
crashes or the operator hits stop before export, Forge can resume on
the next run and skip any files that were already parsed and chunked.

The checkpoint is deleted once the final export is written
successfully. A ``checkpoint_manifest.json`` file records the current
stage status so an operator can see where a partial run stopped.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.parse.parsers.txt_parser import ParsedDocument


@dataclass
class CheckpointResume:
    """Loaded checkpoint state for a resumed run."""

    resumed: bool
    chunks: list[dict]
    docs: list[ParsedDocument]
    source_paths: list[str]
    remaining_files: list[Path]


class ChunkCheckpoint:
    """Append-only JSONL checkpoint for parsed sources and chunks.

    One instance lives per pipeline run and owns the
    ``_checkpoint_active`` folder inside the export directory. It
    handles begin/resume, per-document append, periodic fsync, and
    cleanup after a successful export.
    """

    _SYNC_EVERY_DOCS = 10
    _SYNC_EVERY_SECONDS = 2.0

    def __init__(self, output_dir: str):
        """Remember where the checkpoint folder should live on disk."""
        self.output_dir = Path(output_dir)
        self.root = self.output_dir / "_checkpoint_active"
        self.manifest_path = self.root / "checkpoint_manifest.json"
        self.chunks_path = self.root / "chunks.partial.jsonl"
        self.docs_path = self.root / "docs.partial.jsonl"
        self.sources_path = self.root / "parsed_sources.txt"
        self._checkpointed_files = 0
        self._checkpointed_chunks = 0
        self._signature = ""
        self._last_sync = time.time()
        self._docs_since_sync = 0

    @staticmethod
    def _normalize_path(value: Path | str) -> str:
        """Return path string with forward slashes for cross-platform comparison."""
        return str(value).replace("\\", "/")

    def begin_run(
        self,
        signature: str,
        parse_files: list[Path],
        *,
        file_hashes: dict[str, str] | None = None,
        resume_enabled: bool,
    ) -> CheckpointResume:
        """Start a new checkpoint or resume a compatible active one."""
        self._signature = signature
        current_norms = {self._normalize_path(p): p for p in parse_files}
        manifest = self._load_manifest()

        if (
            resume_enabled
            and manifest is not None
            and manifest.get("signature") == signature
            and self.chunks_path.exists()
            and self.docs_path.exists()
            and self.sources_path.exists()
        ):
            docs = self._load_docs(current_norms, file_hashes or {})
            resumed_norms = {self._normalize_path(doc.source_path) for doc in docs}
            chunks = self._load_chunks(resumed_norms)
            chunked_norms = {
                self._normalize_path(chunk.get("source_path", ""))
                for chunk in chunks
                if chunk.get("source_path")
            }
            docs = [
                doc for doc in docs
                if self._normalize_path(doc.source_path) in chunked_norms
            ]
            source_paths = [doc.source_path for doc in docs]
            resumed_norms = {self._normalize_path(path) for path in source_paths}
            chunks = [
                chunk for chunk in chunks
                if self._normalize_path(chunk.get("source_path", "")) in resumed_norms
            ]
            remaining_files = [
                p for p in parse_files
                if self._normalize_path(p) not in resumed_norms
            ]
            self._checkpointed_files = len(source_paths)
            self._checkpointed_chunks = len(chunks)
            self._write_manifest(status="resumed")
            return CheckpointResume(
                resumed=bool(source_paths or chunks),
                chunks=chunks,
                docs=docs,
                source_paths=source_paths,
                remaining_files=remaining_files,
            )

        self.reset(signature)
        return CheckpointResume(
            resumed=False,
            chunks=[],
            docs=[],
            source_paths=[],
            remaining_files=parse_files,
        )

    def append_document(
        self,
        doc: ParsedDocument,
        chunks: list[dict],
        *,
        content_hash: str,
    ) -> None:
        """Persist one completed parsed document and its chunks."""
        self.root.mkdir(parents=True, exist_ok=True)

        doc_payload = {
            "source_path": self._normalize_path(doc.source_path),
            "text": doc.text,
            "parse_quality": doc.parse_quality,
            "file_ext": doc.file_ext,
            "file_size": doc.file_size,
            "content_hash": content_hash,
        }
        with open(self.docs_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(doc_payload, ensure_ascii=False) + "\n")
            f.flush()

        with open(self.chunks_path, "a", encoding="utf-8", newline="\n") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            f.flush()

        with open(self.sources_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(f"{self._normalize_path(doc.source_path)}\n")
            f.flush()

        self._checkpointed_files += 1
        self._checkpointed_chunks += len(chunks)
        self._docs_since_sync += 1
        if self._should_sync():
            self.sync(status="parsing")

    def set_status(self, status: str) -> None:
        """Update the active checkpoint stage status."""
        if self.root.exists():
            self.sync(status=status)

    def clear(self) -> None:
        """Remove the active checkpoint after a successful export."""
        self._last_sync = time.time()
        self._docs_since_sync = 0
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)
        self._checkpointed_files = 0
        self._checkpointed_chunks = 0
        self._signature = ""

    def reset(self, signature: str) -> None:
        """Replace any incompatible checkpoint with a fresh active one."""
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)
        self._checkpointed_files = 0
        self._checkpointed_chunks = 0
        self._signature = signature
        self._last_sync = time.time()
        self._docs_since_sync = 0
        self.chunks_path.write_text("", encoding="utf-8", newline="\n")
        self.docs_path.write_text("", encoding="utf-8", newline="\n")
        self.sources_path.write_text("", encoding="utf-8", newline="\n")
        self._write_manifest(status="parsing")

    def sync(self, *, status: str = "parsing") -> None:
        """Force an on-disk sync of the active checkpoint files."""
        if not self.root.exists():
            return
        self._fsync_path(self.docs_path)
        self._fsync_path(self.sources_path)
        self._fsync_path(self.chunks_path)
        self._write_manifest(status=status)
        self._last_sync = time.time()
        self._docs_since_sync = 0

    def _load_manifest(self) -> dict | None:
        """Read the checkpoint manifest JSON from disk, or None if missing."""
        if not self.manifest_path.exists():
            return None
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _load_docs(
        self,
        current_norms: dict[str, Path],
        current_hashes: dict[str, str],
    ) -> list[ParsedDocument]:
        """Rehydrate parsed documents from the checkpoint that still match today's files."""
        docs: list[ParsedDocument] = []
        for payload in self._iter_jsonl(self.docs_path):
            norm = self._normalize_path(payload.get("source_path", ""))
            if not norm or norm not in current_norms:
                continue
            expected_hash = payload.get("content_hash")
            current_hash = current_hashes.get(norm)
            if expected_hash and current_hash and current_hash != expected_hash:
                continue
            docs.append(
                ParsedDocument(
                    source_path=norm,
                    text=payload.get("text", ""),
                    parse_quality=float(payload.get("parse_quality", 0.0)),
                    file_ext=payload.get("file_ext", ""),
                    file_size=int(payload.get("file_size", 0)),
                )
            )
        return docs

    def _load_chunks(self, resumed_norms: set[str]) -> list[dict]:
        """Replay chunks whose source file is part of the resumed set."""
        chunks: list[dict] = []
        for chunk in self._iter_jsonl(self.chunks_path):
            if self._normalize_path(chunk.get("source_path", "")) in resumed_norms:
                chunks.append(chunk)
        return chunks

    def _iter_jsonl(self, path: Path):
        """Yield one JSON record per line, tolerant of a half-written tail."""
        if not path.exists():
            return
        with open(path, encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    yield json.loads(raw)
                except json.JSONDecodeError:
                    # Crash-safe replay: ignore a truncated tail line.
                    continue

    def _write_manifest(self, *, status: str) -> None:
        """Atomically write the checkpoint manifest describing current stage status."""
        payload = {
            "schema_version": 1,
            "signature": self._signature,
            "status": status,
            "checkpoint_dir": str(self.root.resolve()),
            "docs_path": str(self.docs_path.resolve()),
            "checkpointed_files": self._checkpointed_files,
            "checkpointed_chunks": self._checkpointed_chunks,
            "updated_at": datetime.now().isoformat(),
        }
        tmp = self.manifest_path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.manifest_path)

    def _should_sync(self) -> bool:
        """Decide whether enough docs or time have passed to force an fsync."""
        return (
            self._docs_since_sync >= self._SYNC_EVERY_DOCS
            or (time.time() - self._last_sync) >= self._SYNC_EVERY_SECONDS
        )

    def _fsync_path(self, path: Path) -> None:
        """Force the OS to flush file contents to disk for durability."""
        if not path.exists():
            return
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.flush()
            os.fsync(f.fileno())
