# Skip/Defer Hardening — 2026-04-09

**Lane:** CorpusForge Lane 2 — family-aware skip/defer hardening
**Evidence base:** Run 6 production export `data/production_output/export_20260409_0720/` (242,650 chunks) + the existing source-corpus profiler (`src/analysis/corpus_profiler.py`) signal taxonomy.
**Scope:** high-confidence, generic, operator-visible improvements only. No customer-specific folder hacks, no V2 changes.

---

## TL;DR

Two new rules are now **automatic** in `SkipManager`, gated by existing config knobs so they are self-documenting and reversible:

1. **Image-asset family hashed/deferred when `parse.ocr_mode == "skip"`** — kills 15,237 `[IMAGE_METADATA]`-only chunks on Tesseract-less workstations (**6.28% of the Run 6 corpus** was this junk).
2. **Encrypted-by-filename-cue as a distinct skip class** — separate reason key in `skip_manifest.json` from the magic-byte detector, so operators can see name-cue vs true-encryption counts at a glance.

One rule stays **report-only** pending more precision evidence:

3. **Recursive folder-signature duplicate bundles** — the existing `scripts/profile_source_corpus.py` already reports these. No pipeline change, no auto-skip.

Every skipped file is still SHA-256 hashed and recorded in `skip_manifest.json` with its reason, preserving hash continuity and resume safety.

---

## Audit of current behavior

### Pain points verified against Run 6 artifacts

Pulled directly from `data/production_output/export_20260409_0720/` (Run 6, 2026-04-09 07:20 MDT):

| Signal | Count | Source |
|---|---:|---|
| Total chunks | 242,650 | `manifest.json` |
| Image-file chunks | 15,239 | `chunks.jsonl` scan |
| Image chunks that are pure `[IMAGE_METADATA]` filename/size junk | **15,237** | `chunks.jsonl` scan |
| Image chunks with any real extracted text | 2 | `chunks.jsonl` scan |
| Encrypted-filename-cue PDFs in this run | 0 | `chunks.jsonl` scan |
| OCR-sidecar-named chunks in this run | 0 | `chunks.jsonl` scan |
| Thumbnail/preview image chunks in this run | 0 | `chunks.jsonl` scan |
| `skip_manifest.json` → `counts_by_reason` | `2767 deferred-by-config`, `43 ~$ temp`, `3 encrypted-magic-bytes` | `skip_manifest.json` |
| `run_report.txt` → `Format Coverage` → `.jpg` | 14,623 | `run_report.txt` |
| `run_report.txt` → `Format Coverage` → `.png` | 331 | `run_report.txt` |
| `run_report.txt` → `Format Coverage` → `.jpeg` | 281 | `run_report.txt` |
| `files_failed` total (including ~6,550 correctly-refused SAO archives) | 7,068 | `run_report.txt` |

See `docs/SKIP_DEFER_HARDENING_2026-04-09_proof.json` for the raw counterfactual replay.

### What the evidence says

- `src/parse/parsers/image_parser.py` correctly degrades to `_metadata_fallback()` when Tesseract or Pillow is missing (primary workstation reality: `docs/HANDOVER_2026-04-09.md` already flagged "No Tesseract / Poppler on primary workstation"). But the degraded output — a ~100-byte `[IMAGE_METADATA] file=... ext=... size_bytes=...` line — reaches the chunker and becomes a retrieval-noise chunk per image. That is 6.28% of the entire Run 6 corpus.
- `src/skip/skip_manager.py` had no image-asset family. `.jpg/.png/.jpeg/.tif` were not in `deferred_formats` (correctly — when OCR is available they should parse), so every image file reached the parser on every run.
- Encrypted files were detected only by the magic-byte path and lumped under a single `encrypted file detected` reason. The profiler's `encrypted_pdf_name` signal (`src/analysis/corpus_profiler.py:42`) was never promoted into a production skip class.
- Recursive folder signatures are already detected by `corpus_profiler.profile_source_tree()` with SHA-256 manifest hashing (`src/analysis/corpus_profiler.py:179-206`). Zero precision data exists yet on whether auto-skip is safe.

---

## Changes (automatic — promoted to SkipManager)

### 1. Image-asset family hashed/deferred when `parse.ocr_mode == "skip"`

**Config (`config/config.yaml` → `skip:`):**

```yaml
image_asset_extensions:
  - ".jpg"
  - ".jpeg"
  - ".png"
  - ".gif"
  - ".bmp"
  - ".tif"
  - ".tiff"
  - ".webp"
  - ".svg"
  - ".wmf"
  - ".emf"
  - ".psd"
```

