# Forge -> V2 Metadata Contract — 2026-04-12

## Purpose

Tight-scope audit of the CorpusForge export surface that HybridRAG_V2 actually consumes today, plus the smallest safe contract fix worth landing on the Forge side.

## Evidence Base

- Live Forge export inspected: `C:\CorpusForge\data\production_output\export_20260409_0720`
- Forge emit path: `src/pipeline.py`, `src/export/packager.py`, `src/skip/skip_manager.py`
- Forge helpers/artifacts: `scripts/check_export_integrity.py`, `tools/inspect_export_quality.py`, `scripts/report_export_metadata_contract.py`
- V2 ingest/store/query path: `C:\HybridRAG_V2\scripts\import_embedengine.py`, `C:\HybridRAG_V2\src\store\lance_store.py`, `C:\HybridRAG_V2\scripts\canonical_rebuild_preflight.py`, `C:\HybridRAG_V2\scripts\import_forge_entities.py`, `C:\HybridRAG_V2\scripts\mine_query_anchors.py`, `C:\HybridRAG_V2\scripts\run_production_eval.py`, `C:\HybridRAG_V2\src\query\pipeline.py`
- V2 metadata target docs: `C:\HybridRAG_V2\docs\RETRIEVAL_METADATA_SCHEMA_SPRINT9_2026-04-10.md`, `C:\HybridRAG_V2\docs\RETRIEVAL_BASELINE_PROBE_V2_2026-04-11.md`, `C:\HybridRAG_V2\docs\PRODUCTION_EVAL_400_RATIONALE_2026-04-12.md`, `C:\HybridRAG_V2\docs\CANARY_INJECTION_METHODOLOGY_2026-04-12.md`

## Live Snapshot

`export_20260409_0720` is structurally valid for V2 import, but its live chunk schema is still minimal:

- `242,650` chunks across `17,134` unique source documents
- chunk rows contain exactly:
  - `chunk_id`
  - `text`
  - `enriched_text`
  - `source_path`
  - `chunk_index`
  - `text_length`
  - `parse_quality`
- no live chunk rows emit `source_ext`, `source_doc_hash`, authority/domain/archive metadata, visual-family metadata, identifier tokens, or logistics/cyber structured fields
- `skip_manifest.json` currently emits `total_skipped`, `counts_by_reason`, and `files`
- historical non-empty `entities.jsonl` rows emit `chunk_id`, `text`, `label`, `score`, `start`, `end`; they do not emit `source_path`

This matches the coordinator note: export/import is usable now, but V2 is still leaning on `source_path` heuristics because richer Forge metadata is not yet present in live exports.

## Compatibility Matrix

| Field / artifact | Emitted by Forge today | Consumed by V2 today | Likely value if added / used better | Incremental vs rebuild |
|---|---|---|---|---|
| `chunks.jsonl.chunk_id` | yes | yes | Core dedup/link key for LanceDB + entity import | already usable |
| `chunks.jsonl.text` | yes | yes | Retrieval payload, extraction input, eval context | already usable |
| `chunks.jsonl.source_path` | yes | yes, heavily | Provenance, path-grounded eval, routing heuristics, archive filtering, manual QA | already usable |
| `chunks.jsonl.enriched_text` | key yes, live values no | yes when present | Better FTS/context once enrichment is populated at scale | incremental, no rebuild required |
| `chunks.jsonl.chunk_index` | yes | yes | Stored in LanceDB, used by utilities like `minhash_dedup.py` | already usable |
| `chunks.jsonl.parse_quality` | yes | partial | Persisted now; can support ranking penalties later | incremental on V2 query side only |
| `chunks.jsonl.text_length` | yes | no | Audit/debug value only today | already emitted, low leverage |
| `manifest.json` core counts/model/timestamp | yes | partial | Import validation, operator visibility, ingest-integrity checks | already usable |
| `skip_manifest.json` current keys (`total_skipped`, `counts_by_reason`, `files`) | yes | mixed | `demo_gate.py` understands them, but import/preflight paths still under-read them | incremental |
| `skip_manifest.json` legacy aliases (`count`, `skipped_files`, `deferred_formats`) | live export no | yes in `import_embedengine.py` and `canonical_rebuild_preflight.py` | Restores operator-visible skip/defer summary without touching V2 | incremental, no rebuild required |
| `entities.jsonl` core rows (`chunk_id`, `label`, `score`, ...) | optional, but off in live export | optional via `import_forge_entities.py` | Useful for isolated entity import, but not part of default chunk ingest | incremental |
| `entities.jsonl.source_path` | no | backfilled indirectly | Would remove the extra chunk-map join during V2 entity import | incremental, no rebuild required |
| `source_ext` | no | no | Fast family/format routing without reparsing `source_path` everywhere | incremental, export rewrite + reimport only |
| `source_doc_hash` | no | no | Dedup lineage, per-document caps, canary isolation, future visual linkage | incremental, export rewrite + reimport only |
| authority/domain/archive/visual/table/OCR flags | no | no | Retires brittle `source_path LIKE` heuristics and enables family-aware retrieval | incremental for path/text-derived MVP; no vector rebuild required |
| identifier/date/site/program tokens | no | no | Exact lookup boosts, eval traceability, scoped filtering | incremental, export rewrite + reimport only |
| logistics/cyber structured fields | no | no | Highest leverage for bounded aggregation and export traceability | incremental if derived from existing chunk text; parser-native fidelity may need a re-parse |
| nightly delta canary matches / canary globs | yes on Forge delta reports | not in V2 import path | Useful for explicit canary isolation, but currently siloed outside chunk metadata | incremental, no rebuild required |

