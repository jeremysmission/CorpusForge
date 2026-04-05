"""
Pipeline orchestrator — runs all stages in sequence.

Minimal Slice 0.2 version: parse → chunk → embed → export.
Stages 1 (download), 2 (hash/dedup), 5 (enrich), 7 (extract) are stubs
that will be wired in during Sprint 1-2.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config.schema import ForgeConfig
from .chunk.chunker import Chunker
from .chunk.chunk_ids import make_chunk_id
from .embed.embedder import Embedder
from .export.packager import Packager
from .parse.parsers.txt_parser import TxtParser, ParsedDocument

logger = logging.getLogger(__name__)


@dataclass
class RunStats:
    """Tracks pipeline run statistics."""

    files_found: int = 0
    files_parsed: int = 0
    files_failed: int = 0
    chunks_created: int = 0
    vectors_created: int = 0
    elapsed_seconds: float = 0.0
    errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "files_found": self.files_found,
            "files_parsed": self.files_parsed,
            "files_failed": self.files_failed,
            "chunks_created": self.chunks_created,
            "vectors_created": self.vectors_created,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "error_count": len(self.errors),
        }


class Pipeline:
    """
    Orchestrates all pipeline stages.

    Slice 0.2 scope: parse → chunk → embed → export on a single file.
    """

    def __init__(self, config: ForgeConfig):
        self.config = config
        self.parser = TxtParser()
        self.chunker = Chunker(
            chunk_size=config.chunk.size,
            overlap=config.chunk.overlap,
            max_heading_len=config.chunk.max_heading_len,
        )
        self.embedder = Embedder(
            model_name=config.embed.model_name,
            dim=config.embed.dim,
            device=config.embed.device,
            max_batch_tokens=config.embed.max_batch_tokens,
            dtype=config.embed.dtype,
        )
        self.packager = Packager(output_dir=config.paths.output_dir)

    def run(self, input_files: list[Path]) -> RunStats:
        """
        Run the pipeline on a list of input files.

        Returns RunStats with processing results.
        """
        stats = RunStats()
        start_time = time.time()

        stats.files_found = len(input_files)

        # Stage 3: Parse
        parsed_docs = self._parse_files(input_files, stats)

        # Stage 4: Chunk
        all_chunks = self._chunk_documents(parsed_docs, stats)

        if not all_chunks:
            logger.warning("No chunks produced — nothing to embed or export.")
            stats.elapsed_seconds = time.time() - start_time
            return stats

        # Stage 6: Embed
        vectors = self._embed_chunks(all_chunks, stats)

        # Stage 8: Export
        export_dir = self.packager.export(
            chunks=all_chunks,
            vectors=vectors,
            entities=[],
            stats=stats.to_dict(),
        )
        logger.info("Export written to: %s", export_dir)

        stats.elapsed_seconds = time.time() - start_time
        return stats

    def _parse_files(
        self, files: list[Path], stats: RunStats
    ) -> list[ParsedDocument]:
        """Parse each file, isolating errors per file."""
        parsed = []
        for file_path in files:
            try:
                doc = self.parser.parse(file_path)
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
        """Chunk all parsed documents, generate deterministic IDs."""
        all_chunks = []
        for doc in docs:
            path = Path(doc.source_path)
            mtime_ns = path.stat().st_mtime_ns

            text_chunks = self.chunker.chunk_text(doc.text)

            for i, chunk_text in enumerate(text_chunks):
                chunk_start = doc.text.find(chunk_text[:100])
                chunk_end = chunk_start + len(chunk_text) if chunk_start >= 0 else i * self.config.chunk.size

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
                    "enriched_text": None,  # Sprint 2: phi4:14B enrichment
                    "source_path": doc.source_path,
                    "chunk_index": i,
                    "text_length": len(chunk_text),
                    "parse_quality": doc.parse_quality,
                })

        stats.chunks_created = len(all_chunks)
        return all_chunks

    def _embed_chunks(
        self, chunks: list[dict], stats: RunStats
    ) -> np.ndarray:
        """Embed all chunks, using text (enriched_text when available)."""
        texts = [c.get("enriched_text") or c["text"] for c in chunks]
        vectors = self.embedder.embed_batch(texts)
        stats.vectors_created = len(vectors)
        return vectors
