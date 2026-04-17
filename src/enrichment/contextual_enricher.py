"""
Contextual enrichment — prepend LLM-generated context preambles to chunks.

Plain-English role
------------------
Stage 6 of the pipeline, optional. For every chunk, Forge sends the
document text (or a window around the chunk if the doc is very long)
plus the chunk text to a local phi4 model running on Ollama. The model
responds with 50-100 tokens describing where the chunk sits in the
document. That preamble is glued onto the chunk before embedding so
the embedding vector captures document context as well as the chunk's
own words.

Graceful degradation: if Ollama or the chosen model is not reachable,
chunks pass through unchanged. The pipeline will have already failed
loudly at boot via ``probe_enrichment`` if enrichment is switched on
but cannot run.

Uses Ollama phi4:14b-q4_K_M via its OpenAI-compatible API endpoint.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import urlopen, Request

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
    max_concurrent: int = 2


@dataclass
class EnrichmentProbeResult:
    """Result of an enrichment readiness probe."""

    ollama_running: bool = False
    model_available: bool = False
    auto_started: bool = False
    error: str = ""

    @property
    def ready(self) -> bool:
        """True only when Ollama is running and the required model is present."""
        return self.ollama_running and self.model_available

    @property
    def status_text(self) -> str:
        """Human-readable one-line status for logs and the GUI."""
        if self.ready:
            return "ready"
        if not self.ollama_running:
            return f"Ollama not running ({self.error})"
        if not self.model_available:
            return f"Model not found ({self.error})"
        return self.error or "unknown"


def probe_enrichment(
    ollama_url: str = "http://127.0.0.1:11434",
    model: str = "phi4:14b-q4_K_M",
    auto_start: bool = True,
    start_timeout: int = 15,
) -> EnrichmentProbeResult:
    """
    Probe Ollama readiness for enrichment. No external dependencies (stdlib only).

    Steps:
      1. GET /api/version — is Ollama running?
      2. If not and auto_start → spawn `ollama serve`, wait up to start_timeout seconds
      3. GET /api/tags — is the required model available?

    Returns EnrichmentProbeResult with status details.
    """
    result = EnrichmentProbeResult()
    base = ollama_url.rstrip("/")

    # Step 1: Check if Ollama is running
    if _ollama_is_running(base):
        result.ollama_running = True
    elif auto_start:
        # Step 2: Attempt auto-start
        logger.info("Ollama not running — attempting auto-start...")
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except FileNotFoundError:
            result.error = "Ollama not installed. Install from ollama.com"
            return result
        except Exception as exc:
            result.error = f"Failed to start Ollama: {exc}"
            return result

        # Wait for Ollama to come up
        deadline = time.time() + start_timeout
        while time.time() < deadline:
            if _ollama_is_running(base):
                result.ollama_running = True
                result.auto_started = True
                logger.info("Ollama auto-started successfully.")
                break
            time.sleep(1)
        else:
            result.error = f"Ollama failed to start within {start_timeout}s"
            return result
    else:
        result.error = "Ollama not running"
        return result

    # Step 3: Check if model is available
    try:
        req = Request(f"{base}/api/tags", method="GET")
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        model_names = [m.get("name", "") for m in data.get("models", [])]
        # Match by prefix — "phi4:14b-q4_K_M" matches "phi4:14b-q4_K_M"
        # Also match short names like "phi4" against full tags
        model_base = model.split(":")[0]
        if any(model in name or name.startswith(model) for name in model_names):
            result.model_available = True
        elif any(name.startswith(model_base) for name in model_names):
            result.model_available = True
        else:
            result.error = (
                f"Model {model} not found. "
                f"Run: ollama pull {model}"
            )
            logger.warning("Available models: %s", model_names)
    except Exception as exc:
        result.error = f"Failed to query models: {exc}"

    return result


def _ollama_is_running(base_url: str) -> bool:
    """Quick check: is Ollama responding on its API port?"""
    try:
        req = Request(f"{base_url}/api/version", method="GET")
        with urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


class ContextualEnricher:
    """
    Generate contextual preambles for document chunks via a local LLM.

    Designed for the CorpusForge pipeline:
      chunker output → **enricher** → embedder input

    Each chunk gets an ``enriched_text`` field:
        "{preamble}\\n\\n{original_chunk_text}"
    """

    def __init__(self, config: EnricherConfig | None = None):
        """Check Ollama readiness on construction; disable enrichment gracefully if unreachable."""
        self.config = config or EnricherConfig()
        self._client = None
        self._available = False

        if self.config.enabled:
            self._init_client()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _init_client(self) -> None:
        """Verify Ollama is reachable (stdlib only — no openai SDK needed)."""
        try:
            base = self.config.ollama_url.rstrip("/")
            req = Request(f"{base}/api/version", method="GET")
            with urlopen(req, timeout=5) as resp:
                if resp.status != 200:
                    raise ConnectionError("Ollama returned non-200")
            self._available = True
            logger.info(
                "Contextual enricher ready: %s via %s",
                self.config.model,
                base,
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
        max_workers = self.config.max_concurrent

        logger.info(
            "Starting contextual enrichment for %d chunks (%d concurrent workers)...",
            total, max_workers,
        )

        def _enrich_one(idx: int) -> tuple[int, str | None]:
            chunk = chunks[idx]
            source = chunk["source_path"]
            doc_text = doc_texts.get(source, "")
            chunk_text = chunk["text"]
            preamble = self._generate_preamble(doc_text, chunk_text)
            return idx, preamble

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_enrich_one, i): i for i in range(total)}
            done = 0
            for future in as_completed(futures):
                idx, preamble = future.result()
                if preamble:
                    chunks[idx]["enriched_text"] = f"{preamble}\n\n{chunks[idx]['text']}"
                    enriched_count += 1
                else:
                    failed_count += 1
                done += 1
                if done % 50 == 0 or done == total:
                    elapsed = time.time() - start
                    rate = done / elapsed if elapsed > 0 else 0
                    logger.info(
                        "Enrichment progress: %d/%d chunks (%.1f chunks/sec)",
                        done, total, rate,
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
            base = self.config.ollama_url.rstrip("/")
            payload = json.dumps({
                "model": self.config.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0, "num_predict": 150},
            }).encode("utf-8")
            req = Request(
                f"{base}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            preamble = data.get("message", {}).get("content", "").strip()
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
