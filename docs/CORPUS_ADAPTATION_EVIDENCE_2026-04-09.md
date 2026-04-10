# Corpus Adaptation Evidence 2026-04-09

Purpose: turn the current baseline sample note plus tonight's Forge artifacts into a generic evidence packet that can guide later hardening without disclosing source-specific details.

## Boundary

This is an evidence pass, not a policy pass.

It is meant to answer:

1. what generic document families dominate
2. which families are likely table-heavy, narrative, drawing-heavy, or image-heavy
3. which metadata fields are worth carrying forward into retrieval
4. where family-aware routing in V2 is likely to help

It does not justify:

1. new broad auto-skip rules by itself
2. corpus-specific folder heuristics
3. fake throughput or quality claims

## Inputs Used

### Baseline sample profile

The starting baseline was the existing 2026-04-09 sample profile note from a small mixed corpus sample:

- `533` files
- top extensions: `.drawio`, `.jpg`, `.pdf`, `.png`, `.xml`
- strong early signals:
  - drawing/diagram assets: `190`
  - image assets: `174`
  - thumbnail/cache assets: `38`
  - encrypted-PDF naming cues: `20`
  - OCR sidecars:
    - `_djvu.txt = 5`
    - `_djvu.xml = 3`
    - `_hocr.html = 3`

What that baseline told us:

- small samples can look drawing-heavy and image-heavy very quickly
- OCR derivatives exist, but the baseline alone does not prove they dominate
- a family-aware strategy needs to separate visual assets from text-bearing records early

### Broader private source-tree profile

The broader private source-tree pass was generated with:

- `scripts/profile_source_corpus.py`

Measured profile summary from that pass:

- `53,750` files
- `92,197,514,524` bytes
- top extensions:
  - `.jpg = 28,969`
  - `.zip = 13,102`
  - `.sao = 2,776`
  - `.rsf = 2,758`
  - `.pdf = 2,264`
  - `.docx = 829`
  - `.xlsx = 532`
- top signals:
  - `image_asset = 30,197`
  - `archive_container = 13,104`

### Tonight's Forge export artifacts

The current clean export package used for this pass was:

- `data/production_output/export_20260409_0720/manifest.json`
- `data/production_output/export_20260409_0720/run_report.txt`
- `data/production_output/export_20260409_0720/skip_manifest.json`
- `data/production_output/export_20260409_0720/chunks.jsonl`

Available failure evidence came from the local failure artifact:

- `data/production_output/export_20260409_0103/failures_run5.txt`

Important limitation:

- the clean `export_20260409_0720` package does not include a fresh per-file failure list
- failure taxonomy in this packet therefore uses the available on-disk failure artifact from the earlier run

## What The Evidence Actually Says

### 1. Raw file-count dominance and retrieval-weight dominance are different

From the broader source-tree profile:

- the raw corpus shape is dominated by images and archives
- binary sensor-style formats are present in large numbers
- spreadsheets are present, but they are not the raw file-count leader

From the clean export package:

- `17,134` parsed source docs
- `242,650` chunks
- chunk counts by source extension:
  - `.xlsx = 189,862`
  - `.jpg = 14,623`
  - `.pdf = 14,324`
  - `.txt = 11,201`
  - `.rtf = 5,194`
  - `.doc = 2,549`
  - `.docx = 2,251`

Interpretation:

- raw file count says "image/archive-heavy"
- retrieval surface says "spreadsheet-heavy operational records dominate"
- any future adaptation work that only looks at file counts will overreact to visual and archive families

### 2. Generic document families that dominate

Measured family-level results from the export artifacts:

| Generic family | Source docs | Chunks | What it means |
|---|---:|---:|---|
| operational support / travel-admin records | 549 | 177,181 | a small number of record packs drive most retrievable text |
| inventory / manifest records | 54 | 17,922 | compact but very dense table-bearing material |
| image / photo assets | 13,442 | 13,494 | massive by file count, almost always low-text |
| drawing / diagram assets | 690 | 784 | present often enough to deserve routing treatment, but not a chunk-volume leader |
| archive-derived bundles | 159 | 2,338 | not dominant, but large enough to flood answers without caps |
| logs / console-style text | 16 | 1,410 | small family, but high-value for exact technical lookups |

