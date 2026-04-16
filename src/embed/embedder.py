"""
Embedder — converts text into 768-dim vectors via nomic-embed-text v1.5.

Ported from V1 (src/core/embedder.py). Simplified for CorpusForge:
  - CUDA primary path (sentence-transformers + PyTorch)
  - ONNX CPU fallback (no Ollama — CorpusForge has no HTTP embedding)
  - Token-budget batching via BatchManager
  - OOM backoff with automatic batch size reduction
  - Task-aware prefixes (search_document: / search_query:) for nomic models

Design rule: No Ollama fallback. CorpusForge runs on a GPU workstation.
If no GPU, fall back to ONNX CPU. If neither works, fail loud.
"""

from __future__ import annotations

import logging
import os

import numpy as np

from .batch_manager import BatchManager
from src.util import skip_signal

logger = logging.getLogger(__name__)


class Embedder:
    """
    Text → vector embedding via sentence-transformers.

    Two inference paths:
      1. Direct CUDA (primary) — 45x faster than Ollama HTTP
      2. ONNX CPU (fallback) — 3-12x faster than Ollama HTTP

    Task-aware: nomic models use different prefixes for documents vs queries.
    """

    # Map Ollama-style names to HuggingFace model IDs
    _MODEL_MAP = {
        "nomic-embed-text": "nomic-ai/nomic-embed-text-v1.5",
        "nomic-embed-text:latest": "nomic-ai/nomic-embed-text-v1.5",
    }

    _TASK_AWARE_PREFIXES = frozenset({"nomic-embed-text", "nomic-embed-text-v2-moe"})

    def __init__(
        self,
        model_name: str = "nomic-ai/nomic-embed-text-v1.5",
        dim: int = 768,
        device: str = "cuda",
        max_batch_tokens: int = 49152,
        dtype: str = "float16",
    ):
        self.model_name = self._MODEL_MAP.get(model_name, model_name)
        self.dim = dim
        self.requested_device = device
        self.dtype = dtype
        self._model = None
        self._mode = "uninitialized"

        self.batch_manager = BatchManager(
            token_budget=max_batch_tokens,
            max_batch_size=int(os.getenv("HYBRIDRAG_EMBED_BATCH", "256")),
        )

        # Determine task-aware prefix from model name
        base_name = model_name.split("/")[-1].split(":")[0]
        self._use_task_prefix = base_name in self._TASK_AWARE_PREFIXES

        self._init_model()

    def _init_model(self) -> None:
        """Initialize sentence-transformers model with CUDA or ONNX fallback."""
        if self.requested_device == "cuda":
            if self._try_init_cuda():
                return

        if self._try_init_onnx():
            return

        raise RuntimeError(
            "No embedding backend available. "
            "Install sentence-transformers + torch (CUDA) or onnxruntime (CPU). "
            "CorpusForge requires a local embedding backend — no Ollama fallback."
        )

    def _try_init_cuda(self) -> bool:
        """Try loading model on CUDA via sentence-transformers."""
        try:
            import torch
            if not torch.cuda.is_available():
                logger.warning("CUDA not available, will try ONNX fallback.")
                return False

            from sentence_transformers import SentenceTransformer

            # When CUDA_VISIBLE_DEVICES is set, PyTorch remaps the selected GPU
            # to cuda:0. We always use cuda:0 here — gpu selection is handled by
            # CUDA_VISIBLE_DEVICES env var set in gpu_selector.py.
            cvd = os.getenv("CUDA_VISIBLE_DEVICES")
            if cvd is not None:
                gpu_index = 0  # remapped by CUDA_VISIBLE_DEVICES
                physical_gpu = int(cvd.split(",")[0])
            else:
                gpu_index = 0
                physical_gpu = 0
            device_str = f"cuda:{gpu_index}"

            model_path = os.getenv("HYBRIDRAG_EMBED_MODEL_PATH", self.model_name)

            self._model = SentenceTransformer(
                model_path,
                device=device_str,
                trust_remote_code=True,
            )

            # Apply precision
            if self.dtype in ("float16", "fp16"):
                self._model.half()
            elif self.dtype in ("bfloat16", "bf16"):
                if torch.cuda.is_bf16_supported():
                    self._model.bfloat16()
                else:
                    self._model.half()

            # Probe dimension
            probe = self._model.encode(["probe"], normalize_embeddings=True)
            self.dim = probe.shape[1]

            total_mem = torch.cuda.get_device_properties(gpu_index).total_memory / (1024**3)
            self._mode = "cuda"
            logger.info(
                "Embedder ready: CUDA on physical GPU %d (logical cuda:%d, %.1f GB), dim=%d, dtype=%s",
                physical_gpu, gpu_index, total_mem, self.dim, self.dtype,
            )
            return True

        except Exception as e:
            logger.warning("CUDA init failed: %s", e)
            return False

    def _try_init_onnx(self) -> bool:
        """Try loading model via ONNX Runtime for CPU inference."""
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                self.model_name,
                backend="onnx",
                device="cpu",
                trust_remote_code=True,
            )

            probe = self._model.encode(["probe"], normalize_embeddings=True)
            self.dim = probe.shape[1]

            self._mode = "onnx"
            logger.info("Embedder ready: ONNX CPU, dim=%d", self.dim)
            return True

        except Exception as e:
            logger.warning("ONNX init failed: %s", e)
            return False

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """
        Embed a list of texts for indexing (document mode).

        Applies 'search_document:' prefix for task-aware nomic models.
        Returns float16 numpy array of shape [N, dim].
        """
        if not texts:
            return np.empty((0, self.dim), dtype=np.float16)

        prefixed = self._add_prefix(texts, "search_document: ")
        vectors = self._encode_with_backoff(prefixed)
        return vectors.astype(np.float16)

    def embed_query(self, text: str) -> np.ndarray:
        """
        Embed a single query text (query mode).

        Applies 'search_query:' prefix for task-aware nomic models.
        Returns float32 numpy array of shape [dim].
        """
        prefixed = self._add_prefix([text], "search_query: ")
        vectors = self._encode_with_backoff(prefixed)
        return vectors[0].astype(np.float32)

    def _add_prefix(self, texts: list[str], prefix: str) -> list[str]:
        """Add task-aware prefix if the model supports it."""
        if self._use_task_prefix:
            return [prefix + t for t in texts]
        return texts

    def _encode_with_backoff(self, texts: list[str]) -> np.ndarray:
        """
        Encode texts with token-budget batching and OOM backoff.

        On CUDA OOM: halves batch size, clears cache, retries.
        """
        all_vectors = []

        with skip_signal.watching("embed OOM backoff"):
            for batch in self.batch_manager.create_batches(texts):
                while True:
                    try:
                        result = self._model.encode(
                            batch,
                            batch_size=len(batch),
                            show_progress_bar=False,
                            convert_to_numpy=True,
                            normalize_embeddings=True,
                        )
                        all_vectors.append(np.asarray(result, dtype=np.float32))
                        break
                    except RuntimeError as exc:
                        if "out of memory" not in str(exc).lower():
                            raise
                        if self.batch_manager.max_batch_size <= self.batch_manager.min_batch_size:
                            raise
                        if skip_signal.pressed():
                            logger.warning(
                                "embed: skip requested during OOM backoff, re-raising to abort this batch"
                            )
                            raise

                        old_size = self.batch_manager.max_batch_size
                        self.batch_manager.reduce_batch_size()
                        logger.warning(
                            "OOM backoff: batch %d -> %d",
                            old_size, self.batch_manager.max_batch_size,
                        )

                        try:
                            import torch
                            torch.cuda.empty_cache()
                        except ImportError:
                            pass

                        # Re-batch this chunk of texts with smaller size
                        sub_batches = self.batch_manager.create_batches(batch)
                        for sub in sub_batches:
                            result = self._model.encode(
                                sub,
                                batch_size=len(sub),
                                show_progress_bar=False,
                                convert_to_numpy=True,
                                normalize_embeddings=True,
                            )
                            all_vectors.append(np.asarray(result, dtype=np.float32))
                        break

        if len(all_vectors) == 1:
            return all_vectors[0]
        return np.concatenate(all_vectors, axis=0)

    @property
    def mode(self) -> str:
        """Current inference mode: 'cuda', 'onnx', or 'uninitialized'."""
        return self._mode
