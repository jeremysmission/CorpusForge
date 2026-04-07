# Legacy Skip-State Audit 2026-04-07

## Purpose

Audit old source trees for deferred or unsupported files that may never have entered `file_state`.

Use this before a large recovery dedup or rebuild run when restart discovery time has become suspiciously slow.

---

## Safe First Step

Dry run only. This does not write to `file_state`.

```powershell
cd C:\CorpusForge
.\.venv\Scripts\python.exe scripts\backfill_skipped_file_state.py --input "<SOURCE_FOLDER>" --dry-run
```

What it tells you:

- files scanned
- parseable files left alone
- deferred files that would be backfilled
- unsupported files that would be backfilled

---

## Actual Backfill

Only do this after reviewing the dry-run output.

```powershell
cd C:\CorpusForge
.\.venv\Scripts\python.exe scripts\backfill_skipped_file_state.py --input "<SOURCE_FOLDER>"
```

Optional limit for a small pilot:

```powershell
cd C:\CorpusForge
.\.venv\Scripts\python.exe scripts\backfill_skipped_file_state.py --input "<SOURCE_FOLDER>" --limit 500
```

---

## Safety Rule

This tool does **not** mark parseable files as already indexed.

By default it only backfills:

- deferred files
- unsupported files

That keeps the audit useful for restart accounting without poisoning a future real parse/chunk run.

---

## When To Use It

Use it when:

- old transferred lists are untrusted
- a large source tree is about to be deduped
- restart discovery time keeps growing
- old skipped/deferred files may have been rediscovered repeatedly without entering state

---

## Expected Outcome

After backfill:

- intentionally deferred files should already be known to `file_state`
- unsupported files should already be known to `file_state`
- restart discovery should become more stable on legacy trees