Measured conclusion:

- operational record families dominate retrieval weight
- image and drawing families dominate file presence far more than they dominate text value
- archive-derived material is real enough to matter, but not yet strong enough to justify automatic suppression

### 3. Which families are table-heavy, narrative, drawing-heavy, or image-heavy

| Family | Evidence | Likely shape | Confidence level |
|---|---|---|---|
| operational support / travel-admin records | `.xlsx` contributes `189,862` chunks; path-level signals such as packing lists, itineraries, receipts, and site inventory are common | strongly table-heavy, often row-oriented with repeated headers | high |
| inventory / manifest records | `54` docs create `17,922` chunks | strongly table-heavy, identifier-rich, record lookup friendly | high |
| narrative reference material | `.pdf`, `.doc`, `.docx`, `.txt`, `.rtf` are all present in the export tail; the small baseline sample also includes engineering/reference folders and prose-friendly extensions | mostly narrative or mixed section/table documents; important, but not the dominant chunk producer in tonight's export | medium |
| drawings / diagrams | baseline sample is drawing-heavy; export has `690` docs but only `784` chunks | drawing/image-heavy with sparse text, title-block metadata, or companion notes | high |
| image / photo assets | `13,442` docs produce `13,494` chunks; `.jpg`, `.png`, `.jpeg` average about `1.0` chunk per document | image-heavy, usually metadata-only or one very short chunk | high |
| archive-derived bundles | `159` docs, `2,338` chunks, plus repeated basenames and explicit archive path clues | mixed; often duplicate or near-duplicate descendants of more useful source documents | medium |

Practical reading:

- table-heavy families should not be treated as ordinary semantic prose
- narrative families still matter, but they are not where most chunk volume landed in this export
- drawings and images should stay queryable without being allowed to dominate default retrieval

### 4. Failure and junk signals

Measured skip and failure evidence:

- clean export skip reasons:
  - `Deferred by config for this run = 2,767`
  - `temp file prefix '~$' = 43`
  - `encrypted file detected = 3`
- dominant deferred extensions:
  - `.sao = 1,388`
  - `.rsf = 1,379`
- available failure artifact summary:
  - `.xml = 314`
  - `.pdf = 145`
  - `.docx = 60`
  - `.pptx = 12`
  - `.xlsx = 2`
  - `.zip = 1`

Measured interpretation:

- binary sensor-style formats remain the clearest explicit defer class
- repetitive telemetry/BIT-style XML is a plausible next defer candidate, but this pass does not prove it strongly enough for a blanket rule
- scanned PDFs remain a quality risk where OCR/tooling is weak or absent
- OCR sidecars are real in the small baseline sample, but they did not present as the dominant clutter class in the broader profile or the clean export

### 5. Duplicate evidence

What was proven:

- exact recursive folder-signature duplicates in the broader profile: `0`
- repeated archive-derived material in the export: present
- repeated basenames in the export: present

What was not proven:

- a strong exact bundle-signature rule that can safely auto-skip whole archive-derived trees

Result:

- keep archive duplicate work in audit mode
- promote bundle caps and visibility before any aggressive suppression

## Metadata Worth Carrying Into Retrieval

These fields have direct evidence behind them:

