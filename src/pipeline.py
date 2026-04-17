"""
Pipeline orchestrator — parallel parse -> GPU batch embed -> export.

Plain-English role
------------------
This module is the conductor of the whole Forge pipeline. Everything the
operator sees in the GUI's progress bar and every artifact that ends up
in the export folder is driven from the ``Pipeline`` class in this file.

The pipeline runs the nine stages in order:

    hash -> dedup -> skip -> parse -> chunk -> enrich -> embed ->
    extract -> export

Key behaviors operators should know:
  - Parsing runs in a pool of worker threads (``workers`` in config)
    with a stale-future watchdog so one bad file cannot wedge the run.
  - Every completed file is written to a crash-safe checkpoint on disk
    immediately, so a stop or crash before export does not throw away
    work already parsed and chunked.
  - Cooperative stop: when the operator clicks stop, Forge finishes
    in-flight work at the nearest safe boundary, preserves the
    checkpoint, and only writes an export folder if the finished
    chunks and vectors stay aligned.
  - Large corpora (>100K chunks) embed in sub-batches backed by a
    memory-mapped file so the machine does not run out of RAM.

Architecture ported from V1 (HybridRAG3 src/core/indexer.py):
  - ThreadPoolExecutor(N workers) for parallel file parsing
  - Prefetch 2x workers to keep the ready queue saturated
  - Main thread drains parsed results -> chunk -> GPU batch embed
  - Stale future watchdog kills hung parsers
  - Token-budget batching + OOM backoff in embedder

V1 achieved 60-200 chunks/sec sustained with this pattern.

For a plain-English overview of what Forge does and what it outputs
for HybridRAG V2, see `docs/FORGE_IN_PLAIN_ENGLISH.md`. This module
is the authoritative stage-by-stage implementation; the plain-English
doc is the operator-facing summary.
"""

from __future__ import annotations

import hashlib
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
from .export.chunk_checkpoint import ChunkCheckpoint
from .export.packager import Packager
from .download.hasher import Hasher
from .download.deduplicator import Deduplicator
from .skip.skip_manager import SkipManager
from .parse.dispatcher import ParseDispatcher, get_supported_extensions
from .parse.parsers.txt_parser import ParsedDocument

logger = logging.getLogger(__name__)


