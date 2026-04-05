"""
Contextual enrichment — prepend LLM-generated context preambles to chunks.

For each chunk, sends the full document context (or a surrounding window if the
document exceeds the model's context limit) plus the chunk text to a local LLM.
The LLM generates a 50-100 token preamble describing where the chunk sits within
the document.  This preamble is prepended to the chunk text before embedding,
improving retrieval accuracy by ~67%.

Uses Ollama phi4:14b-q4_K_M via its OpenAI-compatible API endpoint.
Graceful degradation: if Ollama is unreachable, chunks pass through unchanged.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# phi4 has 16K context window.  Reserve ~2K for the prompt template + output,
# leaving ~14K for document context.  At ~4 chars/token, that's ~56K chars.
# We use a conservative 5000-token budget (~20K chars) when the doc is too big,
# giving plenty of headroom for the prompt envelope.
_MAX_DOC_TOKENS = 14_000
_CHARS_PER_TOKEN_ESTIMATE = 4
_MAX_DOC_CHARS = _MAX_DOC_TOKENS * _CHARS_PER_TOKEN_ESTIMATE  # 56K chars

# When the document exceeds _MAX_DOC_CHARS, extract a window of this many
# tokens (in chars) centered on the chunk.
_WINDOW_TOKENS = 5000
_WINDOW_CHARS = _WINDOW_TOKENS * _CHARS_PER_TOKEN_ESTIMATE  # 20K chars

_PROMPT_TEMPLATE = """\
<document>
{document_context}
</document>
Here is the chunk we want to situate within the whole document:
<chunk>
{chunk_content}
</chunk>
Please give a short succinct context to situate this chunk within the overall \
document for the purposes of improving search retrieval of the chunk. Answer \
only with the succinct context and nothing else."""


@dataclass
class EnricherConfig:
    """Parameters for contextual enrichment — mirrors config.schema.EnrichConfig."""

    enabled: bool = True
    ollama_url: str = "http://127.0.0.1:11434"
    model: str = "phi4:14b-q4_K_M"
    max_chunk_chars: int = 500


class ContextualEnricher:
    """
    Generate contextual preambles for document chunks via a local LLM.

    Designed for the CorpusForge pipeline:
      chunker output → **enricher** → embedder input

    Each chunk gets an ``enriched_text`` field:
        "{preamble}\\n\\n{original_chunk_text}"
    """

    def __init__(self, config: EnricherConfig | None = None):
        self.config = config or EnricherConfig()
        self._client = None
        self._available = False

        if self.config.enabled:
            self._init_client()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _init_client(self) -> None:
        """Create an OpenAI SDK client pointed at the local Ollama instance."""
        try:
            from openai import OpenAI

            base_url = self.config.ollama_url.rstrip("/") + "/v1"
            self._client = OpenAI(
                base_url=base_url,
                api_key="ollama",
            )

            # Quick health check — list models to verify Ollama is running
            self._client.models.list()
            self._available = True
            logger.info(
                "Contextual enricher ready: %s via %s",
                self.config.model,
                base_url,
            )
        except Exception as exc:
            self._available = False
            logger.warning(
                "Ollama unavailable — enrichment disabled (graceful degradation). "
                "Error: %s",
                exc,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enrich_chunks(
        self,
        chunks: list[dict],
        doc_texts: dict[str, str],
    ) -> list[dict]:
        """
        Enrich a list of chunk dicts with contextual preambles.

        Parameters
        ----------
        chunks : list[dict]
            Chunk dicts from the pipeline.  Must contain ``text`` and
            ``source_path`` keys.
        doc_texts : dict[str, str]
            Mapping of source_path → full document text, used as context
            for the LLM prompt.

        Returns
        -------
        list[dict]
            The same chunk dicts, with ``enriched_text`` populated where
            enrichment succeeded.
        """
        if not self.config.enabled:
            logger.info("Enrichment disabled in config — passing chunks through.")
            return chunks

        if not self._available:
            logger.warning("Ollama not available — returning chunks unchanged.")
            return chunks

        total = len(chunks)
        enriched_count = 0
        failed_count = 0
        start = time.time()

        logger.info("Starting contextual enrichment for %d chunks...", total)

        batch_size = 10
        for batch_start in range(0, total, batch_size):
            batch_end = min(batch_start + batch_size, total)
            batch = chunks[batch_start:batch_end]

            for chunk in batch:
                source = chunk["source_path"]
                doc_text = doc_texts.get(source, "")
                chunk_text = chunk["text"]

                preamble = self._generate_preamble(doc_text, chunk_text)
                if preamble:
                    chunk["enriched_text"] = f"{preamble}\n\n{chunk_text}"
                    enriched_count += 1
                else:
                    failed_count += 1

            # Progress logging per batch
            processed = min(batch_end, total)
            elapsed = time.time() - start
            rate = processed / elapsed if elapsed > 0 else 0
            logger.info(
                "Enrichment progress: %d/%d chunks (%.1f chunks/sec)",
                processed,
                total,
                rate,
            )

        elapsed = time.time() - start
        logger.info(
            "Enrichment complete: %d/%d enriched, %d failed, %.1fs elapsed",
            enriched_count,
            total,
            failed_count,
            elapsed,
        )

        return chunks

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _generate_preamble(self, doc_text: str, chunk_text: str) -> str | None:
        """
        Call the LLM to generate a contextual preamble for one chunk.

        Returns the preamble string, or None on failure.
        """
        document_context = self._extract_context(doc_text, chunk_text)
        # Optionally truncate the chunk text sent to the model for speed
        chunk_for_prompt = chunk_text[: self.config.max_chunk_chars]

        prompt = _PROMPT_TEMPLATE.format(
            document_context=document_context,
            chunk_content=chunk_for_prompt,
        )

        try:
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=150,
            )
            preamble = response.choices[0].message.content.strip()
            # Basic sanity check — preamble should be non-empty and reasonable
            if preamble and len(preamble) > 10:
                return preamble
            logger.debug("Preamble too short or empty, skipping chunk.")
            return None

        except Exception as exc:
            logger.debug("Enrichment call failed: %s", exc)
            return None

    def _extract_context(self, doc_text: str, chunk_text: str) -> str:
        """
        Extract the document context to include in the prompt.

        If the full document fits within the model's context budget, use it
        entirely.  Otherwise, extract a window of ~5000 tokens centered on
        the chunk's position within the document.
        """
        if len(doc_text) <= _MAX_DOC_CHARS:
            return doc_text

        # Find chunk position in the document
        chunk_pos = doc_text.find(chunk_text[:200])
        if chunk_pos < 0:
            # Fallback: use first _WINDOW_CHARS of the doc
            return doc_text[:_WINDOW_CHARS]

        # Center the window on the chunk
        half_window = _WINDOW_CHARS // 2
        window_start = max(0, chunk_pos - half_window)
        window_end = min(len(doc_text), chunk_pos + len(chunk_text) + half_window)

        # Adjust if we're near the edges
        if window_start == 0:
            window_end = min(len(doc_text), _WINDOW_CHARS)
        elif window_end == len(doc_text):
            window_start = max(0, len(doc_text) - _WINDOW_CHARS)

        context = doc_text[window_start:window_end]

        # Add markers if we truncated
        prefix = "... " if window_start > 0 else ""
        suffix = " ..." if window_end < len(doc_text) else ""

        return f"{prefix}{context}{suffix}"
