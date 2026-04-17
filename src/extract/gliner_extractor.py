"""
GLiNER2 entity extraction — zero-shot NER with concurrent batch inference.

Plain-English role
------------------
Stage 8 of the pipeline, optional. For every chunk text, this module
asks the GLiNER model "which of these labels appear in this text, and
where?" — labels come from the config (part numbers, people, sites,
dates, etc.). Each hit above the confidence threshold becomes one row
in ``entities.jsonl`` inside the export folder so V2 can seed its
knowledge graph.

Runs on CPU. Uses a pool of worker threads, each calling GLiNER's
native batched inference method.

Output: list[dict] where each dict is one entity occurrence:
  {chunk_id, text, label, score, start, end}
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ExtractorConfig:
    """Parameters for entity extraction — mirrors config.schema.ExtractConfig."""

    enabled: bool = False
    model_name: str = "urchade/gliner_multi-v2.1"
    entity_types: list[str] = field(default_factory=lambda: [
        "PART_NUMBER", "PERSON", "SITE", "DATE",
        "ORGANIZATION", "FAILURE_MODE", "ACTION",
    ])
    min_confidence: float = 0.5
    batch_size: int = 16
    max_concurrent: int = 4


class GlinerExtractor:
    """
    Zero-shot NER using GLiNER multi-v2.1 with concurrent workers.

    Each worker gets its own batch of chunks and calls model.inference().
    max_concurrent workers run simultaneously via ThreadPoolExecutor.
    """

    def __init__(self, config: ExtractorConfig | None = None):
        """Store the extractor config; the GLiNER model loads lazily on first use."""
        self.config = config or ExtractorConfig()
        self._model = None

    def _get_model(self):
        """Lazy-load the GLiNER model on first use (CPU only)."""
        if self._model is None:
            from gliner import GLiNER
            logger.info("Loading GLiNER model: %s (CPU)...", self.config.model_name)
            start = time.time()
            self._model = GLiNER.from_pretrained(self.config.model_name)
            logger.info("GLiNER loaded in %.1fs", time.time() - start)
        return self._model

    def _extract_batch(self, batch_chunks: list[tuple[int, dict]]) -> list[dict]:
        """Extract entities from a single batch of chunks."""
        model = self._get_model()
        texts = [c["text"] for _, c in batch_chunks]
        chunk_ids = [c.get("chunk_id", "") for _, c in batch_chunks]
        entities = []

        try:
            batch_results = model.inference(
                texts,
                self.config.entity_types,
                threshold=self.config.min_confidence,
                batch_size=self.config.batch_size,
            )
            for chunk_id, entities_for_chunk in zip(chunk_ids, batch_results):
                for ent in entities_for_chunk:
                    entities.append({
                        "chunk_id": chunk_id,
                        "text": ent["text"],
                        "label": ent["label"],
                        "score": round(ent["score"], 4),
                        "start": ent["start"],
                        "end": ent["end"],
                    })
        except Exception as exc:
            logger.warning("Batch extraction failed: %s", exc)

        return entities

    def extract_entities(self, chunks: list[dict]) -> list[dict]:
        """
        Extract entities from all chunks using concurrent batch workers.

        Splits chunks into work units of batch_size, then dispatches
        max_concurrent workers to process them in parallel.
        """
        if not self.config.enabled:
            logger.info("Entity extraction disabled — skipping.")
            return []

        self._get_model()  # Pre-load before threading
        total = len(chunks)
        batch_size = self.config.batch_size
        max_workers = self.config.max_concurrent
        start = time.time()
        all_entities: list[dict] = []

        logger.info(
            "Starting entity extraction on %d chunks (batch_size=%d, workers=%d, "
            "%d entity types, threshold=%.2f)...",
            total, batch_size, max_workers,
            len(self.config.entity_types), self.config.min_confidence,
        )

        # Filter out chunks too short to have meaningful entities
        valid_chunks = [(i, c) for i, c in enumerate(chunks) if len(c.get("text", "")) >= 20]
        skipped = total - len(valid_chunks)
        if skipped:
            logger.info("Skipping %d chunks shorter than 20 chars.", skipped)

        # Split into batches
        batches = []
        for batch_start in range(0, len(valid_chunks), batch_size):
            batches.append(valid_chunks[batch_start:batch_start + batch_size])

        # Dispatch batches to concurrent workers
        done_count = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(self._extract_batch, batch): i for i, batch in enumerate(batches)}
            for future in as_completed(futures):
                entities = future.result()
                all_entities.extend(entities)
                done_count += 1
                chunks_done = min(done_count * batch_size, len(valid_chunks))
                if done_count % max(len(batches) // 10, 1) == 0 or done_count == len(batches):
                    elapsed = time.time() - start
                    rate = chunks_done / elapsed if elapsed > 0 else 0
                    logger.info(
                        "Extraction progress: %d/%d chunks (%.1f chunks/sec, %d entities found)",
                        chunks_done, len(valid_chunks), rate, len(all_entities),
                    )

        elapsed = time.time() - start
        logger.info(
            "Extraction complete: %d entities from %d chunks in %.1fs (%.1f chunks/sec)",
            len(all_entities), total, elapsed, total / max(elapsed, 0.01),
        )

        return all_entities
