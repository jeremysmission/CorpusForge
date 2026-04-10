# Corpus Adaptation Plan 2026-04-09

Purpose: turn source-tree evidence into generic, reusable parsing, extraction, chunking, and retrieval rules without disclosing any production-specific document set.

This is not a claim of "perfect RAG." It is a measured adaptation lane built from:

1. source-tree metadata
2. parser outputs and failure logs
3. skip/defer manifests
4. chunk/export artifacts
5. query-side misses and false positives

## Scope

This lane belongs primarily to `CorpusForge`, with downstream query-routing consequences in `HybridRAG_V2`.

Code surfaces this work should influence:

- `src/config/schema.py`
- `src/skip/skip_manager.py`
- `src/pipeline.py`
- `src/parse/dispatcher.py`
- parser modules under `src/parse/parsers/`
- extraction settings in `HybridRAG_V2/src/config/schema.py`

## Two-Phase Approach

### Phase 1: Sample-Tree And Export-Artifact Adaptation

Use the production-like sample tree already mirrored locally plus current Forge outputs.

Primary inputs:

- source-tree folder hierarchy
- extension mix
- filename tokens
- OCR sidecar patterns
- encrypted-file naming cues
- repeated recursive folder signatures
- `manifest.json`
- `run_report.txt`
- `skip_manifest.json`
- `chunks.jsonl`
- parser failure logs or failure lists

Goal:

- identify common document families
- identify junk/derivative families
- identify skip/defer candidates
- identify metadata clues worth preserving into retrieval

### Phase 2: Full-Corpus Calibration

When the larger source drive or a larger production export is available, re-run the same profiling path at scale.

Goal:

- confirm which heuristics generalize
- quantify false positives
- quantify archive-family duplication
- tune config defaults and family-specific extraction thresholds

## Required Artifacts From A Real Run

For any meaningful adaptation pass, preserve:

- export directory
- `manifest.json`
- `run_report.txt`
- `skip_manifest.json`
- `chunks.jsonl`
- failure list or parser log
- if available, the relevant `file_state.sqlite3` copy or a filtered export of statuses

## Generic Adaptation Layers

### 1. Document-Family Classification Before Deep Parsing

Use:

- folder path
- filename tokens
- extension
- archive membership
- image density
- table/prose balance
- OCR sidecar presence
- parse quality

This should drive family-specific behavior instead of one uniform path.

### 2. Family-Specific Parse And Chunk Policy

Examples:

- table-heavy operational records: preserve row continuity and header context
- contracts and budget packets: section-aware chunking
- engineering manuals: heading-aware chunking with identifier retention
- drawings and diagrams: default hash/defer unless text density is high
- OCR-heavy scans: stricter quality gate before indexing

### 3. Family-Specific Extraction Policy

Use the cheapest reliable method first:

- metadata and filename inference
- header and label regex
- table header detection
- proximity rules
- semantic extraction only where precision justifies it

### 4. Query-Side Routing

The retrieval stack should mirror document families:

- logistics / inventory / receiving
- contracts / budgets / milestones
- engineering / maintenance / part lookup
- people / organizations / sites
- drawings / diagrams / asset identity

## Archive-Duplicate Strategy

Repeated extracted-archive trees are a real risk because they multiply parse time and retrieval noise.

The first response should be generic and auditable:

- detect repeated recursive folder signatures from metadata only
- record them as candidate duplicate bundles
- surface them to an operator report
- only promote to auto-skip after confirming precision on held-out samples

Do not hide this in hardcoded one-off folder names. Make it a general "recursive folder signature duplicate" rule if it proves reliable.

## Immediate Deliverables

1. `scripts/profile_source_corpus.py`
2. metadata-only profiling report on a local sample tree
3. document-family matrix
4. field-mining playbook
5. follow-on implementation slices for skip/defer, extraction, and query routing

## Success Criteria

This lane is working if it produces:

- fewer junk chunks
- fewer duplicate archive-derived bundles
- higher-value metadata in exports
- cleaner family-specific query routing in V2
- explicit evidence for every promoted heuristic