**Behavior:**

- `SkipManager.__init__` now accepts `ocr_mode: str = "auto"`. `Pipeline.__init__` passes `config.parse.ocr_mode`.
- In `should_skip`, when `ocr_mode == "skip"` AND `ext` is in `skip.image_asset_extensions`, the file is hashed and skipped with reason `"image asset (OCR disabled — metadata-only parse suppressed)"`.
- When `ocr_mode` is `"auto"` or `"force"` this new rule is dormant. Whether the image then flows through `ImageParser` depends on a **second, unrelated check**: the generic `parse.defer_extensions` list — see the two-group table below.
- The rule runs **before** the generic `deferred_formats` check so the reason string stays family-specific when both would fire.

**Two-group recovery reality (against the current `config/config.yaml`):**

The live config defers `.jpg`, `.jpeg`, `.svg`, and `.psd` unconditionally through `parse.defer_extensions`. Flipping `parse.ocr_mode` alone does **not** route those four extensions back through `ImageParser` — the operator must also edit `parse.defer_extensions` to remove them. The table below spells out the exact populations:

| Extension | `skip.image_asset_extensions` | `parse.defer_extensions` (current config) | Behavior under `ocr_mode="skip"` | Behavior under `ocr_mode="auto"/"force"` | To actually recover text parsing |
|---|:---:|:---:|---|---|---|
| `.jpg` | yes | **yes** | skipped as `image asset (OCR disabled …)` | skipped as `Deferred by config for this run` | flip `ocr_mode` **and** remove from `parse.defer_extensions` |
| `.jpeg` | yes | **yes** | skipped as `image asset (OCR disabled …)` | skipped as `Deferred by config for this run` | flip `ocr_mode` **and** remove from `parse.defer_extensions` |
| `.svg` | yes | **yes** | skipped as `image asset (OCR disabled …)` | skipped as `Deferred by config for this run` | flip `ocr_mode` **and** remove from `parse.defer_extensions` |
| `.psd` | yes | **yes** | skipped as `image asset (OCR disabled …)` | skipped as `Deferred by config for this run` | flip `ocr_mode` **and** remove from `parse.defer_extensions` |
| `.png` | yes | no | skipped as `image asset (OCR disabled …)` | **routed to `ImageParser`** | flip `ocr_mode` only |
| `.gif` | yes | no | skipped as `image asset (OCR disabled …)` | **routed to `ImageParser`** | flip `ocr_mode` only |
| `.bmp` | yes | no | skipped as `image asset (OCR disabled …)` | **routed to `ImageParser`** | flip `ocr_mode` only |
| `.tif` | yes | no | skipped as `image asset (OCR disabled …)` | **routed to `ImageParser`** | flip `ocr_mode` only |
| `.tiff` | yes | no | skipped as `image asset (OCR disabled …)` | **routed to `ImageParser`** | flip `ocr_mode` only |
| `.webp` | yes | no | skipped as `image asset (OCR disabled …)` | **routed to `ImageParser`** | flip `ocr_mode` only |
| `.wmf` | yes | no | skipped as `image asset (OCR disabled …)` | **routed to `ImageParser`** | flip `ocr_mode` only |
| `.emf` | yes | no | skipped as `image asset (OCR disabled …)` | **routed to `ImageParser`** | flip `ocr_mode` only |

No behavior regression is introduced by this lane: `.jpg/.jpeg/.svg/.psd` were already being deferred by the pre-existing `parse.defer_extensions` list; the new rule just tags them with a more informative reason when `ocr_mode == "skip"`. Hash continuity is preserved on either path because both skip classes route through `record_skip` and write a `hashed`/`deferred` state row.

**Reversibility:**

- To keep the new image-asset rule but allow OCR-mode auto recovery for the full image family, edit `config/config.yaml`:
  1. `parse.ocr_mode: "auto"`
  2. remove `.jpg`, `.jpeg`, `.svg`, `.psd` from `parse.defer_extensions` if you want those four back in the parser too.
- To turn the new rule off entirely without touching `parse.defer_extensions`, remove the desired extensions from `skip.image_asset_extensions`. The `parse.defer_extensions` coverage stays in place.
- No code change is required for any of these.

**Operator visibility:**

