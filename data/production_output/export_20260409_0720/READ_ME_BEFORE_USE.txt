Sprint 6.6 Phase 1 Export — CLEAN CANONICAL (Run 6)
====================================================

Status:        CLEAN CANONICAL on the SAO/RSF dimension
Produced by:   reviewer | CorpusForge | Run 6 | 2026-04-09 07:21 MDT
Bug fix:       Archive-member defer leak (segment-based defer in ArchiveParser)

This export REPLACES export_20260409_0103 (Run 5) as the morning-safe
canonical export. Run 5 had a 100,055-chunk SAO leak through ZIP recursion.
Run 6 was produced from the same source corpus AFTER the archive-defer
fix shipped, and has been verified to contain ZERO SAO/RSF leak.

Verification (re-pulled from chunks.jsonl after the run finished):
    *.sao.zip source paths:           0
    *.rsf.zip source paths:           0
    Any 'sao' dot-segment in source:  0
    Any 'rsf' dot-segment in source:  0
    Top-level *.sao source:           0
    Top-level *.rsf source:           0
    VERDICT: ZERO SAO/RSF leak.

Final counts:
    Total chunks:    242,650
    Total vectors:   242,650 (matches; 768 dim float16)
    Files parsed:    17,134
    Files failed:    7,068    (NOT real failures — see note below)
    Files skipped:   2,813    (top-level SAO/RSF + temp files + encrypted)
    Elapsed:         1,937 sec (~32 minutes)

About the "files_failed" count
------------------------------
The 7,068 figure is misleading. ~6,550 of those are .SAO.zip archives
that the new archive-defer fix correctly refuses to extract — the
ArchiveParser returns an empty doc at parse() entry when the archive's
own basename has a deferred dot-segment. The pipeline accounting
counts an empty parse result as "files_failed" rather than
"files_skipped" because the SkipManager only handles top-level
extension skipping. This is a semantic mislabeling, not a real failure.

The remaining ~518 failures are the same baseline as Run 5: 314 BIT.XML
sensor files, 145 scanned PDFs (no Poppler/Tesseract on primary workstation), 60
empty/corrupted DOCX, etc. See failures_run6.txt for detail (will be
written by a follow-up task if QA needs it).

How to import into HybridRAG V2
-------------------------------
NO --exclude-source-glob filter is needed. Run 6 is clean at the source.

    cd C:\HybridRAG_V2
    .venv\Scripts\python.exe scripts\import_embedengine.py ^
      --source C:\CorpusForge\data\production_output\export_20260409_0720 ^
      --create-index

The import will produce a durable import_report_*.json artifact in
this directory recording the import (mode=import, target_db, final
counts, manifest fingerprint linking back to this export).

Comparison with Run 5 + V2 filter
---------------------------------
Run 5 export filtered with --exclude-source-glob "*.SAO.zip" "*.RSF.zip":
    344,129 - 100,055 = 244,074 chunks kept

Run 6 export (no filter needed):
    242,650 chunks total

Within 0.6% of each other. The two paths are operationally equivalent.
Run 6 is preferred because the cleanliness is at the source, not at
import time, so any future re-import or re-build does not require
operators to remember to apply the filter.

Format coverage (top 15 by chunk count)
---------------------------------------
    .xlsx:  189,862  (logistics packing lists — primary value)
    .jpg:    14,623  (metadata-only — no Tesseract on primary workstation)
    .pdf:    14,324  (text-layer only)
    .txt:    11,201
    .rtf:     5,194
    .doc:     2,549
    .docx:    2,251
    .zip:     1,307  (16 legitimate non-SAO archives only)
    .png:       331  (metadata-only)
    .jpeg:      281  (metadata-only)
    .ppt:       178  (legacy parser still produces OLE garbage — open item)
    .ini:       177
    .msg:       170
    .xls:       109
    .pptx:       48

Still-open items inherited from Run 5
-------------------------------------
1. .ppt (legacy binary) parser produces OLE container metadata strings
   for ~178 chunks. parse_quality is misleadingly 0.7. Recommend
   filtering at V2 import OR accepting low retrieval impact.
   Bounded to 178 chunks (0.07% of export).

2. Code-state provenance: src/pipeline.py was a dirty working copy
   when this run executed. Linter/other edits beyond reviewer's two
   intentional fixes (CUDA_VISIBLE_DEVICES remap + sub-batch embed +
   archive-defer fix plumbing) were also active. Reviewer must
   commit-split or accept before this can claim full provenance.

3. Tesseract + Poppler not installed on primary workstation. ~14,623 JPGs are
   metadata-only and ~145 scanned PDFs failed parse. Environment
   limitation, not a code bug.

4. No GLiNER entity extraction. entities.jsonl is empty by design;
   that is the V2 GATE-2 deliverable for a future Phase 2 pass.

5. Forge 6.1-6.5 QA was not performed by reviewer before 6.6 ran.
   Gate compliance is a coordinator decision.

Signed: reviewer | CorpusForge | 2026-04-09 07:25 MDT
