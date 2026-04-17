"""Shared runtime utilities (skip signals, etc.).

Note on naming: this package is about runtime controls the operator
presses during a run (for example the keypress used to abort the
embedder's OOM backoff loop early). It is intentionally kept separate
from ``src.skip``, which is the ingest-time "which files should we not
parse" logic.
"""