@dataclass
class RunStats:
    """Live counters for one pipeline run.

    The GUI and CLI read these fields to show progress and the final
    run report. Every field is plain (files counted, chunks produced,
    vectors created, seconds elapsed) so a non-programmer can read a
    run report and understand exactly what happened.
    """

    files_found: int = 0
    files_after_dedup: int = 0
    files_skipped: int = 0
    files_parsed: int = 0
    files_failed: int = 0
    skipped_unchanged: int = 0
    skipped_duplicate: int = 0
    chunks_created: int = 0
    chunks_per_second: float = 0.0
    chunks_enriched: int = 0
    vectors_created: int = 0
    entities_extracted: int = 0
    elapsed_seconds: float = 0.0
    export_dir: str = ""
    checkpoint_dir: str = ""
    stop_requested: bool = False
    skip_reasons: str = ""
    checkpointed_files: int = 0
    errors: list[dict] = field(default_factory=list)
    format_coverage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize the live counters for the GUI/CLI progress panel."""
        return {
            "files_found": self.files_found,
            "files_after_dedup": self.files_after_dedup,
            "files_skipped": self.files_skipped,
            "files_parsed": self.files_parsed,
            "files_failed": self.files_failed,
            "skipped_unchanged": self.skipped_unchanged,
            "skipped_duplicate": self.skipped_duplicate,
            "chunks_created": self.chunks_created,
            "chunks_per_second": round(self.chunks_per_second, 2),
            "chunks_enriched": self.chunks_enriched,
            "vectors_created": self.vectors_created,
            "entities_extracted": self.entities_extracted,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "export_dir": self.export_dir,
            "checkpoint_dir": self.checkpoint_dir,
            "stop_requested": self.stop_requested,
            "error_count": len(self.errors),
            "skip_reasons": self.skip_reasons,
            "checkpointed_files": self.checkpointed_files,
            "format_coverage": self.format_coverage,
        }


def _apply_cpu_reservation():
    """Reserve 2 logical CPU threads for user interaction.

    Layer 1: CPU affinity — pin this process to logical CPUs 2-N, leaving 0-1 for user.
    Layer 2: Process priority — set to below-normal so user apps win contention.
    Layer 3: PyTorch threads — cap to N-2 so tensor ops don't saturate all logical CPUs.
    """
    logical_cpu_count = os.cpu_count() or 8
    reserved = 2
    max_threads = max(logical_cpu_count - reserved, 1)

    # Layer 1: CPU affinity (strongest guarantee)
    try:
        import psutil
        p = psutil.Process()
        available_cpus = list(range(reserved, logical_cpu_count))
        if available_cpus:
            p.cpu_affinity(available_cpus)
            logger.info(
                "CPU affinity: pinned to logical CPUs %d-%d (logical CPUs 0-%d reserved for user)",
                reserved,
                logical_cpu_count - 1,
                reserved - 1,
            )
    except ImportError:
        logger.info("psutil not installed — skipping CPU affinity (install for guaranteed logical CPU reservation)")
    except Exception as exc:
        logger.warning("CPU affinity failed: %s", exc)

    # Layer 2: Process priority — below normal
    try:
        import psutil
        p = psutil.Process()
        p.nice(getattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS", 10))
        logger.info("Process priority: set to below-normal")
    except Exception:
        pass

    # Layer 3: PyTorch thread cap
    try:
        import torch
        torch.set_num_threads(max_threads)
    except Exception:
        pass
    os.environ.setdefault("OMP_NUM_THREADS", str(max_threads))
    os.environ.setdefault("MKL_NUM_THREADS", str(max_threads))
    logger.info("CPU threads: %d/%d logical CPUs (2 reserved for user)", max_threads, logical_cpu_count)


def _configure_parser_environment(config: ForgeConfig) -> None:
    """Resolve parser runtime settings with env vars taking precedence over config."""
    config.parse.ocr_mode = _resolve_parser_mode(
        env_var="HYBRIDRAG_OCR_MODE",
        config_value=config.parse.ocr_mode,
        allowed={"skip", "auto", "force"},
    )
    config.parse.docling_mode = _resolve_parser_mode(
        env_var="HYBRIDRAG_DOCLING_MODE",
        config_value=config.parse.docling_mode,
        allowed={"off", "fallback", "prefer"},
    )
    os.environ["HYBRIDRAG_OCR_MODE"] = config.parse.ocr_mode
    os.environ["HYBRIDRAG_DOCLING_MODE"] = config.parse.docling_mode


def _resolve_parser_mode(env_var: str, config_value: str, allowed: set[str]) -> str:
    """Use a valid env var override when present; otherwise fall back to config."""
    raw = os.getenv(env_var, "").strip().lower()
    if raw:
        if raw in allowed:
            return raw
        logger.warning(
            "Ignoring invalid %s=%r; expected one of %s. Falling back to config value %r.",
            env_var,
            raw,
            sorted(allowed),
            config_value,
        )
    return config_value


class Pipeline:
    """
    The Forge orchestrator. One instance runs one corpus through the
    nine-stage pipeline and writes an export folder for V2.

    Plain-English tour of what ``run()`` does, in the order it happens:

        1. Hash and dedup (fast, sequential)
           - Fingerprint every file with SHA-256 and drop files that
             were already indexed in a previous run or that are exact
             duplicates of other files in this batch.

        2. Skip check
           - For each surviving file, the skip manager decides whether
             it is parseable (right format, not encrypted, not a temp
             file, inside size limits). Skipped files are still hashed
             and recorded in the skip manifest so nothing is hidden.

        3 + 4 + 5 + 6. Parallel parse -> chunk -> (optional) live embed
           - Worker threads parse files in parallel. Each parsed file is
             chunked immediately and persisted to the checkpoint on disk
             so a crash or stop does not throw away finished work.
           - When enrichment is off, chunks flow to the GPU embedder
             during parsing to keep the GPU warm.

        7. Enrichment (optional)
           - If enabled, the local phi4 model on Ollama writes a one-
             paragraph preamble for each chunk describing where it sits
             in the document. The preamble is prepended to the chunk
             text before embedding and improves retrieval.

        8. Embed
           - Chunks (or enriched chunks) are converted to float16
             vectors on the GPU in token-budget batches. Large corpora
             use a memory-mapped file so RAM does not balloon.

        9. Entity extraction (optional)
           - GLiNER runs on CPU across all chunks to pull candidate
             entities for V2's knowledge graph seeding.

        10. Export
           - Writes chunks.jsonl + vectors.npy + manifest.json +
             skip_manifest.json + run_report.txt to a timestamped
             export folder and updates the ``latest`` pointer.

    Operator-facing features:
      - Stale-future watchdog kills a hung parser after a configurable
        timeout rather than wedging the run.
      - Cooperative stop: if the operator clicks stop, Forge finishes
        in-flight work at a safe boundary, preserves the checkpoint,
        and only writes an export if chunks and vectors line up.
      - Every run writes a human-readable ``run_report.txt`` and
        appends a JSON summary to ``run_history.jsonl``.
    """

    def __init__(self, config: ForgeConfig):
        """Wire up every subsystem the pipeline will need for one run."""
        self.config = config
        self.workers = config.pipeline.workers

        _configure_parser_environment(config)

        # Reserve 2 logical CPU threads for user interaction.
        _apply_cpu_reservation()
        self.stale_timeout = config.pipeline.stale_future_timeout
        self.embed_flush_batch = config.pipeline.embed_flush_batch

        config_deferred = {
            ext: "Deferred by config for this run"
            for ext in config.parse.defer_extensions
        }
        self.hasher = Hasher(config.paths.state_db)
        self.deduplicator = Deduplicator(self.hasher)
        self.skip_manager = SkipManager(
            config.paths.skip_list,
            self.hasher,
            extra_deferred_exts=config_deferred,
            ocr_mode=config.parse.ocr_mode,
        )
        # Reset the cached parser map so the new defer policy takes effect
        # for any archive members opened by ArchiveParser. The dispatcher's
        # ParserMap is module-global and would otherwise carry stale state.
        from src.parse.dispatcher import reset_parser_map
        reset_parser_map()
        self.dispatcher = ParseDispatcher(
            timeout_seconds=config.parse.timeout_seconds,
            max_chars=config.parse.max_chars_per_file,
            skip_list_path=config.paths.skip_list,
            extra_deferred_exts=set(config.parse.defer_extensions),
        )
        self.chunker = Chunker(
            chunk_size=config.chunk.size,
            overlap=config.chunk.overlap,
            max_heading_len=config.chunk.max_heading_len,
        )
        self.packager = Packager(output_dir=config.paths.output_dir)
        self.chunk_checkpoint = ChunkCheckpoint(config.paths.output_dir)

        # Callbacks — set in run(), but helper methods may emit updates.
        self._on_file_start = None
        self._on_stage_progress = None
        self._on_stats_update = None
        self._should_stop = None
        self._run_start_time = None
        self._stop_announced = False
        self._source_path_mapper = None

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
        on_stage_progress: callable | None = None,
        on_stats_update: callable | None = None,
        should_stop: callable | None = None,
        source_path_mapper: callable | None = None,
    ) -> RunStats:
        """
        Run the pipeline on a list of input files.

        Args:
            input_files: List of file paths to process.
            on_file_start: Optional callback(file_path, file_index, total_files)
                called before each file is parsed. Used by GUI for progress.
            on_stage_progress: Optional callback(stage, current, total, detail)
                called periodically for each pipeline stage. Used by GUI for
                live progress across all phases.

        Returns RunStats with processing results.
        """
        self._on_file_start = on_file_start
        self._on_stage_progress = on_stage_progress
        self._on_stats_update = on_stats_update
        stats = RunStats()
        start_time = time.time()
        self._run_start_time = start_time
        self._should_stop = should_stop or (lambda: False)
        self._stop_announced = False
        self._source_path_mapper = source_path_mapper

        stats.files_found = len(input_files)
        self._emit_stats(stats)
        try:
            if self._check_stop(
                stats,
                "Stop requested before dedup started. No new work admitted.",
            ):
                return stats

            # Stage 2: Hash & dedup
            self._emit_stage("dedup", 0, len(input_files), "Starting dedup scan...")
            if self.config.pipeline.full_reindex:
                work_files = input_files
            else:
                def _dedup_progress(scanned, total, current, dupes):
                    self._emit_stage("dedup", scanned, total, f"{current} ({dupes} dupes)")

                work_files = self.deduplicator.filter_new_and_changed(
                    input_files,
                    on_progress=_dedup_progress,
                    should_stop=self._should_stop,
                )
                stats.skipped_unchanged = self.deduplicator.skipped_unchanged
                stats.skipped_duplicate = self.deduplicator.skipped_duplicate
            stats.files_after_dedup = len(work_files)
            self._emit_stats(stats)
            if self._check_stop(
                stats,
                "Stop requested after dedup. Remaining stages will not start.",
            ):
                return stats

            if not work_files:
                logger.info("No new or changed files to process.")
                stats.elapsed_seconds = time.time() - start_time
                self._emit_stats(stats)
                return stats

            # Stage 2b: Skip check (hash but don't parse)
            parse_files = []
            for fp in work_files:
                if self._check_stop(
                    stats,
                    "Stop requested during skip review. Parse will not start.",
                ):
                    break
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
            self._emit_stats(stats)
            if stats.stop_requested and not parse_files:
                stats.skip_reasons = self.skip_manager.get_reason_summary()
                self._finalize_skip(stats, start_time)
                return stats

            if not parse_files:
                logger.info("All files skipped -- nothing to parse.")
                stats.skip_reasons = self.skip_manager.get_reason_summary()
                self._finalize_skip(stats, start_time)
                self._emit_stats(stats)
                return stats

            total_parse_files = len(parse_files)
            resume = self.chunk_checkpoint.begin_run(
                self._build_checkpoint_signature(),
                parse_files,
                file_hashes=self._build_file_hash_lookup(parse_files),
                resume_enabled=True,
            )
            stats.checkpoint_dir = str(self.chunk_checkpoint.root)
            stats.checkpointed_files = len(resume.source_paths)
            live_embed_during_parse = (
                self.config.embed.enabled and not self.config.enrich.enabled
            )
            live_embed_pending = list(resume.chunks) if live_embed_during_parse else []
            live_vector_batches: list[np.ndarray] = []

            all_chunks = list(resume.chunks)
            parsed_source_paths = list(resume.source_paths)
            all_docs = list(resume.docs)
            parse_files = resume.remaining_files

            # Stage 3+4+5+6: Parallel parse → chunk → enrich → embed
            if resume.resumed:
                stats.files_parsed = len(parsed_source_paths)
                stats.chunks_created = len(all_chunks)
                self._emit_stage(
                    "parse",
                    stats.files_parsed,
                    total_parse_files,
                    f"Resumed {len(parsed_source_paths)} files / {len(all_chunks)} chunks from checkpoint.",
                )
                self._emit_stats(stats)

            if parse_files:
                self._emit_stage("parse", stats.files_parsed, total_parse_files, "Starting parse...")
                on_chunks_ready = None
                if live_embed_during_parse:
                    def _on_chunks_ready(new_chunks: list[dict]) -> None:
                        live_embed_pending.extend(new_chunks)
                        self._flush_live_embed_batches(
                            live_embed_pending,
                            live_vector_batches,
                            stats,
                        )

                    on_chunks_ready = _on_chunks_ready
                if self.workers > 1 and len(parse_files) > 1:
                    new_chunks, new_docs, new_source_paths = self._parallel_parse_and_chunk(
                        parse_files,
                        stats,
                        total_files=total_parse_files,
                        on_chunks_ready=on_chunks_ready,
                    )
                else:
                    new_chunks, new_docs, new_source_paths = self._parse_and_chunk_sequential(
                        parse_files,
                        stats,
                        total_files=total_parse_files,
                        on_chunks_ready=on_chunks_ready,
                    )
                all_chunks.extend(new_chunks)
                all_docs.extend(new_docs)
                parsed_source_paths.extend(new_source_paths)

            if not all_chunks:
                logger.warning("No chunks produced -- nothing to embed or export.")
                stats.elapsed_seconds = time.time() - start_time
                self._emit_stats(stats)
                return stats

            self.chunk_checkpoint.set_status("chunked")

            # Stage 5: Contextual enrichment (phi4:14B via Ollama) — skipped if disabled
            if self.config.enrich.enabled:
                self.chunk_checkpoint.set_status("enriching")
                self._emit_stage("enrich", 0, len(all_chunks), "Loading enricher...")
                enricher = self._get_enricher()
                doc_texts = {doc.source_path: doc.text for doc in all_docs}
                all_chunks = enricher.enrich_chunks(all_chunks, doc_texts)
                stats.chunks_enriched = sum(
                    1 for c in all_chunks if c.get("enriched_text") is not None
                )
                self._emit_stage("enrich", stats.chunks_enriched, len(all_chunks), "Done")
                self._emit_stats(stats)
            else:
                logger.info("Enrichment disabled — skipping.")

            # Cooperative stop check before embed. If the operator stops here with
            # embed enabled, we must NOT ship a chunks+vectors export (that would be
            # a chunk/vector length mismatch at V2 import time). Drop chunks to 0 so
            # the export path below sees an empty work set and skips packaging.
            self._check_stop(
                stats,
                "Stop requested before embed. Keeping chunk checkpoint on disk; no mismatched export will be written.",
            )

            # Stage 6: Embed (GPU batch with token-budget packing + OOM backoff)
            if live_embed_during_parse and not stats.stop_requested:
                self.chunk_checkpoint.set_status("embedding")
                prior_vectors = sum(len(batch) for batch in live_vector_batches)
                pending_vectors = np.empty((0, self._get_embedder().dim), dtype=np.float16)
                if live_embed_pending:
                    pending_vectors = self._embed_chunks(live_embed_pending, stats)
                if live_vector_batches:
                    if len(pending_vectors):
                        live_vector_batches.append(np.asarray(pending_vectors, dtype=np.float16))
                    vectors = self._combine_live_vector_batches(
                        live_vector_batches,
                        self._get_embedder().dim,
                    )
                    stats.vectors_created = prior_vectors + len(pending_vectors)
                    self._emit_stats(stats)
                else:
                    vectors = pending_vectors
            elif self.config.embed.enabled and not stats.stop_requested:
                self.chunk_checkpoint.set_status("embedding")
                vectors = self._embed_chunks(all_chunks, stats)
                # If a stop fired mid-embed, vectors may be shorter than chunks.
                # Trim chunks so the export keeps chunks/vectors aligned.
                if stats.stop_requested and len(vectors) < len(all_chunks):
                    logger.warning(
                        "Stop honored mid-embed: trimming chunks %d -> %d to match vectors.",
                        len(all_chunks), len(vectors),
                    )
                    all_chunks = all_chunks[: len(vectors)]
                    stats.chunks_created = len(all_chunks)
            elif self.config.embed.enabled and stats.stop_requested:
                completed_live_vectors = sum(len(batch) for batch in live_vector_batches)
                if live_embed_during_parse and completed_live_vectors > 0:
                    vectors = self._combine_live_vector_batches(
                        live_vector_batches,
                        self._get_embedder().dim,
                    )
                    if completed_live_vectors < len(all_chunks):
                        logger.warning(
                            "Stop honored during live parse/embed: trimming chunks %d -> %d "
                            "to match already-embedded prefix.",
                            len(all_chunks), completed_live_vectors,
                        )
                        all_chunks = all_chunks[:completed_live_vectors]
                    stats.chunks_created = len(all_chunks)
                    stats.vectors_created = len(vectors)
                else:
                    logger.warning(
                        "Stop fired before embed (embed enabled) — preserving %d checkpointed "
                        "chunks on disk, but writing no export to avoid chunk/vector mismatch.",
                        len(all_chunks),
                    )
                    live_vector_batches.clear()
                    all_chunks = []
                    stats.chunks_created = 0
                    vectors = np.empty((0, 768), dtype=np.float16)
            else:
                logger.info("Embedding disabled — chunk-only export.")
                vectors = np.empty((0, 768), dtype=np.float16)

            # If we have nothing left to ship after a cooperative stop, don't write
            # an export directory. The GUI uses stats.export_dir to honestly tell the
            # operator whether any completed work was packaged.
            if stats.stop_requested and not all_chunks:
                logger.warning(
                    "Stop honored with no packageable work — skipping export entirely."
                )
                self.chunk_checkpoint.set_status("stopped_before_export")
                stats.skip_reasons = self.skip_manager.get_reason_summary()
                stats.elapsed_seconds = time.time() - start_time
                self._emit_stats(stats)
                return stats

            # Stage 7: Entity extraction (GLiNER batch on CPU) — skipped if disabled
            entities = []
            if self.config.extract.enabled and not stats.stop_requested:
                self._emit_stage("extract", 0, len(all_chunks), "Loading extractor...")
                extractor = self._get_extractor()
                entities = extractor.extract_entities(all_chunks)
                stats.entities_extracted = len(entities)
                self._emit_stage("extract", len(entities), len(all_chunks), "Done")
                self._emit_stats(stats)
            elif stats.stop_requested:
                logger.info("Stop requested — skipping entity extraction; packaging completed work.")
            else:
                logger.info("Entity extraction disabled — skipping.")

            export_stats = self._build_export_stats(stats, start_time)

            # Stage 8: Export
            self.chunk_checkpoint.set_status("exporting")
            self._emit_stage(
                "export", 0, len(all_chunks),
                f"Writing chunks/vectors/manifest for {len(all_chunks)} chunks...",
            )
            export_dir = self.packager.export(
                chunks=all_chunks,
                vectors=vectors,
                entities=entities,
                stats=export_stats,
            )
            stats.export_dir = str(export_dir)
            self._emit_stage(
                "export", len(all_chunks), len(all_chunks),
                f"Done -> {export_dir.name if hasattr(export_dir, 'name') else export_dir}",
            )
            exported_source_paths = sorted({
                str(chunk["source_path"])
                for chunk in all_chunks
                if chunk.get("source_path")
            })
            self.deduplicator.mark_indexed([Path(path) for path in exported_source_paths])
            self.chunk_checkpoint.clear()
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
            self._emit_stats(stats)

            return stats
        except Exception:
            self._sync_checkpoint_on_failure(stats)
            raise

    def _refresh_live_rates(self, stats: RunStats) -> None:
        """Update elapsed time and chunk throughput for live telemetry."""
        if self._run_start_time is None:
            return
        stats.elapsed_seconds = time.time() - self._run_start_time
        stats.chunks_per_second = stats.chunks_created / max(stats.elapsed_seconds, 0.01)

    def _request_stop(self, stats: RunStats, detail: str) -> None:
        """Mark stop requested and emit a single honest stage update."""
        stats.stop_requested = True
        self._refresh_live_rates(stats)
        self._emit_stats(stats)
        if not self._stop_announced:
            self._emit_stage("stopping", 0, 0, detail)
            self._stop_announced = True

    def _check_stop(self, stats: RunStats, detail: str) -> bool:
        """Return True when a cooperative stop has been requested."""
        if self._should_stop and self._should_stop():
            self._request_stop(stats, detail)
            return True
        return False

    def _emit_stage(self, stage: str, current: int, total: int, detail: str = "") -> None:
        """Emit stage progress to callback and log heartbeat."""
        if self._on_stage_progress:
            try:
                self._on_stage_progress(stage, current, total, detail)
            except Exception:
                pass
        # CLI heartbeat log every call
        logger.info("[%s] %d/%d %s", stage, current, total, detail)

    def _emit_stats(self, stats: RunStats) -> None:
        """Emit a snapshot of live stats to the GUI/CLI callback."""
        self._refresh_live_rates(stats)
        if self._on_stats_update:
            try:
                self._on_stats_update(stats.to_dict())
            except Exception:
                pass

    def _build_checkpoint_signature(self) -> str:
        """Build a stable signature for crash-safe chunk checkpoint reuse."""
        payload = {
            "source_dirs": [str(Path(p)) for p in self.config.paths.source_dirs],
            "output_dir": self.config.paths.output_dir,
            "chunk_size": self.config.chunk.size,
            "chunk_overlap": self.config.chunk.overlap,
            "chunk_heading": self.config.chunk.max_heading_len,
            "parse_max_chars": self.config.parse.max_chars_per_file,
            "parse_ocr_mode": self.config.parse.ocr_mode,
            "parse_docling_mode": self.config.parse.docling_mode,
            "embed_enabled": self.config.embed.enabled,
            "enrich_enabled": self.config.enrich.enabled,
            "extract_enabled": self.config.extract.enabled,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()

    def _checkpoint_document(
        self,
        doc: ParsedDocument,
        chunks: list[dict],
        stats: RunStats,
        *,
        file_ext: str,
    ) -> tuple[list[dict], list[str]]:
        """Persist a parsed document's chunks immediately for crash safety."""
        state = self.hasher.get_state(doc.source_path)
        content_hash = state["hash"] if state else self.hasher.hash_file(Path(doc.source_path))
        self.chunk_checkpoint.append_document(doc, chunks, content_hash=content_hash)
        stats.files_parsed += 1
        stats.chunks_created += len(chunks)
        stats.checkpointed_files += 1
        stats.checkpoint_dir = str(self.chunk_checkpoint.root)
        stats.format_coverage[file_ext] = stats.format_coverage.get(file_ext, 0) + 1
        return chunks, [doc.source_path]

    def _build_file_hash_lookup(self, files: list[Path]) -> dict[str, str]:
        """Map current candidate files to their content hash for safe resume checks."""
        file_hashes: dict[str, str] = {}
        for file_path in files:
            state = self.hasher.get_state(file_path)
            if state:
                file_hashes[self.hasher._normalize_path(file_path)] = state["hash"]
            else:
                file_hashes[self.hasher._normalize_path(file_path)] = self.hasher.hash_file(file_path)
        return file_hashes

    def _sync_checkpoint_on_failure(self, stats: RunStats) -> None:
        """Best-effort checkpoint flush when a run crashes before export completes."""
        try:
            if self.chunk_checkpoint.root.exists():
                self.chunk_checkpoint.sync(status="crashed")
                stats.checkpoint_dir = str(self.chunk_checkpoint.root)
                self._emit_stats(stats)
        except Exception:
            pass

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
        self,
        files: list[Path],
        stats: RunStats,
        *,
        total_files: int | None = None,
        on_chunks_ready: callable | None = None,
    ) -> tuple[list[dict], list[ParsedDocument], list[str]]:
        """
        Parse files in parallel using ThreadPoolExecutor.

        Worker threads parse files concurrently. Main thread collects
        results and chunks them. Keeps GPU embed queue fed.

        V1 pattern: prefetch 2x workers, drain completed futures,
        stale future watchdog kills hung parsers.
        """
        workers = min(self.workers, len(files))
        prefetch = workers * 2
        total = total_files or len(files)

        logger.info(
            "Parallel pipeline: %d parser threads, %d prefetch, %d files",
            workers, prefetch, total,
        )

        all_chunks = []
        all_docs = []
        parsed_source_paths = []
        pending: Dict[Future, Tuple[int, Path]] = {}
        file_iter = iter(enumerate(files))
        stop_submissions = False

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
            last_stage_update = time.time()

            while pending:
                if not stop_submissions and self._check_stop(
                    stats,
                    "Stop requested. Finishing in-flight parse work, cancelling queued files, then packaging completed output.",
                ):
                    stop_submissions = True
                    cancelled = 0
                    for fut, _meta in list(pending.items()):
                        if fut.cancel():
                            pending.pop(fut)
                            cancelled += 1
                    if cancelled:
                        self._emit_stage(
                            "stopping",
                            0,
                            0,
                            f"Cancelled {cancelled} queued parse tasks; waiting on active workers.",
                        )

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
                        self._emit_stats(stats)
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
                            ext = fp_done.suffix.lower() or "(no ext)"
                            new_chunks, new_sources = self._checkpoint_document(
                                doc,
                                chunks,
                                stats,
                                file_ext=ext,
                            )
                            all_chunks.extend(new_chunks)
                            parsed_source_paths.extend(new_sources)
                            if on_chunks_ready and new_chunks:
                                on_chunks_ready(new_chunks)
                        else:
                            logger.warning("Empty parse: %s", fp_done.name)
                            stats.files_failed += 1
                    except Exception as e:
                        logger.error("Parse failed: %s: %s", fp_done.name, e)
                        stats.files_failed += 1
                        stats.errors.append({
                            "file": str(fp_done), "error": str(e),
                        })

                    # Parse stage progress every second; stats every completed file.
                    now_stage = time.time()
                    if now_stage - last_stage_update >= 1.0:
                        done_count = stats.files_parsed + stats.files_failed
                        self._refresh_live_rates(stats)
                        self._emit_stage(
                            "parse", done_count, total,
                            f"{fp_done.name} | CPU/IO parse | {stats.chunks_created} chunks | {stats.chunks_per_second:.1f} chunks/sec",
                        )
                        last_stage_update = now_stage
                    self._emit_stats(stats)

                    # Submit next file to keep pool saturated until stop is requested.
                    if not stop_submissions:
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
        self._refresh_live_rates(stats)
        self._emit_stage(
            "parse",
            stats.files_parsed + stats.files_failed,
            total,
            f"Done ({len(all_chunks)} chunks, {stats.chunks_per_second:.1f} chunks/sec, CPU/IO parse complete)",
        )
        self._emit_stats(stats)
        return all_chunks, all_docs, parsed_source_paths

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
        export_source_path = doc.source_path
        if self._source_path_mapper is not None:
            export_source_path = self._source_path_mapper(doc.source_path)
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
                file_path=export_source_path,
                file_mtime_ns=mtime_ns,
                chunk_start=chunk_start,
                chunk_end=chunk_end,
                chunk_text=chunk_text,
            )

            result.append({
                "chunk_id": chunk_id,
                "text": chunk_text,
                "enriched_text": None,
                "source_path": export_source_path,
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
        self._emit_stats(stats)
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

    def _parse_and_chunk_sequential(
        self,
        files: list[Path],
        stats: RunStats,
        *,
        total_files: int | None = None,
        on_chunks_ready: callable | None = None,
    ) -> tuple[list[dict], list[ParsedDocument], list[str]]:
        """Sequential parse+chunk fallback with per-document checkpoint flush."""
        parsed_docs = []
        parsed_source_paths = []
        all_chunks = []
        total = total_files or len(files)

        for i, file_path in enumerate(files):
            if self._check_stop(
                stats,
                "Stop requested. Sequential parse will stop at the current file boundary.",
            ):
                break
            if self._on_file_start:
                try:
                    self._on_file_start(str(file_path), i, total)
                except Exception:
                    pass
            try:
                doc = self.dispatcher.parse(file_path)
                if doc.text.strip():
                    parsed_docs.append(doc)
                    chunks = self._chunk_single_doc(doc)
                    ext = file_path.suffix.lower() or "(no ext)"
                    new_chunks, new_sources = self._checkpoint_document(
                        doc,
                        chunks,
                        stats,
                        file_ext=ext,
                    )
                    all_chunks.extend(new_chunks)
                    parsed_source_paths.extend(new_sources)
                    if on_chunks_ready and new_chunks:
                        on_chunks_ready(new_chunks)
                else:
                    logger.warning("Empty parse result: %s", file_path)
                    stats.files_failed += 1
            except Exception as e:
                logger.error("Parse failed for %s: %s", file_path, e)
                stats.files_failed += 1
                stats.errors.append({"file": str(file_path), "error": str(e)})
            self._emit_stage(
                "parse",
                stats.files_parsed + stats.files_failed,
                total,
                f"{file_path.name} | CPU/IO parse | {stats.chunks_created} chunks | {stats.chunks_per_second:.1f} chunks/sec",
            )
            self._emit_stats(stats)
        return all_chunks, parsed_docs, parsed_source_paths

    def _embed_chunks(
        self, chunks: list[dict], stats: RunStats
    ) -> np.ndarray:
        """Embed all chunks — GPU batch with token-budget packing + OOM backoff.

        For large corpora (>100K chunks), processes in sub-batches of
        EMBED_SUB_BATCH chunks and writes vectors to a memory-mapped file
        to avoid RAM exhaustion from accumulating all vectors in memory.
        """
        embedder = self._get_embedder()
        total = len(chunks)
        dim = embedder.dim
        # Sub-batch size for memory-safe embedding of large corpora.
        # 100K chunks ≈ 300MB GPU vectors + 100MB text — well within RAM.
        sub_batch_size = 100_000
        self._emit_stage("embed", 0, total, "Starting embedding...")

        embed_start = time.time()

        if total <= sub_batch_size:
            # Small corpus — embed all at once (original path)
            texts = [c.get("enriched_text") or c["text"] for c in chunks]
            vectors = embedder.embed_batch(texts)
        else:
            # Large corpus — embed in sub-batches, write to mmap file to
            # avoid OOM from accumulating 2M+ float32 vectors in RAM.
            import tempfile
            mmap_path = Path(tempfile.mktemp(suffix=".dat", prefix="embed_"))
            vectors_mmap = np.memmap(
                str(mmap_path), dtype=np.float16, mode="w+", shape=(total, dim)
            )

            offset = 0
            for batch_start in range(0, total, sub_batch_size):
                if self._check_stop(
                    stats,
                    f"Stop requested between embed sub-batches "
                    f"({offset}/{total} chunks embedded). "
                    f"Packaging completed sub-batches.",
                ):
                    break
                batch_end = min(batch_start + sub_batch_size, total)
                batch_texts = [
                    c.get("enriched_text") or c["text"]
                    for c in chunks[batch_start:batch_end]
                ]
                batch_vectors = embedder.embed_batch(batch_texts)
                batch_count = len(batch_vectors)
                vectors_mmap[offset:offset + batch_count] = batch_vectors.astype(np.float16)
                vectors_mmap.flush()
                offset += batch_count
                stats.vectors_created = offset

                elapsed = time.time() - embed_start
                rate = offset / max(elapsed, 0.01)
                self._emit_stage(
                    "embed", offset, total,
                    f"sub-batch {batch_start//sub_batch_size + 1} done, {rate:.0f} chunks/sec",
                )
                logger.info(
                    "Embed sub-batch %d-%d complete (%d/%d, %.0f chunks/sec)",
                    batch_start, batch_end, offset, total, rate,
                )
                self._emit_stats(stats)

            # Copy from mmap to regular array for export. Slice to `offset`
            # so a stop mid-embed doesn't drag along zeroed rows.
            vectors = np.array(vectors_mmap[:offset], dtype=np.float16)
            del vectors_mmap
            try:
                mmap_path.unlink()
            except OSError:
                pass

        embed_elapsed = time.time() - embed_start
        stats.vectors_created = len(vectors)

        rate = stats.vectors_created / max(embed_elapsed, 0.01)
        self._emit_stage("embed", stats.vectors_created, total, f"{rate:.0f} chunks/sec")
        self._emit_stats(stats)
        return vectors

    def _flush_live_embed_batches(
        self,
        pending_chunks: list[dict],
        vector_batches: list[np.ndarray],
        stats: RunStats,
        *,
        force: bool = False,
    ) -> None:
        """Embed pending chunks incrementally during parse using embed_flush_batch."""
        if not pending_chunks:
            return

        embedder = None
        while pending_chunks and (
            len(pending_chunks) >= self.embed_flush_batch or force
        ):
            if self._check_stop(
                stats,
                "Stop requested during live embed flush. Preserving checkpoint; no export will be written.",
            ):
                return

            batch_size = min(len(pending_chunks), self.embed_flush_batch)
            batch = pending_chunks[:batch_size]
            del pending_chunks[:batch_size]

            if embedder is None:
                self.chunk_checkpoint.set_status("embedding")
                embedder = self._get_embedder()

            embed_start = time.time()
            texts = [c.get("enriched_text") or c["text"] for c in batch]
            batch_vectors = embedder.embed_batch(texts)
            batch_vectors = np.asarray(batch_vectors, dtype=np.float16)
            vector_batches.append(batch_vectors)
            stats.vectors_created += len(batch_vectors)

            total_known = max(stats.chunks_created, stats.vectors_created)
            rate = len(batch_vectors) / max(time.time() - embed_start, 0.01)
            self._emit_stage(
                "embed",
                stats.vectors_created,
                total_known,
                f"GPU live flush {stats.vectors_created}/{total_known} vectors "
                f"({rate:.0f} chunks/sec)",
            )
            self._emit_stats(stats)

    def _combine_live_vector_batches(
        self,
        vector_batches: list[np.ndarray],
        dim: int,
    ) -> np.ndarray:
        """Concatenate live-embedded batches into the final export array."""
        if not vector_batches:
            return np.empty((0, dim), dtype=np.float16)
        if len(vector_batches) == 1:
            return vector_batches[0]
        return np.concatenate(vector_batches, axis=0)
