"""
Token-budget batch manager — ported from V1.

Packs texts into variable-sized batches that fit a GPU token budget.
Short texts batch larger (more GPU utilization), long texts batch
smaller (less OOM risk). Snowflake measured 16x throughput gain.

Token estimation: chars / 4 (conservative heuristic, avoids needing
the actual tokenizer on the hot path).
"""

from __future__ import annotations


class BatchManager:
    """Manages token-budget batching for embedding."""

    def __init__(
        self,
        token_budget: int = 49152,
        max_batch_size: int = 256,
        min_batch_size: int = 8,
    ):
        self.token_budget = token_budget
        self.max_batch_size = max_batch_size
        self.min_batch_size = min_batch_size

    def create_batches(self, texts: list[str]) -> list[list[str]]:
        """
        Pack texts into batches that fit the token budget.

        Returns list of text batches, each sized to fill but not exceed
        the token budget, clamped to [min_batch_size, max_batch_size].
        """
        batches = []
        i = 0
        n = len(texts)

        while i < n:
            budget_remaining = self.token_budget
            j = i

            while j < n and (j - i) < self.max_batch_size:
                est_tokens = max(1, len(texts[j]) // 4)
                if budget_remaining - est_tokens < 0 and (j - i) >= self.min_batch_size:
                    break
                budget_remaining -= est_tokens
                j += 1

            # Ensure at least min_batch_size (even if over budget)
            if (j - i) < self.min_batch_size and j < n:
                j = min(n, i + self.min_batch_size)

            batches.append(texts[i:j])
            i = j

        return batches

    def reduce_batch_size(self) -> None:
        """Halve max batch size on OOM. Floor at min_batch_size."""
        new_size = max(self.min_batch_size, self.max_batch_size // 2)
        self.max_batch_size = new_size
