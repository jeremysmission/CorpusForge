# Sprint 9.3 Retrieval Metadata Schema (Implementation-Ready)

Date: 2026-04-10  
Lane: reviewer  
Scope: V2 text retrieval metadata now, V3 visual linkage next

## 1) Evidence Base From Captures

Primary capture set:
- `{USER_HOME}\corpus_metadata_capture_2026-04-10\corpustransfr_metadata_capture_2026-04-10.json`
- `{USER_HOME}\corpus_metadata_capture_2026-04-10\corpustransfr_format_incomplete_encrypted_scan_2026-04-10.json`
- `{USER_HOME}\corpus_metadata_capture_2026-04-10\logistics_retrieval_capture_2026-04-10.json`
- `{USER_HOME}\corpus_metadata_capture_2026-04-10\cybersecurity_retrieval_capture_2026-04-10.json`

High-signal observations used by this schema:
- Corpus scale: `430,542` files, `~762 GB`.
- Dominant raw families: images + archives + PDFs + spreadsheets.
- Logistics subtree (`5.0 Logistics`) contains `15,145` files and is table-heavy.
- Logistics spreadsheet headers include strong filter fields (`CLIN`, `Vendor`, `Purchase Req #`, `Purchase Order #`, `PART NUMBER`, `MODEL NUMBER`, `OEM`, `NOMENCLATURE`, `QTY`, `SERIAL NUMBER`, acquisition and revision fields).
- DM/high-authority cues are present under `1.0 enterprise program DM - Restricted` and deliverable/CDRL naming.
- Archive signals are heavy (`Archive`, `zzSEMS ARCHIVE`, backup-style paths) and require down-weighting by default.
- Dedicated cybersecurity capture returned `file_count=0`; however, global capture still shows cybersecurity path cues (`3.0 Cybersecurity`, `ACAS`, `STIG`) that should be first-class metadata fields.
- Bounded GPU probe (`cuda:1`) on a representative sample from `C:\CorpusForge\data\production_output\export_20260409_0720` showed:
  - DM-authority targeting improved from `0.67` to `5.67` relevant hits in top-10 when authority/archive priors were applied.
  - Logistics targeting stayed high (`9.33` to `9.33`) while archive bleed dropped (`0.33` to `0.0`).
  - Cyber targeting is sparse in this sample and can regress if archive suppression is too aggressive (`1.33` to `1.0`), so cyber requires domain-specific penalty guards.

## 2) Metadata Contract Split (Forge vs V2)

This lane requires a hard split so implementation can be staged safely.

## 2.1 Forge Export Metadata (must be emitted per chunk/document)

These fields belong in Forge output so V2 can consume them without re-inference:

| Field | Type | Required | Notes |
|---|---|---|---|
| `source_path` | string | yes | Existing anchor field. |
| `source_ext` | string | yes | Lowercase extension (`.pdf`, `.xlsx`, etc.). |
| `source_doc_hash` | string | yes | Stable document-level hash for dedup lineage. |
| `chunk_id` | string | yes | Existing chunk key. |
| `authority_tier` | enum | yes | `dm_restricted`, `customer_deliverable`, `operational_working`, `archive_copy`, `unknown`. |
| `authority_signals` | string[] | yes | Cues used to set tier (`1.0 enterprise program DM - Restricted`, `CDRL`, `Deliverables`, etc.). |
| `business_domain` | enum | yes | `logistics`, `cybersecurity`, `program`, `engineering`, `site_visit`, `sysadmin`, `unknown`. |
| `archive_class` | enum | yes | `primary`, `archive_original`, `archive_duplicate`, `archive_bundle_member`. |
| `archive_depth` | int | yes | Path-derived archive depth (0 for non-archive). |
| `is_archive_derived` | bool | yes | Fast filter flag. |
| `is_visual_heavy` | bool | yes | True for low-text visual assets/families. |
| `visual_family` | enum | yes | `photo`, `drawing`, `cad`, `scan`, `mixed_visual`, `none`. |
| `table_heavy` | bool | yes | True for spreadsheet/row-first records. |
| `parse_quality` | float | yes | Existing quality signal, normalized 0..1. |
| `is_ocr` | bool | yes | OCR-derived chunk flag. |
| `doc_date` | string/null | no | ISO date if inferable from source/header/path. |
| `site_token` | string/null | no | Site hint for routing/filtering. |
| `program_token` | string/null | no | Program/system cue token. |
| `identifier_tokens` | string[] | no | DD250/PO/CLIN/part/model/serial token list. |

