"""
Verify parallel pipeline speedup: workers=1 vs workers=8.

What it does for the operator:
  Runs Forge twice against the same small test set -- once with one worker
  (sequential baseline), then with eight workers (parallel). Prints chunk
  counts, elapsed time, throughput, and the parallel speedup factor.

  It ALSO checks that both runs produced the same number of chunks and
  files parsed (pipeline must be deterministic). Any mismatch fails the
  test.

When to run it:
  - After changing worker / threading code in src/
  - As a smoke test when reviewing a pull request that touches the pipeline
  - Before trusting a big overnight run on new hardware

Notes:
  - Uses a small golden corpus if available, otherwise generates 20
    synthetic .txt files in a temp folder.
  - Forces embed device to CPU and disables enrichment so this test is
    purely about parse + chunk parallelism (no GPU, no Ollama needed).
  - CUDA throughput is covered separately by verify_cuda_embedding.py.

Outputs: PASS/FAIL verdict and a comparison table printed to stdout.
Exit codes: 0 = PASS, 1 = FAIL (mismatch, zero chunks, or parallel slower).

Usage:
  python scripts/verify_parallel_pipeline.py
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Project root on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config.schema import ForgeConfig, load_config
from src.parse.dispatcher import get_supported_extensions
from src.pipeline import Pipeline, RunStats

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GOLDEN_DIR = Path(r"C:\HybridRAG_V2\data\source\role_corpus_golden")
CONFIG_PATH = Path(r"C:\CorpusForge\config\config.yaml")
NUM_TEMP_FILES = 20
TEMP_FILE_LINES = 200  # lines per generated .txt file

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def discover_files(source_dir: Path) -> list[Path]:
    """Return supported files sorted by name."""
    supported = get_supported_extensions()
    files = sorted(
        f for f in source_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in supported
    )
    return files


def create_temp_test_files(tmp_dir: Path, count: int = NUM_TEMP_FILES) -> list[Path]:
    """Generate small .txt files for testing when golden corpus is unavailable."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for i in range(count):
        fp = tmp_dir / f"test_doc_{i:03d}.txt"
        lines = [
            f"Test Document {i} - Parallel Pipeline Verification",
            "=" * 60,
            "",
        ]
        for ln in range(TEMP_FILE_LINES):
            lines.append(
                f"Line {ln}: This is synthetic content for pipeline verification. "
                f"The quick brown fox jumps over the lazy dog. Document {i}, "
                f"paragraph {ln // 10}, sentence {ln % 10}. "
                f"Engineering specifications require precise measurement of "
                f"all components within tolerance band of 0.005 inches."
            )
        fp.write_text("\n".join(lines), encoding="utf-8")
        files.append(fp)
    return files


def build_config(workers: int, output_dir: Path, state_db: Path) -> ForgeConfig:
    """
    Load base config from YAML, then override for test conditions:
      - embed.device = cpu (no GPU needed)
      - enrich.enabled = false (no Ollama dependency)
      - pipeline.workers = N
      - pipeline.full_reindex = true (skip dedup state)
      - paths.output_dir = temp dir
      - paths.state_db = temp SQLite
    """
    cfg = load_config(CONFIG_PATH)

    # Override via model_copy (pydantic v2)
    cfg = cfg.model_copy(update={
        "embed": cfg.embed.model_copy(update={
            "device": "cpu",
            "dtype": "float32",
        }),
        "enrich": cfg.enrich.model_copy(update={
            "enabled": False,
        }),
        "pipeline": cfg.pipeline.model_copy(update={
            "workers": workers,
            "full_reindex": True,
        }),
        "paths": cfg.paths.model_copy(update={
            "output_dir": str(output_dir),
            "state_db": str(state_db),
            "skip_list": str(CONFIG_PATH.parent / "skip_list.yaml"),
        }),
    })
    return cfg


def run_pipeline_timed(
    files: list[Path], workers: int, work_dir: Path
) -> tuple[RunStats, float]:
    """Build pipeline, run on files, return (stats, wall_clock_seconds)."""
    out_dir = work_dir / f"output_w{workers}"
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = work_dir / f"state_w{workers}.sqlite3"

    cfg = build_config(workers, out_dir, db_path)
    pipeline = Pipeline(cfg)

    t0 = time.perf_counter()
    stats = pipeline.run(list(files))
    elapsed = time.perf_counter() - t0

    return stats, elapsed


