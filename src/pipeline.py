"""
Pipeline orchestrator — parallel parse → GPU batch embed → export.

Architecture ported from V1 (HybridRAG3 src/core/indexer.py):
  - ThreadPoolExecutor(N workers) for parallel file parsing
  - Prefetch 2x workers to keep the ready queue saturated
  - Main thread drains parsed results → chunk → GPU batch embed
  - Stale future watchdog kills hung parsers
  - Token-budget batching + OOM backoff in embedder

V1 achieved 60-200 chunks/sec sustained with this pattern.
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple

import numpy as np

from .config.schema import ForgeConfig
from .chunk.chunker import Chunker
from .chunk.chunk_ids import make_chunk_id
from .embed.embedder import Embedder
from .enrichment.contextual_enricher import ContextualEnricher, EnricherConfig
from .export.packager import Packager
from .download.hasher import Hasher
from .download.deduplicator import Deduplicator
from .skip.skip_manager import SkipManager
from .parse.dispatcher import ParseDispatcher, get_supported_extensions
from .parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


@dataclass
class RunStats:
    """Tracks pipeline run statistics."""

    files_found: int = 0
    files_after_dedup: int = 0
    files_skipped: int = 0
    files_parsed: int = 0
    files_failed: int = 0
    skipped_unchanged: int = 0
    skipped_duplicate: int = 0
    chunks_created: int = 0
    chunks_enriched: int = 0
    vectors_created: int = 0
    elapsed_seconds: float = 0.0
    skip_reasons: str = ""
    errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "files_found": self.files_found,
            "files_after_dedup": self.files_after_dedup,
            "files_skipped": self.files_skipped,
            "files_parsed": self.files_parsed,
            "files_failed": self.files_failed,
            "skipped_unchanged": self.skipped_unchanged,
            "skipped_duplicate": self.skipped_duplicate,
            "chunks_created": self.chunks_created,
            "chunks_enriched": self.chunks_enriched,
            "vectors_created": self.vectors_created,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "error_count": len(self.errors),
            "skip_reasons": self.skip_reasons,
        }


class Pipeline:
    """
    Orchestrates all pipeline stages with parallel parsing.

    Architecture:
      1. Hash & dedup (sequential, fast)
      2. Skip check (sequential, fast)
      3. Parallel parse: N worker threads parse files concurrently
      4. Main thread: chunk → enrich → GPU batch embed → export
      5. Stale future watchdog prevents hung parsers from blocking pipeline
    """

    def __init__(self, config: ForgeConfig):
        self.config = config
        self.workers = config.pipeline.workers
        self.stale_timeout = config.pipeline.stale_future_timeout
        self.embed_flush_batch = config.pipeline.embed_flush_batch

        self.hasher = Hasher(config.paths.state_db)
        self.deduplicator = Deduplicator(self.hasher)
        self.skip_manager = SkipManager(config.paths.skip_list, self.hasher)
        self.dispatcher = ParseDispatcher(
            timeout_seconds=config.parse.timeout_seconds,
            max_chars=config.parse.max_chars_per_file,
        )
        self.chunker = Chunker(
            chunk_size=config.chunk.size,
            overlap=config.chunk.overlap,
            max_heading_len=config.chunk.max_heading_len,
        )
        self.enricher = ContextualEnricher(
            config=EnricherConfig(
                enabled=config.enrich.enabled,
                ollama_url=config.enrich.ollama_url,
                model=config.enrich.model,
                max_chunk_chars=config.enrich.max_chunk_chars,
            )
        )
        self.embedder = Embedder(
            model_name=config.embed.model_name,
            dim=config.embed.dim,
            device=config.embed.device,
            max_batch_tokens=config.embed.max_batch_tokens,
            dtype=config.embed.dtype,
        )
        self.packager = Packager(output_dir=config.paths.output_dir)

    def run(
        self,
        input_files: list[Path],
        on_file_start: callable | None = None,
    ) -> RunStats:
        """
        Run the pipeline on a list of input files.

        Args:
            input_files: List of file paths to process.
            on_file_start: Optional callback(file_path, file_index, total_files)
                called before each file is parsed. Used by GUI for progress.

        Returns RunStats with processing results.
        """
        self._on_file_start = on_file_start
        stats = RunStats()
        start_time = time.time()

        stats.files_found = len(input_files)

        # Stage 2: Hash & dedup
        if self.config.pipeline.full_reindex:
            work_files = input_files
        else:
            work_files = self.deduplicator.filter_new_and_changed(input_files)
            stats.skipped_unchanged = self.deduplicator.skipped_unchanged
            stats.skipped_duplicate = self.deduplicator.skipped_duplicate
        stats.files_after_dedup = len(work_files)

        if not work_files:
            logger.info("No new or changed files to process.")
            stats.elapsed_seconds = time.time() - start_time
            return stats

        # Stage 2b: Skip check (hash but don't parse)
        parse_files = []
        for fp in work_files:
            try:
                fsize = fp.stat().st_size
            except OSError:
                fsize = 0
            skip, reason = self.skip_manager.should_skip(fp, fsize)
            if skip:
                self.skip_manager.record_skip(fp, reason)
                stats.files_skipped += 1
            else:
                parse_files.append(fp)

        if not parse_files:
            logger.info("All files skipped -- nothing to parse.")
            stats.skip_reasons = self.skip_manager.get_reason_summary()
            self._finalize_skip(stats, start_time)
            return stats

        # Stage 3+4+5+6: Parallel parse → chunk → enrich → embed
        if self.workers > 1 and len(parse_files) > 1:
            all_chunks, all_docs = self._parallel_parse_and_chunk(parse_files, stats)
        else:
            all_docs = self._parse_files(parse_files, stats)
            all_chunks = self._chunk_documents(all_docs, stats)

        if not all_chunks:
            logger.warning("No chunks produced -- nothing to embed or export.")
            stats.elapsed_seconds = time.time() - start_time
            return stats

        # Stage 5: Contextual enrichment (phi4:14B via Ollama)
        doc_texts = {doc.source_path: doc.text for doc in all_docs}
        all_chunks = self.enricher.enrich_chunks(all_chunks, doc_texts)
        stats.chunks_enriched = sum(
            1 for c in all_chunks if c.get("enriched_text") is not None
        )

        # Stage 6: Embed (GPU batch with token-budget packing + OOM backoff)
        vectors = self._embed_chunks(all_chunks, stats)

        # Stage 8: Export
        export_dir = self.packager.export(
            chunks=all_chunks,
            vectors=vectors,
            entities=[],
            stats=stats.to_dict(),
        )
        logger.info("Export written to: %s", export_dir)

        # Write skip manifest alongside export
        if self.skip_manager.skip_count > 0:
            self.skip_manager.write_skip_manifest(export_dir)

        stats.skip_reasons = self.skip_manager.get_reason_summary()
        stats.elapsed_seconds = time.time() - start_time

        # Pipeline summary
        rate = stats.chunks_created / max(stats.elapsed_seconds, 0.01)
        logger.info(
            "Pipeline summary: %d files hashed, %d parsed, %d skipped, "
            "%d chunks at %.1f chunks/sec (reasons: %s)",
            stats.files_after_dedup, stats.files_parsed, stats.files_skipped,
            stats.chunks_created, rate, stats.skip_reasons or "none",
        )

        return stats

    # ------------------------------------------------------------------
    # Parallel parse pipeline (ported from V1 indexer.py)
    # ------------------------------------------------------------------

    def _parallel_parse_and_chunk(
        self, files: list[Path], stats: RunStats
    ) -> tuple[list[dict], list[ParsedDocument]]:
        """
        Parse files in parallel using ThreadPoolExecutor.

        Worker threads parse files concurrently. Main thread collects
        results and chunks them. Keeps GPU embed queue fed.

        V1 pattern: prefetch 2x workers, drain completed futures,
        stale future watchdog kills hung parsers.
        """
        workers = min(self.workers, len(files))
        prefetch = workers * 2
        total = len(files)

        logger.info(
            "Parallel pipeline: %d parser threads, %d prefetch, %d files",
            workers, prefetch, total,
        )

        all_chunks = []
        all_docs = []
        pending: Dict[Future, Tuple[int, Path]] = {}
        file_iter = iter(enumerate(files))

        pool = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="parse"
        )

        try:
            # Submit initial prefetch batch
            for _ in range(prefetch):
                try:
                    idx, fp = next(file_iter)
                except StopIteration:
                    break
                if self._on_file_start:
                    try:
                        self._on_file_start(str(fp), idx, total)
                    except Exception:
                        pass
                fut = pool.submit(self._safe_parse_file, fp)
                pending[fut] = (idx, fp)

            last_completion = time.time()

            while pending:
                # Drain completed futures
                newly_done = [f for f in pending if f.done()]

                if not newly_done:
                    # Watchdog: kill stale futures
                    stall = time.time() - last_completion
                    if stall > self.stale_timeout:
                        oldest = next(iter(pending))
                        idx_stale, fp_stale = pending.pop(oldest)
                        oldest.cancel()
                        logger.error(
                            "[TIMEOUT] %s stalled for %.0fs -- skipping",
                            fp_stale.name, stall,
                        )
                        stats.files_failed += 1
                        stats.errors.append({
                            "file": str(fp_stale),
                            "error": f"parser stalled {stall:.0f}s",
                        })
                        last_completion = time.time()
                    else:
                        time.sleep(0.05)  # Brief yield before re-checking
                    continue

                for fut in newly_done:
                    idx_done, fp_done = pending.pop(fut)
                    last_completion = time.time()

                    try:
                        doc = fut.result(timeout=1)
                        if doc is not None and doc.text.strip():
                            all_docs.append(doc)
                            chunks = self._chunk_single_doc(doc)
                            all_chunks.extend(chunks)
                            stats.files_parsed += 1
                        else:
                            logger.warning("Empty parse: %s", fp_done.name)
                            stats.files_failed += 1
                    except Exception as e:
                        logger.error("Parse failed: %s: %s", fp_done.name, e)
                        stats.files_failed += 1
                        stats.errors.append({
                            "file": str(fp_done), "error": str(e),
                        })

                    # Submit next file to keep pool saturated
                    try:
                        next_idx, next_fp = next(file_iter)
                        if self._on_file_start:
                            try:
                                self._on_file_start(str(next_fp), next_idx, total)
                            except Exception:
                                pass
                        new_fut = pool.submit(self._safe_parse_file, next_fp)
                        pending[new_fut] = (next_idx, next_fp)
                    except StopIteration:
                        pass

        finally:
            pool.shutdown(wait=False)

        stats.chunks_created = len(all_chunks)
        return all_chunks, all_docs

    def _safe_parse_file(self, file_path: Path) -> ParsedDocument | None:
        """Parse a single file, catching exceptions for the thread pool."""
        try:
            return self.dispatcher.parse(file_path)
        except Exception as e:
            logger.error("Parser exception for %s: %s", file_path.name, e)
            return None

    def _chunk_single_doc(self, doc: ParsedDocument) -> list[dict]:
        """Chunk a single parsed document into chunk dicts."""
        path = Path(doc.source_path)
        try:
            mtime_ns = path.stat().st_mtime_ns
        except OSError:
            mtime_ns = 0

        text_chunks = self.chunker.chunk_text(doc.text)
        result = []

        for i, chunk_text in enumerate(text_chunks):
            chunk_start = doc.text.find(chunk_text[:100])
            chunk_end = (
                chunk_start + len(chunk_text)
                if chunk_start >= 0
                else i * self.config.chunk.size
            )

            chunk_id = make_chunk_id(
                file_path=doc.source_path,
                file_mtime_ns=mtime_ns,
                chunk_start=chunk_start,
                chunk_end=chunk_end,
                chunk_text=chunk_text,
            )

            result.append({
                "chunk_id": chunk_id,
                "text": chunk_text,
                "enriched_text": None,
                "source_path": doc.source_path,
                "chunk_index": i,
                "text_length": len(chunk_text),
                "parse_quality": doc.parse_quality,
            })

        return result

    # ------------------------------------------------------------------
    # Sequential fallback (single-worker mode)
    # ------------------------------------------------------------------

    def _finalize_skip(self, stats: RunStats, start_time: float) -> None:
        """Write skip manifest and summary when all files were skipped."""
        if self.skip_manager.skip_count > 0:
            self.skip_manager.write_skip_manifest(self.config.paths.output_dir)
        stats.elapsed_seconds = time.time() - start_time
        logger.info(
            "Pipeline summary: %d files hashed, %d parsed, %d skipped (reasons: %s)",
            stats.files_after_dedup, stats.files_parsed, stats.files_skipped,
            stats.skip_reasons or "none",
        )

    def _parse_files(
        self, files: list[Path], stats: RunStats
    ) -> list[ParsedDocument]:
        """Sequential parse fallback (workers=1)."""
        parsed = []
        for i, file_path in enumerate(files):
            if self._on_file_start:
                try:
                    self._on_file_start(str(file_path), i, len(files))
                except Exception:
                    pass
            try:
                doc = self.dispatcher.parse(file_path)
                if doc.text.strip():
                    parsed.append(doc)
                    stats.files_parsed += 1
                else:
                    logger.warning("Empty parse result: %s", file_path)
                    stats.files_failed += 1
            except Exception as e:
                logger.error("Parse failed for %s: %s", file_path, e)
                stats.files_failed += 1
                stats.errors.append({"file": str(file_path), "error": str(e)})
        return parsed

    def _chunk_documents(
        self, docs: list[ParsedDocument], stats: RunStats
    ) -> list[dict]:
        """Chunk all parsed documents (sequential fallback)."""
        all_chunks = []
        for doc in docs:
            all_chunks.extend(self._chunk_single_doc(doc))
        stats.chunks_created = len(all_chunks)
        return all_chunks

    def _embed_chunks(
        self, chunks: list[dict], stats: RunStats
    ) -> np.ndarray:
        """Embed all chunks — GPU batch with token-budget packing + OOM backoff."""
        texts = [c.get("enriched_text") or c["text"] for c in chunks]
        vectors = self.embedder.embed_batch(texts)
        stats.vectors_created = len(vectors)
        return vectors