Logistics structured fields (document/chunk-level extracted metadata):
- `log_clin`
- `log_vendor`
- `log_purchase_req`
- `log_purchase_order`
- `log_part_number`
- `log_model_number`
- `log_oem`
- `log_nomenclature`
- `log_qty`
- `log_serial_number`
- `log_acquisition_contract_code`
- `log_acquisition_cost`
- `log_acquisition_date`
- `log_revision`
- `log_remarks`

Cybersecurity structured fields (where present):
- `cyber_report_family` (`acas`, `nessus`, `stig`, `rmf`, `poam`, `iavm`, `cci`, `waiver`, `other`)
- `cyber_scan_date`
- `cyber_system_scope`
- `cyber_site_scope`
- `cyber_finding_id`
- `cyber_severity`
- `cyber_status` (`open`, `mitigated`, `closed`, `exception`, `unknown`)
- `cyber_waiver_flag` (bool)

## 2.3 Candidate Regex / Structure Cues (Generic)

Use these cues for metadata population and query expansion. They are intentionally generic and non-sensitive.

Authority / deliverable cues:
- `(?i)\\bcdrl\\b`
- `(?i)\\bdd\\s*250\\b`
- `(?i)\\bdeliverable(s)?\\b`
- `(?i)\\bdata\\s+accession\\s+list\\b`
- Path cues: `\\1.0 enterprise program DM - Restricted\\`, `\\Deliverables\\`

Logistics identifier cues:
- CLIN: `(?i)\\bCLIN\\b\\s*[:#-]?\\s*([A-Z0-9-]{2,})`
- Purchase request: `(?i)\\bPurchase\\s*Req(?:uest)?\\s*#?\\b\\s*[:#-]?\\s*([A-Z0-9-]{3,})`
- Purchase order: `(?i)\\b(?:PO|Purchase\\s*Order)\\s*#?\\b\\s*[:#-]?\\s*([A-Z0-9-]{3,})`
- Part/model/serial: `(?i)\\b(?:Part|P\\/N|Model|Serial)\\s*(?:Number|No\\.?|#)?\\b\\s*[:#-]?\\s*([A-Z0-9._-]{2,})`
- DD250 form token: `(?i)\\bdd\\s*250\\b`

Cybersecurity cues:
- `(?i)\\bACAS\\b|\\bNessus\\b|\\bSTIG\\b|\\bRMF\\b|\\bPOA\\&?M\\b|\\bIAVM\\b|\\bCCI\\b|\\bwaiver\\b|\\bfinding\\b`
- Severity: `(?i)\\bcritical\\b|\\bhigh\\b|\\bmedium\\b|\\blow\\b`
- Status: `(?i)\\bopen\\b|\\bclosed\\b|\\bmitigated\\b|\\bexception\\b|\\baccepted\\s+risk\\b`

Archive / lineage cues:
- Path cues: `\\Archive\\`, `\\backup\\`, `\\zzSEMS ARCHIVE\\`
- Duplicate suffix cue: `_(\\d+)\\.[A-Za-z0-9]+$`

Visual-heavy cues:
- Extension cues: `.jpg`, `.jpeg`, `.png`, `.gif`, `.tif`, `.tiff`, `.psd`, `.dwg`, `.sldprt`, `.sldasm`, `.step`, `.stp`
- Folder cues: `\\Drawings\\`, `\\GIS\\`, `\\Photos\\`

## 2.2 V2 Payload / Routing Metadata (must be indexed and queryable)

