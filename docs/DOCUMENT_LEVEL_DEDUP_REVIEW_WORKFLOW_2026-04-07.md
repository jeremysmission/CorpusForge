# Document-Level Dedup Review Workflow 2026-04-07

## Approved Review Lane

Use the document-level dedup review path as the human-review source of truth.

Current rule:

- document-level review: approved
- chunk-level review: conditional only

Reason:

- document-level dedup preserves readable canonical/duplicate file identities
- chunk-level review can still lose duplicate-member metadata after dedup and is not yet strong enough to be the primary human review lane

---

## Run It

From the `CorpusForge` repo root:

```powershell
cd C:\CorpusForge
.\.venv\Scripts\python.exe scripts\review_dedup_samples.py --dedup-dir "<DOCUMENT_DEDUP_OUTPUT_DIR>"
```

Example:

```powershell
cd C:\CorpusForge
.\.venv\Scripts\python.exe scripts\review_dedup_samples.py --dedup-dir "C:\CorpusForge\data\smoke\dedup_output"
```

The tool writes:

- `dedup_review_report.md`
- `dedup_review_rows.jsonl`
- `dedup_review_rows.csv`

into a timestamped review folder under the dedup output.

---

## Review Rules

Use these canonical-choice rules:

1. Prefer the most editable source when content is effectively the same.
2. Prefer `DOCX` over `DOC` over `PDF` when parse quality is close.
3. Prefer the file with the most complete text.
4. Prefer the version with fewer OCR artifacts.
5. If the family looks mixed or risky, flag it for manual decision instead of trusting the automatic canonical choice.

---

## Use It For

Use this workflow when:

- validating duplicate families before freezing `canonical_files.txt`
- reviewing mixed-format families
- checking whether the dedup pass is choosing sensible canonical sources

---

## Do Not Use Chunk-Level Review As Primary Evidence

Chunk-level review is still useful for exploratory analysis, but it is not yet the accepted human-review lane for recovery dedup decisions.

Until that path is improved, use chunk-level review only as supporting evidence, not as the approval source for canonical choice.