- `skip_manifest.json` → `counts_by_reason` → new key `"image asset (OCR disabled — metadata-only parse suppressed)": N`.
- `skip_manifest.json` → `files[]` → one entry per skipped image with SHA-256, size, reason.
- `run_report.txt` → `Skip Reasons:` line will include the new class automatically via `SkipManager.get_reason_summary()`.
- GUI Live Stats → `Files skipped` counter rises as discovery feeds the skip pass.
- Log line (INFO level) per file: `SKIP: {name} — image asset (OCR disabled — metadata-only parse suppressed) (sha256=...)`.

### 2. Encrypted-by-filename-cue as a distinct skip class

**Config (`config/config.yaml` → `skip:`):**

```yaml
encrypted_filename_tokens:
  - "encrypted"
  - "password-protected"
  - "password_protected"
  - "drm-protected"
  - "drm_protected"
```

**Behavior:**

- Case-insensitive, **alphanumeric-boundary-anchored** match against the file basename (compiled once per token as `(?<![A-Za-z0-9])<token>(?![A-Za-z0-9])`).
- This means `unencrypted_notes.pdf`, `UNENCRYPTED_FY25.pdf`, `final_unencrypted.pdf`, `encryption_policy.pdf`, and `EncryptionStandards.docx` do **not** match. `contract_encrypted.pdf`, `Report.ENCRYPTED.v2.pdf`, `ENCRYPTED-v2.pdf`, `Budget_FY25_PASSWORD-PROTECTED.pdf`, and `Report_DRM-Protected_v2.docx` **do** match.
- Multi-word tokens like `password-protected` are treated as a single unit — the boundary check is applied to the whole token, not the internal hyphen.
- Matched files are hashed and skipped with reason `"encrypted file (filename cue: '<token>')"` unless the payload also trips the magic-byte detector, in which case `"encrypted file (magic bytes)"` wins.
- The existing magic-byte detector stays in place and now reports its class as `"encrypted file (magic bytes)"` so the two are visibly distinct in `skip_manifest.json`.
- Name-cue check runs **before** the deferred/format check so the class survives format misrouting.

**Why not a PDF tail-scan for `/Encrypt`?** Tail scanning is an orthogonal enhancement for the magic-byte path (useful specifically for PDFs whose `/Encrypt` dict sits near the trailer rather than the 4 KB head we currently read). It does not generalize — old Office encryption markers sit near the file head, and other formats need container-specific checks. It also does not fix the naming-cue false-positive class, which is what this lane set out to address. If a PDF tail scan is promoted, it belongs in the `_is_encrypted` magic-byte path, not here.

**Reversibility:**

- Operator edits `skip.encrypted_filename_tokens` in `config/config.yaml`.

**Operator visibility:**

- `skip_manifest.json` → `counts_by_reason` → two distinct keys: `"encrypted file (filename cue: '<token>')"` and `"encrypted file (magic bytes)"`.
- Same `run_report.txt` / GUI / log surfacing as image-asset skips.

**Overlap evidence (live config, 2026-04-09, QA pass 3 repro):**

A single `contract_encrypted.pdf` file whose body is `b"%PDF-1.7\n1 0 obj\n<< /Encrypt << /Filter /Standard >> >>\n"` hits both classes. Replaying against the live `config/config.yaml` with `ocr_mode="auto"` and `skip.skip_conditions.encrypted: true`:

```
name     : contract_encrypted.pdf
head     : b'%PDF-1.7\n1 0 obj\n<< /Encrypt << /Filter /Standard >> >>\n'
ocr_mode : auto
skip.skip_conditions.encrypted: True
result   : skip=True reason='encrypted file (magic bytes)'
no-magic : skip=True reason="encrypted file (filename cue: 'encrypted')"
```

The magic-byte class wins on overlap; the filename cue still fires when no magic-byte payload is present. This is locked in by `tests/test_skip_manager.py::test_encrypted_magic_bytes_preferred_over_filename_cue_when_both_match` (fixture-based) and `tests/test_skip_manager.py::test_encrypted_overlap_against_live_runtime_config` (live-config-based).

---

## Report-only (not promoted)

### Recursive folder-signature duplicate bundles

**Decision:** stays report-only pending a precision study on held-out samples per the rule in `docs/CORPUS_ADAPTATION_PLAN_2026-04-09.md:134` ("only promote to auto-skip after confirming precision on held-out samples").

**How operator sees it:**

- Run `scripts/profile_source_corpus.py --root <path> --output-md docs/profile_<date>.md --output-json docs/profile_<date>.json`.
- The profiler groups folders by SHA-256 of a sorted `name|ext|size` manifest of their descendants and emits a `duplicate_folder_signatures` section in both reports.
- Operator reviews the groups manually and decides whether to delete or exclude before the next ingest.

