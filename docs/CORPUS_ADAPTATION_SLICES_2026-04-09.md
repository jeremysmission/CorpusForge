# Corpus Adaptation Slices 2026-04-09

Purpose: keep the corpus-adaptation lane alive across context loss.

## 2026-04-09 Status

- Slice A: READY FOR QA
  - profiler run completed against `C:\CorpusForge\ProductionSource\verified\source\verified\IGS`
  - outputs:
    - `C:\CorpusForge\data\export\corpus_profile_igs_sample_20260409.json`
    - `C:\CorpusForge\data\export\corpus_profile_igs_sample_20260409.md`
    - `C:\CorpusForge\data\export\corpus_adaptation_export_analysis_20260409.json`
  - reproducible export-analysis generator:
    - `C:\CorpusForge\scripts\analyze_export_artifacts.py`
- Slice B: EVIDENCE CAPTURED, NOT YET PROMOTED
  - exact recursive folder-signature duplicates were `0` in the sample-tree profile
  - weaker archive-derived and repeated-basename duplicates do show up in the real export artifacts
  - keep this lane in audit mode until a looser signature heuristic is measured
- Slice C: INITIAL TUNING EVIDENCE CAPTURED
  - spreadsheet-heavy travel/admin and inventory/manifest families dominate retrieval-weight
  - image families dominate file count but mostly produce one short chunk each
  - drawing/diagram and archive-derived families are visible enough to justify explicit family tags
- Slice D: INITIAL TUNING EVIDENCE CAPTURED
  - table/header/path-first extraction should take priority over semantic extraction for the dominant spreadsheet families
  - XML telemetry/BIT-style failures look like a defer candidate, but only after one more value audit
- Slice E: INITIAL ROUTING INPUTS IDENTIFIED
  - high-value retrieval metadata candidates now include `source_extension`, `document_family`, `table_heavy`, `archive_derived`, `image_or_metadata_only`, `parse_quality`, and `reused_basename_flag`

Primary evidence note:

- `C:\CorpusForge\docs\CORPUS_ADAPTATION_EVIDENCE_2026-04-09.md`

## Slice A: Metadata Profiling

Deliverable:

- run `scripts/profile_source_corpus.py` against a production-like sample tree

Output:

- local JSON report
- local markdown report

Questions answered:

- what extensions dominate
- which folders are image-heavy or drawing-heavy
- where OCR sidecars are common
- where repeated recursive folder signatures exist

## Slice B: Archive-Duplicate Candidate Audit

Deliverable:

- review duplicate recursive folder-signature groups from the profiler

Goal:

- decide whether a generic bundle-signature skip lane is precise enough to promote

Do not auto-skip until sampled.

## Slice C: Document-Family Tuning

Deliverable:

- map dominant families to parse, chunk, and extraction policy

Targets:

- table-heavy records
- section-heavy narrative docs
- drawing / diagram families
- OCR-heavy scan families
- archive-derived bundles

## Slice D: Field-Mining Upgrade

Deliverable:

- prioritize header, table, and identifier rules before semantic extraction

Goal:

- make the extraction stack cheaper and more precise for repeated field families

## Slice E: Query-Routing Alignment

Deliverable:

- update V2 query routing heuristics to mirror document families surfaced by Forge

Goal:

- avoid treating all queries as generic prose retrieval

## Inputs To Preserve From Any Meaningful Run

- export directory
- `manifest.json`
- `run_report.txt`
- `skip_manifest.json`
- `chunks.jsonl`
- failure list or parser log

## Near-Term Recommendation

Do not wait for a raw-drive move to begin this lane.

Start with:

1. the production-like sample tree already mirrored locally
2. the next successful Forge export package
3. the associated skip and failure artifacts

Then re-run the same profiling path later against the larger corpus or full source tree for calibration.