| Metadata field | Why it matters |
|---|---|
| `document_family` | core routing key for separating table-heavy records, narrative references, drawings, images, logs, and archive-derived material |
| `family_confidence` | prevents weak family guesses from oversteering retrieval |
| `source_extension` | the export is heavily skewed by extension, especially `.xlsx` |
| `source_doc_id` or stable file hash | needed for dedup, per-document caps, and provenance |
| `table_heavy` | justified by spreadsheet chunk density and row-oriented answer needs |
| `table_id`, `row_index`, `header_tokens`, `sheet_name` | keeps row-level answers intact instead of turning them into generic text windows |
| `section_path` or `heading_path` | improves narrative ranking and citation grouping |
| `page_number` or `sheet_name` | useful for record narrowing, citations, and drawing references |
| `archive_derived` plus `bundle_signature` | supports caps and audit-first archive handling |
| `image_or_metadata_only` | helps suppress low-text assets in broad semantic retrieval |
| `is_drawing_like` plus title-block tokens | enables asset lookup without flooding prose search |
| `parse_quality` | low-quality chunks should not compete equally with clean text |
| `is_ocr` and `ocr_confidence` | useful for ranking and fallback behavior on scans |
| `identifier_tokens` | critical for exact lookup over manifests, inventory, and operational records |
| `reused_basename_flag` | useful when archive descendants repeat the same logical document many times |

## Where Family-Aware Query Routing Would Likely Help In V2

### Structured-first routing for operational records

This is the clearest win.

Why:

- `603` operational-table families (`549` operational support + `54` inventory/manifest) account for `195,103` chunks
- those families are more naturally answered as rows, not arbitrary semantic windows

Expected effect:

- route exact status, shipment, inventory, date, and identifier questions to table/entity paths first
- keep vector retrieval as supporting context, not the primary answer unit

### Semantic-first routing for narrative reference material

Narrative material is present, but it is not the dominant chunk producer in tonight's export.

Expected effect:

- keep procedures, troubleshooting, and explanatory questions in the semantic path
- avoid polluting narrative answers with high-volume operational rows unless the query explicitly asks for a record

### Metadata-first routing for drawings and diagram assets

Why:

- drawings are common enough to matter
- they are low-text enough that ordinary semantic retrieval will usually rank them badly or flood the result set with weak chunks

Expected effect:

- use title-block, revision, sheet, and identifier metadata first
- allow text fallback only when the operator explicitly wants a drawing-like result or provides an exact asset identifier

### Suppression and caps for images and archive-derived bundles

Why:

- image/photo assets are abundant but low-text
- archive-derived descendants can multiply nearly identical evidence

Expected effect:

- do not let image-only or archive-derived material dominate broad semantic searches
- cap repeated results by source document and bundle

### Quality-aware handling for OCR and failure-prone families

Why:

- scanned PDFs and telemetry/BIT-style XML show up in the failure evidence

Expected effect:

- low-quality OCR or weak-parse families should be down-ranked or surfaced with lower trust
- they should not silently disappear, but they also should not compete with clean table or narrative evidence on equal terms

## Safe Conclusions

What this packet supports now:

1. carry family and quality metadata forward from Forge into V2
2. treat operational tables, narratives, drawings, images, and archive-derived material as different retrieval shapes
3. keep archive duplicate handling in audit-first mode
4. keep binary sensor-style families deferred
5. sample telemetry/BIT-style XML before promoting it to a broad defer rule

What this packet does not support yet:

1. broad archive auto-skip
2. a new OCR-sidecar defer rule based only on tonight's evidence
3. a claim that narrative families do not matter
4. any throughput claim beyond the artifact counts already recorded

## Code And Artifact Anchors

- source-tree profiler: `scripts/profile_source_corpus.py`
- baseline sample note: local 2026-04-09 corpus profile note
- clean export package:
  - `data/production_output/export_20260409_0720/manifest.json`
  - `data/production_output/export_20260409_0720/run_report.txt`
  - `data/production_output/export_20260409_0720/skip_manifest.json`
  - `data/production_output/export_20260409_0720/chunks.jsonl`
- failure artifact:
  - `data/production_output/export_20260409_0103/failures_run5.txt`

## Handoff Status 2026-04-09

- this lane stayed in docs/analysis scope
- no code changes were made in this pass
- this lane itself is isolated to new docs only
- repo-wide sanitizer verification still reports unrelated tracked docs outside Lane 4, but those files are not part of this lane's staged doc-only commit
- this CorpusForge half was later pushed as an isolated doc-only commit on 2026-04-10
- the next safe follow-on is to use this evidence packet to define a minimal metadata payload for Forge export and V2 import, then QA routing behavior against a fixed proof set

Signed: Agent Four | Lane 4
