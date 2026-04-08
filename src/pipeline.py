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

import json
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
from .enrichment.contextual_enricher import ContextualEnricher, EnricherConfig, probe_enrichment
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
    entities_extracted: int = 0
    elapsed_seconds: float = 0.0
    skip_reasons: str = ""
    errors: list[dict] = field(default_factory=list)
    format_coverage: dict = field(default_factory=dict)

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
            "entities_extracted": self.entities_extracted,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "error_count": len(self.errors),
            "skip_reasons": self.skip_reasons,
            "format_coverage": self.format_coverage,
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

        config_deferred = {
            ext: "Deferred by config for this run"
            for ext in config.parse.defer_extensions
        }
        self.hasher = Hasher(config.paths.state_db)
        self.deduplicator = Deduplicator(self.hasher)
        self.skip_manager = SkipManager(config.paths.skip_list, self.hasher, extra_deferred_exts=config_deferred)
        self.dispatcher = ParseDispatcher(
            timeout_seconds=config.parse.timeout_seconds,
            max_chars=config.parse.max_chars_per_file,
            skip_list_path=config.paths.skip_list,
        )
        self.chunker = Chunker(
            chunk_size=config.chunk.size,
            overlap=config.chunk.overlap,
            max_heading_len=config.chunk.max_heading_len,
        )
        self.packager = Packager(output_dir=config.paths.output_dir)

        # Lazy-loaded models — only initialized when their stage runs
        self._embedder: Embedder | None = None
        self._enricher: ContextualEnricher | None = None
        self._extractor = None

        models = []
        if config.embed.enabled:
            models.append("embedder")
        if config.enrich.enabled:
            models.append("enricher")
        if config.extract.enabled:
            models.append("extractor")
        if models:
            logger.info("Models to load on first use: %s", ", ".join(models))
        else:
            logger.info("Chunk-only mode — no AI models will be loaded.")

        # Pre-flight: fail loud if enrichment enabled but Ollama unavailable
        if config.enrich.enabled:
            probe = probe_enrichment(
                ollama_url=config.enrich.ollama_url,
                model=config.enrich.model,
                auto_start=True,
            )
            if not probe.ready:
                raise RuntimeError(
                    f"Enrichment is enabled but not available: {probe.status_text}. "
                    f"Disable enrichment (enrich.enabled: false) or fix the issue."
                )

    def _get_embedder(self) -> Embedder:
        """Lazy-load the embedder on first use."""
        if self._embedder is None:
            logger.info("Loading embedder: %s on %s...",
                        self.config.embed.model_name, self.config.embed.device)
            self._embedder = Embedder(
                model_name=self.config.embed.model_name,
                dim=self.config.embed.dim,
                device=self.config.embed.device,
                max_batch_tokens=self.config.embed.max_batch_tokens,
                dtype=self.config.embed.dtype,
            )
        return self._embedder

    def _get_enricher(self) -> ContextualEnricher:
        """Lazy-load the enricher on first use."""
        if self._enricher is None:
            logger.info("Loading enricher: %s via %s...",
                        self.config.enrich.model, self.config.enrich.ollama_url)
            self._enricher = ContextualEnricher(
                config=EnricherConfig(
                    enabled=self.config.enrich.enabled,
                    ollama_url=self.config.enrich.ollama_url,
                    model=self.config.enrich.model,
                    max_chunk_chars=self.config.enrich.max_chunk_chars,
                    max_concurrent=self.config.enrich.max_concurrent,
                )
            )
        return self._enricher

    def _get_extractor(self):
        """Lazy-load the GLiNER extractor on first use."""
        if self._extractor is None:
            from src.extract.gliner_extractor import GlinerExtractor, ExtractorConfig
            logger.info("Loading extractor: %s (batch_size=%d, workers=%d)...",
                        self.config.extract.model_name, self.config.extract.batch_size,
                        self.config.extract.max_concurrent)
            self._extractor = GlinerExtractor(
                config=ExtractorConfig(
                    enabled=self.config.extract.enabled,
                    model_name=self.config.extract.model_name,
                    entity_types=self.config.extract.entity_types,
                    min_confidence=self.config.extract.min_confidence,
                    batch_size=self.config.extract.batch_size,
                    max_concurrent=self.config.extract.max_concurrent,
                )
            )
        return self._extractor

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

        # Stage 5: Contextual enrichment (phi4:14B via Ollama) — skipped if disabled
        if self.config.enrich.enabled:
            enricher = self._get_enricher()
            doc_texts = {doc.source_path: doc.text for doc in all_docs}
            all_chunks = enricher.enrich_chunks(all_chunks, doc_texts)
            stats.chunks_enriched = sum(
                1 for c in all_chunks if c.get("enriched_text") is not None
            )
        else:
            logger.info("Enrichment disabled — skipping.")

        # Stage 6: Embed (GPU batch with token-budget packing + OOM backoff) — skipped if disabled
        if self.config.embed.enabled:
            vectors = self._embed_chunks(all_chunks, stats)
        else:
            logger.info("Embedding disabled — chunk-only export.")
            vectors = np.empty((0, 768), dtype=np.float16)

        # Stage 7: Entity extraction (GLiNER batch on CPU) — skipped if disabled
        entities = []
        if self.config.extract.enabled:
            extractor = self._get_extractor()
            entities = extractor.extract_entities(all_chunks)
            stats.entities_extracted = len(entities)
        else:
            logger.info("Entity extraction disabled — skipping.")

        export_stats = self._build_export_stats(stats, start_time)

        # Stage 8: Export
        export_dir = self.packager.export(
            chunks=all_chunks,
            vectors=vectors,
            entities=entities,
            stats=export_stats,
        )
        self.deduplicator.mark_indexed([Path(doc.source_path) for doc in all_docs])
        logger.info("Export written to: %s", export_dir)

        # Write skip manifest alongside export
        if self.skip_manager.skip_count > 0:
            self.skip_manager.write_skip_manifest(export_dir)

        stats.skip_reasons = export_stats["skip_reasons"]
        stats.elapsed_seconds = export_stats["elapsed_seconds"]

        # Pipeline summary
        rate = stats.chunks_created / max(stats.elapsed_seconds, 0.01)
        logger.info(
            "Pipeline summary: %d files hashed, %d parsed, %d skipped, "
            "%d chunks at %.1f chunks/sec (reasons: %s)",
            stats.files_after_dedup, stats.files_parsed, stats.files_skipped,
            stats.chunks_created, rate, stats.skip_reasons or "none",
        )

        # Write run report (slice 3.3)
        self._write_run_report(export_dir, stats)

        # Append to run history (slice 4.1)
        self._append_run_history(export_dir, stats)

        return stats

    def _write_run_report(self, export_dir: Path, stats: RunStats) -> None:
        """Write a human-readable run report alongside the export."""
        report_path = export_dir / "run_report.txt"
        lines = [
            "=" * 60,
            "  CorpusForge Run Report",
            "=" * 60,
            "",
            "Files",
            f"  Found:          {stats.files_found}",
            f"  After dedup:    {stats.files_after_dedup}",
            f"  Parsed:         {stats.files_parsed}",
            f"  Skipped:        {stats.files_skipped}",
            f"  Failed:         {stats.files_failed}",
            "",
            "Output",
            f"  Chunks:         {stats.chunks_created}",
            f"  Enriched:       {stats.chunks_enriched}",
            f"  Vectors:        {stats.vectors_created}",
            f"  Entities:       {stats.entities_extracted}",
            "",
            "Performance",
            f"  Elapsed:        {stats.elapsed_seconds:.1f}s",
            f"  Chunks/sec:     {stats.chunks_created / max(stats.elapsed_seconds, 0.01):.1f}",
            "",
        ]
        if stats.format_coverage:
            lines.append("Format Coverage")
            for ext, count in sorted(stats.format_coverage.items(), key=lambda x: -x[1]):
                lines.append(f"  {ext:12s}  {count}")
            lines.append("")

        if stats.skip_reasons:
            lines.append("Skip Reasons")
            lines.append(f"  {stats.skip_reasons}")
            lines.append("")

        if stats.errors:
            lines.append(f"Errors ({len(stats.errors)})")
            for err in stats.errors[:20]:
                lines.append(f"  {err['file']}: {err['error']}")
            if len(stats.errors) > 20:
                lines.append(f"  ... and {len(stats.errors) - 20} more")
            lines.append("")

        lines.append("=" * 60)

        with open(report_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
        logger.info("Run report written to: %s", report_path)

    def _append_run_history(self, export_dir: Path, stats: RunStats) -> None:
        """Append this run to the history log (last 10 runs kept)."""
        from datetime import datetime
        history_path = Path(self.config.paths.output_dir) / "run_history.jsonl"
        entry = {
            "timestamp": datetime.now().isoformat(),
            "export_dir": str(export_dir),
            "files_found": stats.files_found,
            "files_parsed": stats.files_parsed,
            "files_skipped": stats.files_skipped,
            "files_failed": stats.files_failed,
            "chunks_created": stats.chunks_created,
            "chunks_enriched": stats.chunks_enriched,
            "vectors_created": stats.vectors_created,
            "entities_extracted": stats.entities_extracted,
            "elapsed_seconds": round(stats.elapsed_seconds, 1),
            "format_coverage": stats.format_coverage,
        }
        # Append
        try:
            with open(history_path, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(entry) + "\n")
            # Trim to last 10
            with open(history_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) > 10:
                with open(history_path, "w", encoding="utf-8", newline="\n") as f:
                    f.writelines(lines[-10:])
            logger.info("Run history updated: %s", history_path)
        except Exception as exc:
            logger.warning("Failed to update run history: %s", exc)

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
                            ext = fp_done.suffix.lower() or "(no ext)"
                            stats.format_coverage[ext] = stats.format_coverage.get(ext, 0) + 1
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

    def _build_export_stats(self, stats: RunStats, start_time: float) -> dict:
        """Finalize the stats snapshot that is written into manifest.json."""
        stats.skip_reasons = self.skip_manager.get_reason_summary()
        stats.elapsed_seconds = time.time() - start_time
        return stats.to_dict()

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
        embedder = self._get_embedder()
        texts = [c.get("enriched_text") or c["text"] for c in chunks]
        vectors = embedder.embed_batch(texts)
        stats.vectors_created = len(vectors)
        return vectors
