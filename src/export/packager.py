"""
Export packager — builds the package consumed by HybridRAG V2.

Output structure:
  data/output/export_YYYYMMDD_HHMM/
    chunks.jsonl        — chunk text, metadata, enriched_text
    vectors.npy         — float16 numpy array [N, 768]
    entities.jsonl      — candidate entities (when extraction enabled)
    manifest.json       — version, model info, chunk count, stats

A symlink 'latest' points to the most recent successful export.

All file writes use encoding="utf-8", newline="\\n" per repo rules.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import numpy as np


class Packager:
    """Builds the export package for V2 consumption."""

    def __init__(self, output_dir: str = "data/output"):
        self.output_dir = Path(output_dir)

    def export(
        self,
        chunks: list[dict],
        vectors: np.ndarray,
        entities: list[dict] | None = None,
        stats: dict | None = None,
    ) -> Path:
        """
        Write all artifacts to a timestamped output directory.

        Returns the path to the export directory.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        export_dir = self.output_dir / f"export_{timestamp}"
        export_dir.mkdir(parents=True, exist_ok=True)

        self._write_chunks(export_dir, chunks)
        self._write_vectors(export_dir, vectors)
        self._write_entities(export_dir, entities or [])
        self._write_manifest(export_dir, chunks, vectors, entities or [], stats or {})
        self._update_latest_link(export_dir)

        return export_dir

    def _write_chunks(self, export_dir: Path, chunks: list[dict]) -> None:
        """Write chunks.jsonl — one JSON object per line."""
        path = export_dir / "chunks.jsonl"
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    def _write_vectors(self, export_dir: Path, vectors: np.ndarray) -> None:
        """Write vectors.npy — float16 numpy array."""
        path = export_dir / "vectors.npy"
        np.save(str(path), vectors.astype(np.float16))

    def _write_entities(self, export_dir: Path, entities: list[dict]) -> None:
        """Write entities.jsonl — candidate entities with confidence scores."""
        path = export_dir / "entities.jsonl"
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for entity in entities:
                f.write(json.dumps(entity, ensure_ascii=False) + "\n")

    def _write_manifest(
        self,
        export_dir: Path,
        chunks: list[dict],
        vectors: np.ndarray,
        entities: list[dict],
        stats: dict,
    ) -> None:
        """Write manifest.json — metadata about this export."""
        manifest = {
            "version": "1.0",
            "timestamp": datetime.now().isoformat(),
            "chunk_count": len(chunks),
            "vector_dim": int(vectors.shape[1]) if vectors.ndim == 2 else 0,
            "vector_dtype": "float16",
            "embedding_model": "nomic-embed-text-v1.5",
            "entity_count": len(entities),
            "stats": stats,
        }
        path = export_dir / "manifest.json"
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
            f.write("\n")

    def _update_latest_link(self, export_dir: Path) -> None:
        """Update 'latest' symlink to point to this export."""
        latest = self.output_dir / "latest"
        try:
            if latest.exists() or latest.is_symlink():
                if latest.is_symlink():
                    latest.unlink()
                elif latest.is_file():
                    latest.unlink()
            # On Windows, symlinks may need admin. Fall back to writing path.
            try:
                latest.symlink_to(export_dir.resolve())
            except OSError:
                # Fallback: write a text file with the path
                with open(latest, "w", encoding="utf-8", newline="\n") as f:
                    f.write(str(export_dir.resolve()))
        except Exception:
            pass  # Non-critical — V2 can find exports by timestamp