**Why not auto-skip yet:** the Run 6 export does not contain the 700GB source tree; the 90GB sample that produced the profiler's duplicate findings is an aged snapshot. A precision study against a fresh full-corpus Forge export is needed before promoting this to automatic behavior.

### Broader sidecar families (thumbnails, previews, spectrograms outside the IA pattern)

**Decision:** not promoted. The existing `ocr_sidecar_suffixes` list in `config/config.yaml` covers the Internet Archive derivative family. Run 6 has zero hits on thumbnail/preview naming, so adding new patterns would be speculative. The profiler already emits the `spectrogram_image`, `thumbnail_cache_asset`, and `scan_named_image` signals for operator review.

---

## Parse-time waste cut (safely, without hiding files)

Run 6 produced **15,239 image chunks** via `ImageParser._metadata_fallback()`, of which **15,237 are retrieval-noise**. Under the new rules with `parse.ocr_mode == "skip"`:

| Metric | Run 6 (before) | Run 6 (counterfactual, rules active) | Delta |
|---|---:|---:|---:|
| Chunks in export | 242,650 | 227,413 | **−15,237** (−6.28%) |
| Image files reaching `ImageParser` | 15,239 | 0 | −15,239 |
| Image files hashed + listed in `skip_manifest.json` | 0 | 15,239 | +15,239 |
| Hash continuity preserved | ✓ | ✓ | — |
| Files hidden | 0 | 0 | — |

Every file the parser used to burn CPU on now lands in `skip_manifest.json` with its SHA-256, size, and reason — nothing is hidden; the work just moves from "thin parse + thin chunk + thin embed" to "hash and list." On a Tesseract-equipped workstation, `.png/.gif/.bmp/.tif/.tiff/.webp/.wmf/.emf` flow back through `ImageParser` as soon as `parse.ocr_mode` is set to `auto` or `force`. For `.jpg/.jpeg/.svg/.psd`, the operator must additionally remove those extensions from `parse.defer_extensions` (see the two-group table above) — the current config defers them unconditionally for reasons outside this lane. Hash-based dedup recognizes both groups across runs, so any file that is later routed to the parser gets its real text captured on the first OCR-enabled run without reprocessing already-parsed work.

Proof artifact: `docs/SKIP_DEFER_HARDENING_2026-04-09_proof.json` (computed from the real Run 6 `chunks.jsonl`, not synthetic data).

---

## Files changed

```
src/skip/skip_manager.py      (+image_asset + encrypted-name-cue + ocr_mode param)
src/pipeline.py               (pass ocr_mode to SkipManager)
config/config.yaml            (+skip.image_asset_extensions + skip.encrypted_filename_tokens)
tests/test_skip_manager.py    (+13 new tests)
docs/SKIP_DEFER_HARDENING_2026-04-09.md         (this doc)
docs/SKIP_DEFER_HARDENING_2026-04-09_proof.json (counterfactual replay)
```

No changes to: the pipeline stage graph, the chunker, the embedder, the dispatcher, the archive parser, the GUI, the V2 import path, the nightly scheduler, or any config defaults outside the `skip:` section.

## Tests run

```
python -m pytest tests/test_skip_manager.py tests/test_pipeline_e2e.py \
                 tests/test_archive_member_defer.py tests/test_parsers.py -q
```

Result (post-QA-pass-3): **86 passed**. Skip-manager suite grew from 18 → 49 tests (the original 18 baseline plus the hardening + QA-pass-2 + QA-pass-3 regressions). No regressions in parser or pipeline e2e suites.