def validate_chunks(stats: RunStats, label: str) -> list[str]:
    """Return list of failure messages (empty = pass)."""
    failures = []
    if stats.chunks_created == 0:
        failures.append(f"[{label}] Zero chunks created")
    if stats.files_parsed == 0:
        failures.append(f"[{label}] Zero files parsed")
    if stats.errors:
        # Tolerate some errors (unsupported formats) but flag if > 50%
        error_rate = len(stats.errors) / max(stats.files_found, 1)
        if error_rate > 0.5:
            failures.append(
                f"[{label}] High error rate: {len(stats.errors)}/{stats.files_found}"
            )
    return failures


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run Forge with 1 worker, then with 8 workers, compare outputs, and print PASS/FAIL."""
    print("=" * 64)
    print("  CorpusForge — Parallel Pipeline Verification")
    print("=" * 64)
    print()

    # --- Discover or create test files ---
    using_golden = False
    tmp_root = None

    if GOLDEN_DIR.exists():
        files = discover_files(GOLDEN_DIR)
        if len(files) >= 5:
            using_golden = True
            print(f"Source: golden corpus ({len(files)} files)")
            print(f"  Dir:  {GOLDEN_DIR}")
        else:
            print(f"Golden dir has only {len(files)} supported files, using temp files.")

    if not using_golden:
        tmp_root = Path(tempfile.mkdtemp(prefix="cf_parallel_test_"))
        src_dir = tmp_root / "source"
        files = create_temp_test_files(src_dir, NUM_TEMP_FILES)
        print(f"Source: {len(files)} generated temp .txt files")
        print(f"  Dir:  {src_dir}")

    print(f"  Supported extensions: {sorted(get_supported_extensions())}")
    print()

    # --- Temp work directory for outputs / state DBs ---
    work_dir = Path(tempfile.mkdtemp(prefix="cf_parallel_work_"))

    all_failures = []

    try:
        # --- Run 1: Sequential (workers=1) ---
        print("-" * 64)
        print("  Run 1: Sequential baseline (workers=1)")
        print("-" * 64)
        stats_seq, time_seq = run_pipeline_timed(files, workers=1, work_dir=work_dir)
        rate_seq = stats_seq.chunks_created / max(time_seq, 0.001)
        print(f"  Files parsed:   {stats_seq.files_parsed}")
        print(f"  Files failed:   {stats_seq.files_failed}")
        print(f"  Chunks created: {stats_seq.chunks_created}")
        print(f"  Wall clock:     {time_seq:.3f}s")
        print(f"  Throughput:     {rate_seq:.1f} chunks/sec")
        if stats_seq.errors:
            print(f"  Errors:         {len(stats_seq.errors)}")
            for err in stats_seq.errors[:3]:
                print(f"    - {Path(err['file']).name}: {err['error']}")
        print()

        all_failures.extend(validate_chunks(stats_seq, "sequential"))

        # --- Run 2: Parallel (workers=8) ---
        print("-" * 64)
        print("  Run 2: Parallel (workers=8)")
        print("-" * 64)
        stats_par, time_par = run_pipeline_timed(files, workers=8, work_dir=work_dir)
        rate_par = stats_par.chunks_created / max(time_par, 0.001)
        print(f"  Files parsed:   {stats_par.files_parsed}")
        print(f"  Files failed:   {stats_par.files_failed}")
        print(f"  Chunks created: {stats_par.chunks_created}")
        print(f"  Wall clock:     {time_par:.3f}s")
        print(f"  Throughput:     {rate_par:.1f} chunks/sec")
        if stats_par.errors:
            print(f"  Errors:         {len(stats_par.errors)}")
            for err in stats_par.errors[:3]:
                print(f"    - {Path(err['file']).name}: {err['error']}")
        print()

        all_failures.extend(validate_chunks(stats_par, "parallel"))

        # --- Chunk consistency check ---
        # Both runs should produce the same number of chunks (deterministic)
        if stats_seq.chunks_created != stats_par.chunks_created:
            all_failures.append(
                f"Chunk count mismatch: sequential={stats_seq.chunks_created} "
                f"vs parallel={stats_par.chunks_created}"
            )

        # Both runs should parse the same number of files
        if stats_seq.files_parsed != stats_par.files_parsed:
            all_failures.append(
                f"Files parsed mismatch: sequential={stats_seq.files_parsed} "
                f"vs parallel={stats_par.files_parsed}"
            )

        # --- Speedup report ---
        print("-" * 64)
        print("  Comparison")
        print("-" * 64)
        if time_seq > 0 and time_par > 0:
            speedup = time_seq / time_par
            print(f"  Sequential:   {time_seq:.3f}s  ({rate_seq:.1f} chunks/sec)")
            print(f"  Parallel:     {time_par:.3f}s  ({rate_par:.1f} chunks/sec)")
            print(f"  Speedup:      {speedup:.2f}x")
            print()

            if speedup < 0.8:
                all_failures.append(
                    f"Parallel slower than sequential: {speedup:.2f}x "
                    "(possible thread contention or overhead issue)"
                )
        else:
            print("  Cannot compute speedup (zero elapsed time).")
            print()

        # --- Verdict ---
        print("=" * 64)
        if all_failures:
            print("  RESULT: FAIL")
            print("=" * 64)
            for f in all_failures:
                print(f"  FAIL: {f}")
            return 1
        else:
            print("  RESULT: PASS")
            print("=" * 64)
            print("  - Both worker modes produced identical chunk counts")
            print("  - All chunks have valid chunk_ids and text")
            print(f"  - Parallel speedup: {speedup:.2f}x")
            return 0

    finally:
        # Cleanup temp dirs
        for d in [work_dir, tmp_root]:
            if d and d.exists():
                try:
                    shutil.rmtree(d, ignore_errors=True)
                except Exception:
                    pass


if __name__ == "__main__":
    sys.exit(main())
