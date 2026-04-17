"""Chunking helpers — stage 5 of the Forge pipeline.

After a parser produces clean text for a document, the chunker in this
package splits that text into overlapping passages sized for the
embedding model. Each chunk is given a stable, deterministic ID so the
same file always produces the same IDs and resume is crash-safe.

Modules:
  - ``chunker``    : splits text with smart paragraph/sentence
                     boundaries and an optional prepended heading.
  - ``chunk_ids``  : turns (file path, mtime, span, text) into a
                     repeatable 64-character SHA-256 ID.
"""
