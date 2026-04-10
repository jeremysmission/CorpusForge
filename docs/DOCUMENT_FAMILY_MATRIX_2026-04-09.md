# Document Family Matrix 2026-04-09

Purpose: define generic document families and the best-fit handling strategy for each one.

These are common enterprise families, not claims about any one production corpus.

| Family | Common Signals | Parse Policy | Chunk Policy | Extraction Priority | Retrieval Metadata |
|---|---|---|---|---|---|
| Logistics / receiving / shipment records | tables, line items, identifiers, dates, quantities, shipping terms | prefer table-preserving parser path | keep header row context and row adjacency | regex + table-header cues first | document family, source folder, part/vendor/date flags |
| Contracts / funding / milestones | section labels, amendment language, dates, monetary fields, deliverable language | preserve section ordering and headings | section-aware chunks, avoid splitting clause headers from body | label regex + proximity rules + selective semantic extraction | document family, section title, contract-like field presence |
| Program management status docs | action items, schedules, owners, risks, decision language | parse prose and tables; preserve headings | chunk by section and bullet grouping | role/date/action extraction | document family, heading path, action/risk markers |
| Engineering manuals / maintenance references | headings, procedures, cautions, part references, step order | preserve heading hierarchy | heading-aware chunks with procedure continuity | identifier regex + local context windows | document family, manual/procedure flag, identifier presence |
| Inventory / parts / BOM exports | structured columns, repeated identifiers, status fields | preserve tabular structure | chunk by row groups, not arbitrary character windows | regex + table schema mapping | part-count flags, table-heavy flag, identifier families |
| Drawings / CAD / diagrams | drawing extensions, image-heavy folders, sparse text, title blocks | default hash/defer or metadata-only unless text density is strong | if parsed, keep page/title-block grouping | metadata inference first, OCR only when justified | drawing flag, title-block presence, diagram family |
| OCR-heavy scans | scan names, image formats, low text density, OCR sidecars | stricter quality gate before full indexing | larger chunks only after quality passes | labels and identifiers only if confidence passes | OCR flag, parse quality, scan confidence |
| OCR sidecars / derivatives / cache assets | suffix patterns, hOCR, djvu text/xml, thumbs, spectrograms | hash/defer by default | none | none | derivative flag, parent-file relation if known |
| Archive containers and extracted bundles | archive extensions, nested folder trees, repeated recursive signatures | inspect container provenance, then parse selectively | chunk only after bundle passes duplicate screen | metadata first, content extraction second | archive flag, bundle signature, parent archive path |
| Cyber / compliance / framework references | policy language, controls, enumerated standards | preserve headings and lists | chunk by control or subsection | section and control-ID regex | framework flag, control identifiers |

## Promotion Rules

Promote a family-specific rule only when:

1. it improves precision or throughput in repeated samples
2. the failure mode is visible in reports
3. the rule can be described generically
4. the rule is reversible through config or an explicit waiver

## Anti-Patterns

- one-off folder-name hacks with no evidence
- treating drawings as normal prose by default
- indexing OCR derivatives alongside their parent documents
- letting archive extractions multiply near-identical content silently
- using semantic extraction where headers or tables are already precise
