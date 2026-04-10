Sprint 6.6 Phase 1 Export — SUPERSEDED BY RUN 6
================================================

Status:        SUPERSEDED — use export_20260409_0720 (Run 6) instead
Produced by:   reviewer | CorpusForge | Run 5 | 2026-04-09 01:04 MDT
Hardened:      2026-04-09 01:50 MDT (post coordinator review)
Updated:       2026-04-09 06:50 MDT (archive leak fix shipped, V2 filter available)
Superseded:    2026-04-09 07:25 MDT (Run 6 landed clean, zero SAO/RSF leak)

>>> NEW CANONICAL EXPORT IS:
>>>     C:\CorpusForge\data\production_output\export_20260409_0720\
>>>
>>> See its READ_ME_BEFORE_USE.txt for the morning-safe import command.
>>> Run 6 has 242,650 chunks with ZERO SAO/RSF leak — no V2 filter needed.

THIS EXPORT (RUN 5) IS KEPT FOR HISTORICAL REFERENCE ONLY.
It still has the 100,055-chunk SAO leak. If you must import it for any
retroactive reason, the V2 --exclude-source-glob fallback below still
works.

MORNING-SAFE USAGE INSTRUCTIONS (added 2026-04-09 06:50 MDT)
------------------------------------------------------------
The CorpusForge archive-defer leak that produced this export has been
FIXED in code (commit-pending) and proven on a short sample. A clean
production rerun (Run 6) is in progress but will not finish in time
for the morning work session.

The V2 importer at C:\HybridRAG_V2\scripts\import_embedengine.py now
accepts an explicit --exclude-source-glob flag that can filter the
SAO leak from THIS export at import time:

    .venv\Scripts\python.exe scripts\import_embedengine.py ^
      --source C:\CorpusForge\data\production_output\export_20260409_0103 ^
      --exclude-source-glob "*.SAO.zip" ^
      --exclude-source-glob "*.RSF.zip" ^
      [--create-index]

Verified dry-run result against this export:
    - Pre-filter:  344,129 chunks
    - Excluded:    100,055 chunks  (the entire SAO leak)
    - Kept:        244,074 chunks  (the document content)

The filter is visible at startup (banner + active globs), at end-of-
import (excluded count), and is recorded in a durable
``import_report_*.json`` artifact under the ``import_filters`` block
so the filtered import is not indistinguishable from an unfiltered one.

REMOVAL CONDITION FOR THE V2 FILTER:
Retire --exclude-source-glob once Run 6 (the clean rerun) has landed
and been spot-checked for zero SAO leak. Until then, treat it as a
required operator argument when importing this export.

DO NOT TREAT THIS EXPORT AS A CLEAN CANONICAL PHASE 1 SET.

Three blockers were identified by coordinator review and are not resolved
in this artifact:

1. SAO LEAK (HIGH — 29.1% of export)
   parse.defer_extensions: [.sao, .rsf] worked at the top filesystem layer
   (0 top-level .sao / .rsf chunks), but the archive parser extracted SAO
   members from *.SAO.zip and parsed them in-place. That bypassed the
   defer rule entirely.

   Hard count from chunks.jsonl:
     - SAO data via *.SAO.zip   100,055 chunks   29.1%
     - Other ZIP archives         2,731 chunks    0.8%
     - Top-level .sao / .rsf          0 chunks    0%
     - Document-only (estimated)  ~244,074 chunks  ~70.9%

   Actual document-only count is approximately 244,074, NOT 344,129.

2. UNBOUNDED CODE STATE (MEDIUM)
   Run 5 was produced from a dirty working copy of src/pipeline.py that
   contains edits beyond reviewer's two claimed fixes
   (CUDA_VISIBLE_DEVICES remap + sub-batch embedding). The unreviewed
   delta includes a parser-environment override layer, _emit_stats
   callback infrastructure, and CPU terminology renames.
   Until this is split into a separate commit or reverted, this export
   is not attributable to a bounded reviewed code state.

3. .PPT OVERCLAIM (MEDIUM — 178 chunks)
   Legacy .ppt parser at src/parse/parsers/ppt_parser.py returns OLE
   container metadata strings ("[Content_Types].xml", "_rels/.rels", etc.)
   on files it cannot decode, and still assigns parse_quality=0.7. These
   178 chunks are garbage. .pptx (modern) is fine — only legacy .ppt is
   degraded.

Other documented gaps (environment limitations, NOT bugs):
   - No Tesseract on primary workstation → 14,623 .jpg chunks are metadata-only,
     plus 145 of the 534 file failures are scanned PDFs.
   - No Poppler on primary workstation → no rasterize-and-OCR fallback.
   - No GLiNER entity extraction (entities.jsonl is empty by design;
     this is a Phase 2 deliverable for V2 GATE-2).
   - No contextual enrichment (Ollama phi4 too slow at this scale).
   - Forge 6.1-6.5 QA was NOT performed by reviewer before 6.6 ran;
     gate compliance is a coordinator/QA decision.

PERMITTED LIMITED USES (with explicit non-canonical labeling)
-------------------------------------------------------------
- V2 GATE-1 import smoke test
- Internal rehearsal of the V2 ingestion pipeline
- Logistics-persona demo where the operator filters *.SAO.zip source
  paths at import time, or explicitly accepts the 29% ionogram leak

PROHIBITED USES UNTIL BLOCKERS RESOLVED
---------------------------------------
- Operational signoff
- Any claim that this is a clean canonical Phase 1 export
- Any claim that SAO/RSF was successfully excluded
- Anything that depends on the .ppt content being meaningful

REQUIRED BEFORE OPERATIONAL SIGNOFF
-----------------------------------
- Resolve the SAO leak: either filter *.SAO.zip at V2 import time,
  or re-run Forge 6.6 with archive_parser taught to honor
  parse.defer_extensions for extracted members.
- Bound the dirty pipeline.py code state: commit-split reviewer's
  two fixes from the unreviewed linter/other edits, or revert the
  delta and re-run against a clean baseline.
- Accept or filter the .ppt garbage chunks at V2 import.

REFERENCES
----------
- Full evidence note (with Coordinator Review section):
  C:\CorpusForge\docs\SPRINT_6_6_EVIDENCE_2026-04-08.md
- Failure list (534 files, categorized):
  C:\CorpusForge\data\production_output\export_20260409_0103\failures_run5.txt
- Sprint board entries (READY FOR QA — HOLD ON SIGNOFF):
  C:\CorpusForge\docs\SPRINT_SYNC.md  (line 232)
  C:\HybridRAG_V2\docs\SPRINT_SYNC.md (line 232)

Signed: reviewer | CorpusForge | 2026-04-09 01:50 MDT