New skip-manager tests cover:
- image-asset skipped under `ocr_mode="skip"` (4 files × 4 extensions)
- image-asset NOT skipped under `ocr_mode="auto"` and `ocr_mode="force"`
- encrypted-by-filename cue matches `encrypted`, `password-protected`, `DRM-Protected` (case-insensitive)
- encrypted-by-filename cue **does not** false-positive on unrelated names containing substrings like "security"
- encrypted-by-filename cue **does not** false-positive on `unencrypted_notes.pdf`, `UNENCRYPTED_FY25.pdf`, `final_unencrypted.pdf`, `Report-unencrypted-v2.pdf`, or `UnEncryptedArchive.zip`
- encrypted-by-filename cue **does not** false-positive on `encryption_policy.pdf`, `EncryptionStandards.docx`, or `encryption-guide.pdf` (the noun must not match the adjective)
- encrypted-by-filename cue **does** fire on every expected basename form: `contract_encrypted.pdf`, `encrypted_budget.pdf`, `Report.ENCRYPTED.v2.pdf`, `ENCRYPTED-v2.pdf`, `Budget_FY25_PASSWORD-PROTECTED.pdf`, `Report_DRM-Protected_v2.docx`, and `draft encrypted.pdf`
- when a file matches both classes, the reported skip reason is `encrypted file (magic bytes)` rather than the filename cue (`test_encrypted_magic_bytes_preferred_over_filename_cue_when_both_match`)
- the same overlap assertion is also run **against the live `config/config.yaml`** (not an isolated fixture) to prove the in-tree config actually wires `skip.skip_conditions.encrypted = true` (`test_encrypted_overlap_against_live_runtime_config`)
- encrypted-filename cue and encrypted-magic-bytes produce **distinct** reason keys in the skip manifest
- image skips are visible in `skip_manifest.json` with their SHA-256 for restart safety
- parametrized gate matrix: `ocr_mode` × 2 image extensions × 3 modes → 7 combinations
- parametrized boundary matrix: 13 name/should-fire pairs covering the known true-positive and false-positive classes

---

## Answers to the brief's questions

**What should be automatic now?**
- Image-asset hash/defer under `parse.ocr_mode == "skip"` (strong Run 6 evidence: 15,237 junk chunks, 6.28% of corpus).
- Encrypted-by-filename-cue skip with a distinct reason class (generic, low-risk, reversible).

**What should remain report-only pending more evidence?**
- Recursive folder-signature duplicate bundles — available via `scripts/profile_source_corpus.py`, not wired into the pipeline.
- Broader sidecar families (thumbnails, previews, non-IA derivative caches) — 0 hits in Run 6, so promotion would be speculative. Profiler signals remain available.

**How does the operator see each behavior?**
- `skip_manifest.json` → per-reason counts and per-file entries with SHA-256
- `run_report.txt` → `Skip Reasons:` line
- GUI Live Stats → `Files skipped` counter, `Skip reasons:` tile
- Log lines at INFO level: `SKIP: {name} — {reason} (sha256=...)`
- Report-only rules: `scripts/profile_source_corpus.py` markdown + JSON output

**Can parse-time waste be cut safely without hiding files?**
Yes. ~15,237 parse operations (and their downstream chunk/embed work) are eliminated per Run-6-class ingest. Every affected file still exists in `skip_manifest.json` with SHA-256, so nothing is hidden and hash continuity/resume is preserved.

---

## Remaining risk and follow-up

- **Workstation with Tesseract installed:** the new rule is dormant for the Group B set (`.png/.gif/.bmp/.tif/.tiff/.webp/.wmf/.emf`) as soon as `ocr_mode` flips to `auto` or `force`. Group A (`.jpg/.jpeg/.svg/.psd`) remains deferred until the operator also removes those extensions from `parse.defer_extensions` — an edit that is outside this lane's responsibility but is documented in the two-group table above.
- **Workstation with OCR enabled but on a corpus that's truly image-heavy:** Group B flows through the parser as before. The new rule does not interfere once `ocr_mode != "skip"`.
- **Workstation that changes OCR state mid-corpus:** hash continuity is preserved — both the new `image asset (OCR disabled …)` skips and the pre-existing `Deferred by config for this run` skips route through `SkipManager.record_skip`, which writes a `deferred`/`hashed` status row via `Hasher`. A later OCR-enabled run recognizes the file by hash and routes it through the parser without reprocessing work already in the index.
- **Report-only folder-signature duplicates** need a precision study against a fresh full-corpus Forge export before promotion. Flagged for a later slice, not this one.
- **Phase 2 calibration** (per `CORPUS_ADAPTATION_PLAN_2026-04-09.md` §Phase 2) should re-run the Run 6 counterfactual on a 700GB full-corpus export once it lands, to confirm the 6.28% eliminate-rate holds at scale and to decide whether broader sidecar families have enough hits to auto-promote.
- **`parse.defer_extensions` overlap:** four image extensions are currently deferred by the unrelated `parse.defer_extensions` config field. This overlap is documented in the two-group table rather than auto-cleaned; removing image extensions from `parse.defer_extensions` is out of scope for this lane (another lane owns that list).

---

Signed: reviewer | CorpusForge | 2026-04-09 MDT
