# Dedup Review Guide 2026-04-06

**Purpose:** Explain how to review duplicate families produced by the recovery dedup tooling and how to choose a canonical file before a rebuild.

---

## What This Review Is For

The dedup recovery pass finds document families that are likely the same content in different formats or export variants.

Typical examples:

- `DOCX` and `PDF` versions of the same document
- signed or stamped variants
- exported copies that differ only in layout
- files with an extra cover page or one short appended section

The review step is where a human checks whether the automatic canonical choice is acceptable before the rebuild input list is frozen.

---

## What To Look At

Review these fields in the generated report:

- canonical path
- file extension mix
- parse quality
- normalized character counts
- similarity or containment score
- dedup reason
- duplicate count in the family

The report is designed to be read by a non-programmer operator. It is safe to open in a text editor, spreadsheet, or markdown viewer.

---

## Canonical Choice Rules

Use these rules when reviewing a family:

1. Prefer the most editable source when the content is effectively the same.
2. Prefer `DOCX` over `DOC` over `PDF` when parse quality is close.
3. Prefer the file with the best parse quality and the most complete text.
4. Prefer the file with fewer OCR artifacts and fewer missing sections.
5. If one version has a signature page, cover page, or a short appended block, keep the cleaner core document.
6. If the family is mixed-format and the canonical choice looks wrong, flag it for manual review instead of freezing it.

---

## What Counts As A Good Result

A good family usually has:

- one obvious canonical source
- clear duplicate members
- a sensible format preference
- no suspicious loss of content

Examples of good canonical outcomes:

- `DOCX` kept over `PDF` when both parse similarly
- the cleaner editable source kept over a stamped export copy
- the version with more complete text kept when one file is truncated

---

## What Counts As A Risk

Review more carefully if a family has:

- mixed `DOC`, `DOCX`, and `PDF` formats
- very different parse quality across members
- low similarity but the same filename family
- a scanned PDF that may have OCR noise
- a signature or appendix that might change meaning

Those families should be flagged for manual inspection before rebuild approval.

---

## How To Run The Reviewer

From the `CorpusForge` repo root:

```powershell
python scripts/review_dedup_samples.py --dedup-dir C:\CorpusForge\data\smoke\dedup_output
```

Or review a larger recovery output:

```powershell
python scripts/review_dedup_samples.py --dedup-dir C:\CorpusForge\data\output\sprint6_scale_subset_20260405_1810\export_20260405_1753_dedup
```

The tool writes:

- `dedup_review_report.md`
- `dedup_review_rows.jsonl`
- `dedup_review_rows.csv`

into a timestamped review folder under the dedup output directory unless you specify `--output-dir`.

---

## Review Order

Suggested order:

1. Review the families with the largest duplicate counts first.
2. Review mixed-format families next.
3. Review families with low similarity or weak parse quality.
4. Freeze the canonical list only after the sample looks sane.

---

## Related Paths

- `scripts/review_dedup_samples.py`
- `scripts/build_document_dedup_index.py`
- `scripts/run_pipeline.py --input-list`

