"""Contextual enrichment — stage 6 of the Forge pipeline.

For each chunk, Forge can optionally ask a small local LLM (phi4 on
Ollama) to write a short paragraph describing where that chunk sits
inside its parent document. That paragraph is prepended to the chunk
text before embedding. In practice this raises retrieval accuracy by
roughly two thirds on heterogeneous corpora.

Enrichment is fully optional. If Ollama or the chosen model is not
available, chunks pass through unchanged and the pipeline continues.
"""

from .contextual_enricher import ContextualEnricher

__all__ = ["ContextualEnricher"]