V2 should persist the following as retrievable metadata columns:
- all required Forge fields above
- all logistics/cyber fields above (nullable)
- `rerank_class` (computed at import: `authority_primary`, `table_primary`, `cyber_primary`, `archive_penalty`, `visual_link_only`)
- `v3_link_key` (stable key for future visual linkage graph)

V2 should not recompute authority tiers from scratch unless field missing; Forge stays source-of-truth for tiering.

## 3) Authority Tier Rules (DM/Deliverables First)

Deterministic precedence:
1. `dm_restricted` when path/metadata indicates `1.0 enterprise program DM - Restricted`.
2. `customer_deliverable` when deliverable/CDRL/DD250/customer-delivery cues present.
3. `operational_working` for active operations folders (logistics, cyber operations, engineering, site support).
4. `archive_copy` for archive/backup/legacy trees unless explicit query overrides.
5. `unknown` fallback.

Conflict rule:
- If both `deliverable` and `archive` cues exist, keep deliverable tier but apply archive penalty unless query asks for historical/archive.

## 4) Retrieval Ranking / Filtering / Reranking Rules

These rules are for V2 text retrieval behavior once metadata is present.

## 4.1 Pre-filter

Always-on:
- Drop temporary/lock/incomplete cues from ranking candidates (`~$`, known temp cues) unless query asks for recovery/forensics.

Default query behavior:
- `is_archive_derived=true` is **not excluded**, but gets penalty and cap.
- `dm_restricted` and `customer_deliverable` are never suppressed by archive rules.

Intent-triggered archive override (historical mode):
- Enable when query contains cues such as `archive`, `historical`, `legacy`, `prior`, `older`, specific past-year references.
- In historical mode, remove archive cap and reduce archive penalty.

## 4.2 Candidate Scoring (before cross-encoder rerank)

Recommended additive prior adjustments (probe-calibrated):
- `authority_tier=dm_restricted`: `+1.25`
- `authority_tier=customer_deliverable`: `+0.75`
- `authority_tier=operational_working`: `+0.25`
- `table_heavy=true` and query has logistics-table cues: `+0.80`
- `business_domain=logistics` with logistics intent: `+0.55`
- `business_domain=cybersecurity` with cyber intent: `+0.75`
- `is_visual_heavy=true` on generic text query: `-0.65`
- `parse_quality < 0.45`: `-0.40`

Domain-aware archive penalty:
- DM/authority intent: `-0.90` (or `-0.25` in historical mode)
- Logistics intent: `-0.70` (or `-0.25` in historical mode)
- Cyber intent: `-0.35` (or `-0.15` in historical mode)

Cyber sparse-domain guard:
- If cyber-class candidates in top-40 are fewer than 3, relax archive penalty one step and broaden domain match to adjacent sysadmin/security records before final rerank.

Identifier exact-match boosts (stackable, cap `+1.20` total):
- exact token hit on `log_purchase_order`, `log_part_number`, `log_serial_number`, `log_clin`, `cyber_finding_id`: `+0.35` each.

## 4.3 Rerank and Mix Policy

Rerank input mix constraints:
- At least 40% of rerank pool from highest authority tier available for the detected intent.
- Archive candidates capped to 20% of rerank pool in non-historical mode.
- Visual-heavy candidates capped to 15% for text answers unless explicit visual intent.

Cross-encoder rerank should include metadata features:
- authority tier
- domain match
- identifier exact-match flags
- archive/historical intent compatibility

## 4.5 Probe-Driven Calibration Notes

Probe artifact:
- `C:\HybridRAG_V2\docs\RETRIEVAL_METADATA_GPU_PROBE_2026-04-10.json`
- `C:\HybridRAG_V2\docs\RETRIEVAL_METADATA_GPU_PROBE_2026-04-10.md`

Measured impact on sample (`n=1074`, `cuda:1`, nomic embedding):
- DM authority targeting improved strongly with authority+archive priors.
- Logistics remained already separable; priors mainly reduced archive leakage.
- Cyber remained sparse, so hard archive suppression without guard reduced target hit rate.

