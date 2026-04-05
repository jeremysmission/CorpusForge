"""
verify_cuda_embedding.py — Verify CUDA embedding is active and benchmark throughput.

Usage:  py -3.12 scripts/verify_cuda_embedding.py
Run from CorpusForge project root.
"""

from __future__ import annotations

import sys
import os
import time

# Ensure project root is on sys.path so 'src.embed.embedder' resolves
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

SEPARATOR = "-" * 60


def make_test_texts(n: int) -> list[str]:
    """Generate n realistic-length test strings for embedding."""
    base_sentences = [
        "The hybrid retrieval system combines dense vector search with sparse keyword matching.",
        "Graph databases store relationships between entities as first-class objects.",
        "Token-budget batching prevents out-of-memory errors during large embedding jobs.",
        "GovCloud deployments require FedRAMP-compliant infrastructure configurations.",
        "Nomic embed text v1.5 produces 768-dimensional normalized vectors for semantic search.",
        "Document chunking at 512 tokens with 64-token overlap preserves context boundaries.",
        "ONNX runtime provides CPU inference as a fallback when CUDA is unavailable.",
        "Reciprocal rank fusion merges results from multiple retrieval strategies.",
        "The corpus extraction pipeline converts PDF and DOCX files into clean text chunks.",
        "Sentence transformers encode variable-length text into fixed-dimension embeddings.",
    ]
    return [base_sentences[i % len(base_sentences)] for i in range(n)]


def main() -> int:
    print(SEPARATOR)
    print("  CorpusForge CUDA Embedding Verification")
    print(SEPARATOR)
    print()

    # ------------------------------------------------------------------
    # Step 1: Import and init Embedder with device="cuda"
    # ------------------------------------------------------------------
    try:
        from src.embed.embedder import Embedder
    except ImportError as exc:
        print(f"[FAIL] Cannot import Embedder: {exc}")
        print("VERDICT: FAIL -- import error, check sys.path and dependencies")
        return 1

    try:
        embedder = Embedder(device="cuda")
    except RuntimeError as exc:
        print(f"[FAIL] Embedder init failed: {exc}")
        print("VERDICT: FAIL -- no backend available")
        return 1

    # ------------------------------------------------------------------
    # Step 2: Verify CUDA mode (not ONNX fallback)
    # ------------------------------------------------------------------
    mode = embedder.mode
    if mode == "cuda":
        print(f"[CHECK] Embedder mode: {mode} ✓")
    else:
        print(f"[FAIL] Embedder mode: {mode} -- expected cuda, got fallback")
        if mode == "onnx":
            print("        Embedder fell back to ONNX CPU. CUDA is not available or failed.")
            print("        Ensure torch with CUDA support is installed and a GPU is visible.")
        print(f"VERDICT: FAIL -- running in {mode} mode, not CUDA")
        return 1

    # ------------------------------------------------------------------
    # Step 3: Report GPU info
    # ------------------------------------------------------------------
    try:
        import torch

        gpu_idx = int(os.getenv("CUDA_VISIBLE_DEVICES", "0").split(",")[0])
        props = torch.cuda.get_device_properties(gpu_idx)
        gpu_name = props.name
        total_gb = props.total_memory / (1024 ** 3)
        print(f"[CHECK] GPU: {gpu_name} ({total_gb:.0f}GB)")
    except Exception as exc:
        print(f"[WARN] Could not read GPU properties: {exc}")
        gpu_name = "unknown"
        total_gb = 0.0

    # ------------------------------------------------------------------
    # Step 4: Batch 1 — 100 texts
    # ------------------------------------------------------------------
    texts_100 = make_test_texts(100)

    torch.cuda.reset_peak_memory_stats()
    t0 = time.perf_counter()
    vectors_1 = embedder.embed_batch(texts_100)
    t1 = time.perf_counter()

    elapsed_1 = t1 - t0
    rate_1 = len(texts_100) / elapsed_1 if elapsed_1 > 0 else 0
    shape_ok = vectors_1.shape == (100, embedder.dim)

    if shape_ok and rate_1 > 0:
        print(f"[CHECK] Batch 1: {len(texts_100)} texts in {elapsed_1:.2f}s = {rate_1:.0f} chunks/sec ✓")
    else:
        print(f"[FAIL] Batch 1: shape={vectors_1.shape}, expected=(100, {embedder.dim})")
        print(f"VERDICT: FAIL -- batch 1 produced wrong output shape")
        return 1

    # ------------------------------------------------------------------
    # Step 5: Batch 2 — 500 texts (sustained throughput)
    # ------------------------------------------------------------------
    texts_500 = make_test_texts(500)

    t2 = time.perf_counter()
    vectors_2 = embedder.embed_batch(texts_500)
    t3 = time.perf_counter()

    elapsed_2 = t3 - t2
    rate_2 = len(texts_500) / elapsed_2 if elapsed_2 > 0 else 0
    shape_ok_2 = vectors_2.shape == (500, embedder.dim)

    if shape_ok_2 and rate_2 > 0:
        print(f"[CHECK] Batch 2: {len(texts_500)} texts in {elapsed_2:.2f}s = {rate_2:.0f} chunks/sec ✓")
    else:
        print(f"[FAIL] Batch 2: shape={vectors_2.shape}, expected=(500, {embedder.dim})")
        print(f"VERDICT: FAIL -- batch 2 produced wrong output shape")
        return 1

    # ------------------------------------------------------------------
    # Step 6: GPU memory usage
    # ------------------------------------------------------------------
    try:
        peak_bytes = torch.cuda.max_memory_allocated()
        peak_gb = peak_bytes / (1024 ** 3)
        if total_gb > 0:
            print(f"[CHECK] GPU memory peak: {peak_gb:.1f}GB / {total_gb:.0f}GB")
        else:
            print(f"[CHECK] GPU memory peak: {peak_gb:.1f}GB")
    except Exception as exc:
        print(f"[WARN] Could not read GPU memory stats: {exc}")

    # ------------------------------------------------------------------
    # Step 7: Throughput consistency check
    # ------------------------------------------------------------------
    avg_rate = (rate_1 + rate_2) / 2
    ratio = min(rate_1, rate_2) / max(rate_1, rate_2) if max(rate_1, rate_2) > 0 else 0

    if ratio < 0.3:
        print(f"[WARN] Throughput inconsistent: batch1={rate_1:.0f}, batch2={rate_2:.0f} chunks/sec")

    # ------------------------------------------------------------------
    # Verdict
    # ------------------------------------------------------------------
    print()
    print(f"VERDICT: PASS -- CUDA embedding verified at {avg_rate:.0f} chunks/sec")
    return 0


if __name__ == "__main__":
    sys.exit(main())
