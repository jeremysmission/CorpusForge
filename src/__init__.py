"""Top-level package for the CorpusForge pipeline.

Plain-English overview
----------------------
CorpusForge (Forge) is the ingest pipeline that feeds HybridRAG V2. An
operator points Forge at a folder of mixed-format documents and Forge
walks them through a nine-step pipeline:

    1. hash   - fingerprint every file with SHA-256
    2. dedup  - drop files that are unchanged since last run or that are
                duplicates of each other
    3. skip   - set aside files Forge cannot or should not parse
                (encrypted, image-only, oversize, temp files, etc.)
    4. parse  - turn each supported file into clean text
    5. chunk  - slice that text into retrieval-sized passages
    6. enrich - optionally ask a local LLM to describe where each chunk
                sits inside its document (improves search quality)
    7. embed  - convert chunks (or enriched chunks) into float16 vectors
    8. extract- optionally pull candidate entities from chunk text
    9. export - write chunks.jsonl + vectors.npy + manifests to a
                timestamped export folder for V2 to pick up

Subpackages map onto these stages. See each subpackage's ``__init__``
module and the ``pipeline`` module for the orchestrator.
"""