Calibration consequence:
- keep strong authority boost
- keep archive down-rank
- apply domain-specific archive penalties and a cyber sparse-domain fallback guard

## 4.4 Final Answer Source Policy

When equally relevant chunks conflict:
1. Prefer `dm_restricted`
2. then `customer_deliverable`
3. then `operational_working`
4. then `archive_copy`

If answer relies on archive content while non-archive conflicts exist, response metadata should flag `archive_evidence_used=true`.

## 5) Domain-Specific Retrieval Rules

## 5.1 Logistics

Router cues:
- `CLIN`, `PO`, `Purchase Req`, `Vendor`, `Part Number`, `Model`, `OEM`, `Serial`, `DD250`, `shipment`, `packing list`, `EEMS`.

Routing behavior:
- Prefer table/structured retrieval first when logistics header fields are detected.
- Expand query with normalized logistics field synonyms (e.g., `PO` -> `Purchase Order #`).
- Return row-level hits before narrative context.

## 5.2 Cybersecurity / ACAS

Router cues:
- `ACAS`, `Nessus`, `STIG`, `RMF`, `POA&M`, `IAVM`, `CCI`, `waiver`, `finding`, `severity`, `mitigation`.

Routing behavior:
- Boost `business_domain=cybersecurity`.
- Prioritize chunks with populated cybersecurity fields.
- For remediation-status questions, prefer records with `cyber_status` and `cyber_scan_date`.

Data gap handling:
- If cybersecurity structured fields are sparse, keep keyword fallback but mark confidence as reduced.

## 6) V3 Visual Linkage Contract (Forward-Compatible)

V2 must persist enough lineage to link text answers to visual assets in V3:
- `v3_link_key` (stable doc/asset lineage key)
- `source_doc_hash`
- `visual_family`
- `is_visual_heavy`
- drawing/CAD identifiers when present (`drawing_number`, `sheet`, `revision`, `cad_part_id`)
- relationship fields linking visual asset -> authoritative text/doc record

V3 intent triggers:
- `show drawing`, `schematic`, `layout`, `photo evidence`, `CAD`, `sheet`, `title block`, `revision`.

In text-first V2 mode:
- do not over-rank visual-only chunks for generic narrative/logistics queries
- do return visual lineage references in metadata when applicable

## 7) Next Coding Slices (Concrete)

1. Forge metadata emit pass
- Files: `C:\CorpusForge\src\pipeline.py`, `C:\CorpusForge\src\export\packager.py` (or current export writer), metadata helper module under `C:\CorpusForge\src\export\`.
- Add authority/domain/archive/visual/identifier fields per section 2.1.

2. V2 import schema acceptance
- Files: `C:\HybridRAG_V2\scripts\import_embedengine.py`, `C:\HybridRAG_V2\src\store\lance_store.py`.
- Accept/store new metadata columns and ensure backward compatibility when fields are missing.

3. Router domain flags + cue extraction
- File: `C:\HybridRAG_V2\src\query\query_router.py`.
- Add `intent_domain`, `historical_mode`, and domain cue flags derived from query text.

4. Retrieval rerank priors
- File: `C:\HybridRAG_V2\src\query\pipeline.py` (and/or retriever merge point).
- Apply prior adjustments + domain-specific archive penalties + cyber sparse-domain guard.

5. Response and operator visibility
- Files: `C:\HybridRAG_V2\src\api\models.py`, `C:\HybridRAG_V2\src\gui\panels\query_panel.py`.
- Expose authority tier, archive usage, and domain routing reason in response metadata.

## 8) Residual Risks

- Cybersecurity dedicated capture returned zero files in this snapshot; cybersecurity field prevalence is inferred from global path signals and domain rules, not a full subtree census.
- OCR/visual-heavy families remain high-volume and low-text; metadata penalties must be tuned against real relevance judgments to avoid hiding useful evidence.
- Archive penalty thresholds need QA on conflict-heavy queries to prevent over-suppression of legitimate historical records.
