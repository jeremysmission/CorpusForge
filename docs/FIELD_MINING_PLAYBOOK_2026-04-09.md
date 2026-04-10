# Field Mining Playbook 2026-04-09

Purpose: define how to mine structured signals from mixed-format corpora using generic, reusable techniques.

## Extraction Order

Use the cheapest reliable method first.

1. path and filename metadata
2. extension and document family
3. label-value regex
4. table header detection
5. local proximity rules
6. semantic extraction for the remainder

## What To Mine

Common high-value fields across enterprise corpora:

- identifiers
- people / roles
- organizations
- sites / locations
- dates
- quantities
- statuses
- actions / recommendations
- line-item attributes

## Evidence Types

### Label-Value Pairs

Best when the corpus uses forms, templates, or repeated headings.

Examples of generic lead-ins:

- `Part Number`
- `Serial Number`
- `PO`
- `Ship Date`
- `Received`
- `Contract`
- `Deliverable`
- `Owner`
- `Status`

Rules:

- mine normalized labels first
- preserve the raw matched text
- capture nearby heading context

### Table Headers

Best when the value is repeated row-wise.

Approach:

- detect stable headers
- map synonyms into canonical field names
- keep row-group context together during chunking

### Filename And Path Clues

Best when content is sparse or parser quality is low.

Use:

- folder lineage
- filename tokens
- extension
- archive parent/member path
- encrypted / OCR-sidecar markers

These clues should not override strong text evidence, but they are often enough to classify family and route the right extractor.

### Proximity Rules

Best for prose-heavy documents.

Approach:

- anchor on a strong label or identifier
- inspect a narrow left/right context window
- use sentence or line boundaries as hard limits

### Semantic Extraction

Reserve for:

- prose-only entities
- normalized role and organization names
- action-item extraction
- cases where the label grammar is not stable

Do not use semantic extraction where table headers or label-value pairs are already high precision.

## Chunking Implications

Field mining and chunking are linked.

Recommended defaults:

- table-heavy docs: row-group chunks with repeated headers
- section-heavy docs: heading-aware chunks
- OCR-heavy docs: chunk only after quality passes
- drawings: metadata-first, text extraction second

## Quality Gates

Before promoting any mined field:

1. test on held-out files
2. measure false positives
3. compare against a simpler regex-only baseline
4. record the family where the rule applies

## Generic Rule Design

Good:

- "When a table contains repeated line-item headers, preserve the header in every downstream chunk."
- "When OCR sidecar suffixes are present, hash/defer the derivative asset and prefer the parent document."
- "When repeated recursive folder signatures exist, surface them as duplicate-bundle candidates before parse."

Bad:

- rules named after a specific customer folder
- private acronyms baked into code comments
- production-only labels exposed in public docs
