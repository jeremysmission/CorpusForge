"""Document-level dedup — a recovery-stage helper, separate from stage 2.

The ``download.deduplicator`` module runs during the pipeline at stage
2 and handles fast hash-based dedup of identical files. This package,
by contrast, is used in a recovery pass that parses suspected
duplicates (same-stem families like ``Report.docx`` vs ``Report.pdf``)
and decides which copy to treat as canonical based on parse quality
and normalized text similarity.

Operators typically only run this during corpus-cleanup work, not on
every pipeline run.
"""
