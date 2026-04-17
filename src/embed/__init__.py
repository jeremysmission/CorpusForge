"""Embedding components — stage 7 of the Forge pipeline.

This package converts chunk text into the float16 vectors that V2
later uses for semantic search. On a workstation with a GPU, the
embedder runs on CUDA; if the GPU is unavailable it falls back to ONNX
on CPU. Either way the output shape is consistent: float16 vectors
with the model's configured dimension (768 for nomic-embed-text-v1.5).

Modules:
  - ``embedder``       : the model wrapper (CUDA or ONNX fallback).
  - ``batch_manager``  : packs chunks into token-budgeted batches so
                         the GPU stays fed without running out of VRAM.
"""
