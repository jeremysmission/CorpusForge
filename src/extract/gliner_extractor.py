"""
GLiNER2 entity extraction — zero-shot NER with batch inference.

Extracts candidate entities from chunk text using GLiNER multi-v2.1.
Uses GLiNER's native batch inference (model.inference) which processes
multiple texts in parallel at the tensor level — faster than threading.

Batch size is config-driven (extract.batch_size in config.yaml / config.local.yaml)
so each machine can tune to its CPU/RAM capacity.

Output: list[dict] where each dict is one entity occurrence:
  {chunk_id, text, label, score, start, end}
"""

from __future__ import annotations

import logging
import time
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


class GlinerExtractor:
    """
    Zero-shot NER using GLiNER multi-v2.1.

    Designed for the CorpusForge pipeline:
      chunker output -> enricher -> embedder -> **extractor** -> export

    Each chunk produces zero or more entity candidates written to entities.jsonl.
    """

    def __init__(self, config: ExtractorConfig | None = None):
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

    def extract_entities(self, chunks: list[dict]) -> list[dict]:
        """
        Extract entities from all chunks using batch inference.

        Parameters
        ----------
        chunks : list[dict]
            Chunk dicts from the pipeline. Must contain 'chunk_id' and 'text'.

        Returns
        -------
        list[dict]
            Entity candidates: {chunk_id, text, label, score, start, end}
        """
        if not self.config.enabled:
            logger.info("Entity extraction disabled — skipping.")
            return []

        model = self._get_model()
        total = len(chunks)
        batch_size = self.config.batch_size
        start = time.time()
        all_entities: list[dict] = []

        logger.info(
            "Starting entity extraction on %d chunks (batch_size=%d, %d entity types, threshold=%.2f)...",
            total, batch_size, len(self.config.entity_types), self.config.min_confidence,
        )

        # Filter out chunks too short to have meaningful entities
        valid_chunks = [(i, c) for i, c in enumerate(chunks) if len(c.get("text", "")) >= 20]
        skipped = total - len(valid_chunks)
        if skipped:
            logger.info("Skipping %d chunks shorter than 20 chars.", skipped)

        # Process in batches using GLiNER's native batch inference
        for batch_start in range(0, len(valid_chunks), batch_size):
            batch = valid_chunks[batch_start:batch_start + batch_size]
            texts = [c["text"] for _, c in batch]
            chunk_ids = [c.get("chunk_id", "") for _, c in batch]

            try:
                batch_results = model.inference(
                    texts,
                    self.config.entity_types,
                    threshold=self.config.min_confidence,
                    batch_size=batch_size,
                )

                for chunk_id, entities_for_chunk in zip(chunk_ids, batch_results):
                    for ent in entities_for_chunk:
                        all_entities.append({
                            "chunk_id": chunk_id,
                            "text": ent["text"],
                            "label": ent["label"],
                            "score": round(ent["score"], 4),
                            "start": ent["start"],
                            "end": ent["end"],
                        })
            except Exception as exc:
                logger.warning(
                    "Batch extraction failed (chunks %d-%d): %s",
                    batch_start, batch_start + len(batch), exc,
                )

            # Progress logging
            processed = min(batch_start + len(batch), len(valid_chunks))
            if processed % (batch_size * 10) == 0 or processed == len(valid_chunks):
                elapsed = time.time() - start
                rate = processed / elapsed if elapsed > 0 else 0
                logger.info(
                    "Extraction progress: %d/%d chunks (%.1f chunks/sec, %d entities found)",
                    processed, len(valid_chunks), rate, len(all_entities),
                )

        elapsed = time.time() - start
        logger.info(
            "Extraction complete: %d entities from %d chunks in %.1fs (%.1f chunks/sec)",
            len(all_entities), total, elapsed, total / max(elapsed, 0.01),
        )

        return all_entities
