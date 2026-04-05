"""
Benchmark the full CorpusForge pipeline with per-stage timing.

Usage:
  python scripts/benchmark_pipeline.py --source data/source
  python scripts/benchmark_pipeline.py --source data/source --workers 8 --max-files 500
  python scripts/benchmark_pipeline.py --source data/source --config config/config.yaml --output bench.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.config.schema import ForgeConfig, load_config
from src.parse.dispatcher import get_supported_extensions


# ---------------------------------------------------------------------------
# GPU memory helpers
# ---------------------------------------------------------------------------

def _cuda_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def _gpu_mem_mb() -> Optional[float]:
    """Return current GPU allocated memory in MB, or None."""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.memory_allocated() / (1024 ** 2)
    except ImportError:
        pass
    return None


def _gpu_peak_mb() -> Optional[float]:
    """Return peak GPU allocated memory in MB, or None."""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.max_memory_allocated() / (1024 ** 2)
    except ImportError:
        pass
    return None


def _gpu_total_mb() -> Optional[float]:
    """Return total GPU memory in MB, or None."""
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            return props.total_memory / (1024 ** 2)
    except ImportError:
        pass
    return None


def _reset_gpu_peak() -> None:
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Stage timing record
# ---------------------------------------------------------------------------

@dataclass
class StageResult:
    name: str
    elapsed: float = 0.0
    items: int = 0
    label: str = ""  # e.g. "files/s" vs default "/s"

    @property
    def rate(self) -> float:
        if self.elapsed <= 0:
            return 0.0
        return self.items / self.elapsed


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_files(source_dir: Path, max_files: Optional[int] = None) -> list[Path]:
    supported = get_supported_extensions()
    files = sorted(source_dir.rglob("*"))
    files = [f for f in files if f.is_file() and f.suffix.lower() in supported]
    if max_files is not None and max_files > 0:
        files = files[:max_files]
    return files


# ---------------------------------------------------------------------------
# Benchmark driver
# ---------------------------------------------------------------------------

def run_benchmark(
    config: ForgeConfig,
    source_dir: Path,
    max_files: Optional[int] = None,
) -> dict:
    """Run the pipeline stages individually with per-stage timing."""

    # Late imports so sys.path is set
    from src.chunk.chunker import Chunker
    from src.chunk.chunk_ids import make_chunk_id
    from src.download.deduplicator import Deduplicator
    from src.download.hasher import Hasher
    from src.embed.embedder import Embedder
    from src.enrichment.contextual_enricher import ContextualEnricher, EnricherConfig
    from src.export.packager import Packager
    from src.parse.dispatcher import ParseDispatcher
    from src.parse.parsers.txt_parser import ParsedDocument
    from src.skip.skip_manager import SkipManager

    stages: list[StageResult] = []
    has_cuda = _cuda_available()
    _reset_gpu_peak()

    # ------------------------------------------------------------------
    # File discovery
    # ------------------------------------------------------------------
    print(f"\nDiscovering files in {source_dir} ...")
    files = discover_files(source_dir, max_files)
    total_files = len(files)
    if total_files == 0:
        print("No supported files found. Exiting.")
        sys.exit(1)
    print(f"  Found {total_files} supported file(s)\n")

    workers = config.pipeline.workers

    # ------------------------------------------------------------------
    # Stage 1: Dedup
    # ------------------------------------------------------------------
    print("Stage: Dedup ...")
    hasher = Hasher(config.paths.state_db)
    deduplicator = Deduplicator(hasher)

    t0 = time.perf_counter()
    if config.pipeline.full_reindex:
        work_files = files
    else:
        work_files = deduplicator.filter_new_and_changed(files)
    t_dedup = time.perf_counter() - t0

    stages.append(StageResult(
        name="Dedup",
        elapsed=t_dedup,
        items=total_files,
    ))
    print(f"  {len(work_files)} files after dedup ({t_dedup:.2f}s)")

    # ------------------------------------------------------------------
    # Stage 2: Skip check
    # ------------------------------------------------------------------
    print("Stage: Skip check ...")
    skip_manager = SkipManager(config.paths.skip_list, hasher)

    t0 = time.perf_counter()
    parse_files = []
    for fp in work_files:
        try:
            fsize = fp.stat().st_size
        except OSError:
            fsize = 0
        skip, reason = skip_manager.should_skip(fp, fsize)
        if not skip:
            parse_files.append(fp)
    t_skip = time.perf_counter() - t0

    stages.append(StageResult(
        name="Skip check",
        elapsed=t_skip,
        items=len(work_files),
    ))
    print(f"  {len(parse_files)} files to parse ({t_skip:.2f}s)")

    if not parse_files:
        print("All files skipped or deduped -- nothing to benchmark.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # Stage 3: Parse
    # ------------------------------------------------------------------
    worker_label = f"Parse ({workers} wrk)" if workers > 1 else "Parse (1 wrk)"
    print(f"Stage: {worker_label} ...")

    dispatcher = ParseDispatcher(
        timeout_seconds=config.parse.timeout_seconds,
        max_chars=config.parse.max_chars_per_file,
    )

    parsed_docs: list[ParsedDocument] = []
    parse_errors = 0

    if workers > 1 and len(parse_files) > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="bench-parse") as pool:
            futures = {pool.submit(dispatcher.parse, fp): fp for fp in parse_files}
            for fut in as_completed(futures):
                try:
                    doc = fut.result(timeout=config.pipeline.stale_future_timeout)
                    if doc is not None and doc.text.strip():
                        parsed_docs.append(doc)
                    else:
                        parse_errors += 1
                except Exception:
                    parse_errors += 1
        t_parse = time.perf_counter() - t0
    else:
        t0 = time.perf_counter()
        for fp in parse_files:
            try:
                doc = dispatcher.parse(fp)
                if doc.text.strip():
                    parsed_docs.append(doc)
                else:
                    parse_errors += 1
            except Exception:
                parse_errors += 1
        t_parse = time.perf_counter() - t0

    stages.append(StageResult(
        name=worker_label,
        elapsed=t_parse,
        items=len(parsed_docs),
        label="files/s",
    ))
    print(f"  {len(parsed_docs)} docs parsed, {parse_errors} failed ({t_parse:.2f}s)")

    if not parsed_docs:
        print("No documents parsed -- nothing to chunk.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # Stage 4: Chunk
    # ------------------------------------------------------------------
    print("Stage: Chunk ...")
    chunker = Chunker(
        chunk_size=config.chunk.size,
        overlap=config.chunk.overlap,
        max_heading_len=config.chunk.max_heading_len,
    )

    t0 = time.perf_counter()
    all_chunks: list[dict] = []
    for doc in parsed_docs:
        path = Path(doc.source_path)
        try:
            mtime_ns = path.stat().st_mtime_ns
        except OSError:
            mtime_ns = 0

        text_chunks = chunker.chunk_text(doc.text)
        for i, chunk_text in enumerate(text_chunks):
            chunk_start = doc.text.find(chunk_text[:100])
            chunk_end = (
                chunk_start + len(chunk_text)
                if chunk_start >= 0
                else i * config.chunk.size
            )
            chunk_id = make_chunk_id(
                file_path=doc.source_path,
                file_mtime_ns=mtime_ns,
                chunk_start=chunk_start,
                chunk_end=chunk_end,
                chunk_text=chunk_text,
            )
            all_chunks.append({
                "chunk_id": chunk_id,
                "text": chunk_text,
                "enriched_text": None,
                "source_path": doc.source_path,
                "chunk_index": i,
                "text_length": len(chunk_text),
                "parse_quality": doc.parse_quality,
            })
    t_chunk = time.perf_counter() - t0

    stages.append(StageResult(
        name="Chunk",
        elapsed=t_chunk,
        items=len(all_chunks),
    ))
    print(f"  {len(all_chunks)} chunks ({t_chunk:.2f}s)")

    if not all_chunks:
        print("No chunks produced.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # Stage 5: Enrich
    # ------------------------------------------------------------------
    enrich_label = "Enrich" if config.enrich.enabled else "Enrich"
    print(f"Stage: {enrich_label} ...")

    enricher = ContextualEnricher(
        config=EnricherConfig(
            enabled=config.enrich.enabled,
            ollama_url=config.enrich.ollama_url,
            model=config.enrich.model,
            max_chunk_chars=config.enrich.max_chunk_chars,
        )
    )

    doc_texts = {doc.source_path: doc.text for doc in parsed_docs}
    t0 = time.perf_counter()
    all_chunks = enricher.enrich_chunks(all_chunks, doc_texts)
    t_enrich = time.perf_counter() - t0

    enriched_count = sum(1 for c in all_chunks if c.get("enriched_text") is not None)
    disabled_tag = "" if config.enrich.enabled else " (disabled)"

    stages.append(StageResult(
        name=f"Enrich{disabled_tag}",
        elapsed=t_enrich,
        items=enriched_count,
    ))
    print(f"  {enriched_count} enriched{disabled_tag} ({t_enrich:.2f}s)")

    # ------------------------------------------------------------------
    # Stage 6: Embed
    # ------------------------------------------------------------------
    embed_device = "CUDA" if has_cuda and config.embed.device == "cuda" else "CPU"
    embed_label = f"Embed ({embed_device})"
    print(f"Stage: {embed_label} ...")

    gpu_mem_before = _gpu_mem_mb()

    embedder = Embedder(
        model_name=config.embed.model_name,
        dim=config.embed.dim,
        device=config.embed.device,
        max_batch_tokens=config.embed.max_batch_tokens,
        dtype=config.embed.dtype,
    )

    texts = [c.get("enriched_text") or c["text"] for c in all_chunks]
    _reset_gpu_peak()

    t0 = time.perf_counter()
    vectors = embedder.embed_batch(texts)
    t_embed = time.perf_counter() - t0

    gpu_mem_after = _gpu_mem_mb()
    gpu_peak = _gpu_peak_mb()

    stages.append(StageResult(
        name=embed_label,
        elapsed=t_embed,
        items=len(all_chunks),
    ))
    print(f"  {len(vectors)} vectors ({t_embed:.2f}s)")

    # ------------------------------------------------------------------
    # Stage 7: Export
    # ------------------------------------------------------------------
    print("Stage: Export ...")
    packager = Packager(output_dir=config.paths.output_dir)

    dummy_stats = {
        "benchmark": True,
        "files_found": total_files,
        "files_parsed": len(parsed_docs),
        "chunks_created": len(all_chunks),
    }

    t0 = time.perf_counter()
    export_dir = packager.export(
        chunks=all_chunks,
        vectors=vectors,
        entities=[],
        stats=dummy_stats,
    )
    t_export = time.perf_counter() - t0

    stages.append(StageResult(
        name="Export",
        elapsed=t_export,
        items=len(all_chunks),
    ))
    print(f"  Exported to {export_dir} ({t_export:.2f}s)")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total_time = sum(s.elapsed for s in stages)
    total_chunks = len(all_chunks)
    overall_rate = total_chunks / max(total_time, 0.001)

    # Print table
    print()
    print("=" * 62)
    print("  CorpusForge Benchmark Results")
    print("=" * 62)
    header = f"{'Stage':<16}| {'Time (s)':>8} | {'Items':>8} | {'Rate':>12}"
    sep    = f"{'-' * 16}|{'-' * 10}|{'-' * 10}|{'-' * 13}"
    print(header)
    print(sep)

    for s in stages:
        rate_unit = s.label if s.label else "/s"
        if s.items == 0 and s.elapsed < 0.01:
            rate_str = "(disabled)"
        else:
            rate_val = s.rate
            if rate_val >= 1:
                rate_str = f"{rate_val:.0f} {rate_unit}"
            else:
                rate_str = f"{rate_val:.2f} {rate_unit}"
        print(f"{s.name:<16}| {s.elapsed:>8.1f} | {s.items:>8} | {rate_str:>12}")

    print(sep)
    print(f"{'TOTAL':<16}| {total_time:>8.1f} | {total_chunks:>8} | {overall_rate:>8.0f} chunks/s")
    print("=" * 62)

    # GPU info
    if has_cuda:
        gpu_total = _gpu_total_mb()
        print(f"\nGPU memory:")
        if gpu_mem_before is not None:
            print(f"  Before embed:  {gpu_mem_before:>8.1f} MB")
        if gpu_mem_after is not None:
            print(f"  After embed:   {gpu_mem_after:>8.1f} MB")
        if gpu_peak is not None:
            print(f"  Peak (embed):  {gpu_peak:>8.1f} MB")
        if gpu_total is not None:
            print(f"  Total VRAM:    {gpu_total:>8.1f} MB")
        print(f"  Embed device:  {embedder.mode}")

    print()

    # Build JSON results
    results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_dir": str(source_dir),
        "workers": workers,
        "total_files_found": total_files,
        "files_after_dedup": len(work_files),
        "files_parsed": len(parsed_docs),
        "parse_errors": parse_errors,
        "total_chunks": total_chunks,
        "total_time_s": round(total_time, 3),
        "overall_chunks_per_sec": round(overall_rate, 1),
        "stages": [],
        "config": {
            "chunk_size": config.chunk.size,
            "chunk_overlap": config.chunk.overlap,
            "embed_model": config.embed.model_name,
            "embed_device": config.embed.device,
            "embed_dtype": config.embed.dtype,
            "embed_max_batch_tokens": config.embed.max_batch_tokens,
            "enrich_enabled": config.enrich.enabled,
            "full_reindex": config.pipeline.full_reindex,
        },
    }

    for s in stages:
        results["stages"].append({
            "name": s.name,
            "elapsed_s": round(s.elapsed, 3),
            "items": s.items,
            "rate": round(s.rate, 1),
        })

    if has_cuda:
        results["gpu"] = {
            "available": True,
            "embed_mode": embedder.mode,
            "mem_before_embed_mb": round(gpu_mem_before, 1) if gpu_mem_before else None,
            "mem_after_embed_mb": round(gpu_mem_after, 1) if gpu_mem_after else None,
            "peak_embed_mb": round(gpu_peak, 1) if gpu_peak else None,
            "total_vram_mb": round(gpu_total, 1) if gpu_total else None,
        }
    else:
        results["gpu"] = {"available": False, "embed_mode": embedder.mode}

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark the full CorpusForge pipeline with per-stage timing.",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source directory containing files to process.",
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=None,
        help="Number of parser worker threads (overrides config).",
    )
    parser.add_argument(
        "--max-files", "-n",
        type=int,
        default=None,
        help="Limit number of files to process.",
    )
    parser.add_argument(
        "--config", "-c",
        default="config/config.yaml",
        help="Path to config YAML (default: config/config.yaml).",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="JSON output file path (default: benchmark_<timestamp>.json).",
    )
    parser.add_argument(
        "--full-reindex",
        action="store_true",
        help="Force full reindex (skip dedup shortcut).",
    )
    args = parser.parse_args()

    # Load config
    config = load_config(args.config)

    # Apply CLI overrides
    if args.workers is not None:
        config.pipeline.workers = args.workers
    if args.full_reindex:
        config.pipeline.full_reindex = True

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    source_dir = Path(args.source)
    if not source_dir.is_dir():
        print(f"Error: {source_dir} is not a directory.", file=sys.stderr)
        sys.exit(1)

    results = run_benchmark(config, source_dir, max_files=args.max_files)

    # Save JSON
    if args.output:
        out_path = Path(args.output)
    else:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out_path = Path(f"benchmark_{stamp}.json")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to: {out_path}")


if __name__ == "__main__":
    main()
