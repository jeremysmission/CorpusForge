"""Export and checkpoint helpers — the Forge side of the V2 handoff.

Stage 9 of the Forge pipeline plus the crash-safety layer that keeps
earlier work safe.

Modules:
  - ``packager``         : writes the final ``export_YYYYMMDD_HHMM``
                           folder that V2 consumes (chunks.jsonl,
                           vectors.npy, entities.jsonl, manifest.json).
  - ``chunk_checkpoint`` : an append-only JSONL store that keeps parsed
                           and chunked work on disk between stages so a
                           stop or crash before embed/export does not
                           throw away hours of effort.
"""