## What V2 Actually Uses Today

### Direct chunk/store contract

V2 hard-requires only `chunk_id`, `text`, and `source_path` at import time. It persists `chunk_index`, `parse_quality`, and `enriched_text` when present, but does not currently persist any richer metadata columns from the Sprint 9 schema.

### Path heuristics are still doing the real routing work

Current V2 code still derives important behavior from `source_path` text:

- `scripts/mine_query_anchors.py` groups entity results with `source_path LIKE '%Logistics%'`, `'%Cybersecurity%'`, `'%Drawings%'`, etc.
- `scripts/run_production_eval.py` judges family hits by checking signal tokens in `source_path` or chunk text.
- `src/query/pipeline.py` prioritizes or caps results based on path tokens instead of first-class metadata columns.
- `docs/RETRIEVAL_BASELINE_PROBE_V2_2026-04-11.md` explicitly recommends a secondary filename/path-aware retrieval path for code-like identifiers.

That is workable for the demo, but it is exactly why the current contract is underbuilt for family-aware routing.

### Skip-manifest contract is inconsistent across V2 consumers

There is a real schema mismatch today:

- Forge live exports write `total_skipped`, `counts_by_reason`, `files`
- V2 `demo_gate.py` already reads the new shape
- V2 `import_embedengine.py` and `canonical_rebuild_preflight.py` still expect `skipped_files` and `deferred_formats`

That means the skip/defer story is partially visible in V2 today, but not consistently.

## Highest-Leverage Improvements

### 1. Landed in Forge: backward-compatible skip-manifest aliases

`src/skip/skip_manager.py` now also emits:

- `count`
- `skipped_files`
- `deferred_formats`

This is the smallest safe contract fix because it improves current V2 import/preflight visibility without touching V2 code or changing chunk/vector alignment. It applies to newly written skip manifests. Existing exports would need a skip-manifest rewrite or a new export to pick it up.

### 2. Next metadata MVP: path-derived chunk fields

Best next emit pass:

- `source_ext`
- `business_domain`
- `is_archive_derived`
- `archive_class`
- `archive_depth`
- `is_visual_heavy`
- `visual_family`
- `table_heavy`

Why this set first:

- Forge already has enough `source_path` and extension evidence to emit them safely
- V2 already has clear path-based heuristics these fields could replace
- this is incremental work; it does not require re-embedding vectors

### 3. Next lineage pass: stable document identity + exact-match helpers

Best second emit pass:

- `source_doc_hash`
- `identifier_tokens`
- `site_token`
- `program_token`

Why this set next:

- it improves provenance, dedup lineage, per-document caps, and eval traceability
- it strengthens bounded aggregation and canary isolation without widening into general architecture work

## Incremental vs Rebuild-Requiring

### Incremental, no vector rebuild required

- skip-manifest alias normalization
- `source_ext`
- path-derived authority/domain/archive/visual/table flags
- `source_doc_hash` if pulled from existing file-hash state
- `identifier_tokens` if mined from existing chunk text / `source_path`
- V2 import/store acceptance of the extra columns

### Likely needs a re-parse, but still not a re-embed

- parser-native table metadata such as `sheet_name`, row/header lineage, or stronger OCR provenance
- structured logistics/cyber fields if the team wants parser fidelity instead of chunk-text regex backfill

### Not justified for this lane

- general Forge architecture changes
- broad V2 query architecture changes
- anything that forces a full corpus rebuild before the May 2 demo

## Reusable Helper

Use the new inspection helper to audit any export package:

```powershell
python scripts/report_export_metadata_contract.py `
  --export-dir data/production_output/export_20260409_0720 `
  --output-json %TEMP%\forge_v2_metadata_contract.json
```

It reports:

- live chunk-field coverage
- skip-manifest shape and alias presence
- entity artifact shape
- obvious contract gaps against the planned Sprint 9 metadata set

## Bottom Line

Forge -> V2 is valid for the current retrieval-first demo because the minimal contract is intact: chunks, vectors, manifest, and provenance path all line up. The real gap is not “can V2 import this?”; it is “how much of V2’s routing/eval/provenance story still depends on parsing `source_path` strings because richer metadata is absent?”

Today that answer is: still too much. The safe lane forward is incremental, not rebuild-heavy:

1. keep the minimal contract stable
2. normalize skip-manifest compatibility
3. add path-derived metadata first
4. add document lineage and identifier helpers next
