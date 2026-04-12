# Forge Export Integrity Checklist

Date: 2026-04-12
Repo: `C:\CorpusForge`
Audience: operator validating a fresh Forge desktop export before any real HybridRAG_V2 import

## Purpose

Provide one lightweight handoff gate for a large Forge export.

This checklist is designed for full production exports where loading the entire corpus into memory just to audit it is unnecessary risk.

Tonight's mandatory gate is:

1. required artifacts exist
2. `manifest.json`, `chunks.jsonl`, and `vectors.npy` agree on count
3. `run_report.txt` and `skip_manifest.json` are readable and sane
4. HybridRAG_V2 accepts the export in `--dry-run` mode

## Mandatory Tonight

Do these steps on the fresh desktop export before any real V2 import:

1. capture the export directory path
2. verify required artifacts exist
3. run the lightweight count-alignment gate
4. review the run report and skip summary
5. run the HybridRAG_V2 dry-run import

If any mandatory gate fails, hold the export and investigate. Do not move on to `--create-index`.

## Optional Later

Optional later work, not required tonight:

- deeper corpus audit on smaller exports or when RAM headroom is available
- richer artifact analysis using failure lists or adaptation tooling
- a real V2 import with `--create-index`

## Not Solved By This Checklist

Passing this checklist does not mean:

- Tier 2 is clean
- Tier 1 entities are clean in V2
- demo-ready aggregation claims are safe
- family-aware metadata is present in the export

This checklist only validates the Forge export and the basic Forge -> V2 handoff contract.

## Step 1: Capture The Export Path

From PowerShell:

```powershell
cd C:\CorpusForge
$export = (
  Get-ChildItem .\data\production_output -Directory -Filter 'export_*' |
  Sort-Object Name -Descending |
  Select-Object -First 1
).FullName
Write-Host "Export path: $export"
```

All later steps assume `$export` is set to the target export directory.

## Step 2: Required Artifact Presence Gate

From PowerShell:

```powershell
$required = @(
  'chunks.jsonl',
  'vectors.npy',
  'manifest.json',
  'run_report.txt',
  'skip_manifest.json',
  'entities.jsonl'
)

foreach ($name in $required) {
  $path = Join-Path $export $name
  if (-not (Test-Path $path)) {
    throw "Missing required artifact: $path"
  }
}

Write-Host "Artifact gate: PASS"
```

Mandatory result:

```text
Artifact gate: PASS
```

## Step 3: Lightweight Count-Alignment Gate

Run this from `C:\CorpusForge` so the repo venv is available:

```powershell
cd C:\CorpusForge
@'
import json
import sys
from pathlib import Path

import numpy as np

export = Path(sys.argv[1])
manifest = json.loads((export / "manifest.json").read_text(encoding="utf-8-sig"))
skip_manifest = json.loads((export / "skip_manifest.json").read_text(encoding="utf-8-sig"))

chunk_lines = 0
with open(export / "chunks.jsonl", encoding="utf-8-sig") as handle:
    for line in handle:
        if line.strip():
            chunk_lines += 1

vectors = np.load(export / "vectors.npy", mmap_mode="r")
manifest_count = int(manifest.get("chunk_count", -1))
manifest_dim = int(manifest.get("vector_dim", -1))
vector_rows, vector_dim = int(vectors.shape[0]), int(vectors.shape[1])

print(f"manifest.chunk_count={manifest_count:,}")
print(f"chunks.jsonl_lines={chunk_lines:,}")
print(f"vectors.rows={vector_rows:,}")
print(f"manifest.vector_dim={manifest_dim}")
print(f"vectors.dim={vector_dim}")
print(f"manifest.entity_count={manifest.get('entity_count', 'MISSING')}")
print(f"skip.total_skipped={skip_manifest.get('total_skipped', 'MISSING')}")

issues = []
if manifest_count != chunk_lines:
    issues.append("manifest chunk_count does not match chunks.jsonl line count")
if vector_rows != chunk_lines:
    issues.append("vectors.npy row count does not match chunks.jsonl line count")
if manifest_dim != vector_dim:
    issues.append("manifest vector_dim does not match vectors.npy dimension")

if issues:
    for item in issues:
        print(f"FAIL: {item}")
    raise SystemExit(2)

print("Count alignment: PASS")
'@ | .\.venv\Scripts\python.exe - $export
```

Mandatory result:

```text
Count alignment: PASS
```

## Step 4: Run Report And Skip Summary Review

Review the human-readable run report:

```powershell
Get-Content (Join-Path $export 'run_report.txt') -Tail 60
```

What you want to see:

- `Files parsed` is greater than zero
- `Chunks created` is greater than zero
- `Vectors created` matches `Chunks created`
- `Entities found` may be zero for this Phase 1 packet

Review the skip/defer summary:

```powershell
Get-Content (Join-Path $export 'skip_manifest.json') -Head 80
```

What you want to see:

- the file parses cleanly
- skip reasons look explainable from the current config
- there is no sign the export silently dropped files without accounting for them

## Step 5: Export Audit Step For Tonight

Tonight's required export audit is the combination of:

- artifact presence gate
- count-alignment gate
- run report review
- skip summary review

That is the required audit for a large export.

Do not treat `scripts/audit_corpus.py` as tonight's mandatory gate for a full 10M-class export. It is better suited to smaller exports or later analysis when RAM headroom is not a concern.

## Step 6: HybridRAG_V2 Dry-Run Import Validation

From PowerShell:

```powershell
cd C:\HybridRAG_V2
.\.venv\Scripts\python.exe .\scripts\import_embedengine.py --source $export --dry-run
```

Mandatory success signals:

- no required-file errors
- no chunk/vector mismatch error
- no manifest rejection
- no strict validation failure
- dry-run summary prints the expected chunk and vector counts

Useful follow-up after the dry run:

```powershell
Get-ChildItem $export -Filter 'import_report_*_dry_run.json' |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
```

If a dry-run report JSON was written, keep it with the export evidence.

## Pass / Hold / Fail

### Pass To Handoff

All of these are true:

- artifact presence gate passes
- count-alignment gate passes
- run report is readable and sane
- skip manifest is readable and sane
- V2 `--dry-run` import passes

### Hold For Review

Any of these is true:

- Forge exited `2` but the export still exists
- the export looks usable, but the run report needs explanation
- the V2 dry run passes but the failure count in Forge needs coordinator review

### Fail

Any of these is true:

- missing required artifacts
- manifest/chunk/vector counts do not align
- V2 dry-run rejects the export
- no fresh export directory was written

## If This Checklist Passes

The export is ready for the next operator decision:

- either hold it as a validated export package
- or proceed to a real HybridRAG_V2 import with `--create-index` when that lane is authorized

## Related Docs

- [FORGE_DESKTOP_RERUN_PACKET_2026-04-12.md](./FORGE_DESKTOP_RERUN_PACKET_2026-04-12.md)
- [OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md](./OPERATOR_700GB_INGEST_RUNBOOK_2026-04-09.md)
