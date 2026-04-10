# Daily Workflow — 2026-04-08

This is the default operating model for CorpusForge + HybridRAG V2 catch-up, demo prep, and crash-safe daily execution.

## Goal

Use the available repos, clones, and 2x RTX 3090 GPUs to keep work moving in parallel without corrupting shared state, hiding blockers, or losing recovery context after a crash.

## Default Lane Split

Use 4 working lanes when possible.

1. **reviewer — Forge mainline critical path**
   - Repo: `C:\CorpusForge`
   - Scope: production ingest, dedup state, canonical mainline export
   - GPU: default `GPU 0`
   - Rule: only writer on Forge mainline and production dedup/hash state

2. **reviewer — Forge sample/export lane**
   - Repo: `C:\CorpusForge_Dev`
   - Scope: 90GB sample analysis, canonical 1000-file subset, export package for V2
   - GPU: default `GPU 1` when needed, CPU otherwise
   - Rule: clone-local only, no pushes from clone

3. **reviewer — V2 import/eval lane**
   - Repo: `C:\HybridRAG_V2_Dev`
   - Scope: clone-local import, tiered extraction, retrieval/golden eval, query proof
   - GPU: default `GPU 1` when reviewer is idle or after handoff
   - Rule: do not touch main V2 store until upstream Forge export is accepted

4. **reviewer — Provisioning / config-hardening / operator-surface lane**
   - Scope: workstation prerequisites, installer gaps, demo-safe config presets, root/docs updates, visible operator settings, skip/defer policy hardening
   - GPU: avoid GPU unless explicitly validating CUDA behavior
   - Rule: this lane exists to remove drag from the 3 production lanes

If only 3 working agents are available, keep reviewer, reviewer, and reviewer intact. Do not collapse reviewer and reviewer into one lane unless forced.

## GPU Rules

- Only 2 GPU-heavy lanes should run at once.
- `GPU 0` default: Forge mainline long-running production work.
- `GPU 1` default: subset export work or V2 rehearsal work.
- If both GPUs are active, the next CUDA user takes the lesser-used GPU and documents why.
- CPU-heavy work should stay off GPU whenever possible:
  - docs
  - dedup accounting
  - regex analysis
  - provisioning
  - board updates
  - QA evidence review

## Repo Separation Rules

- Mainline production work stays in `C:\CorpusForge` and `C:\HybridRAG_V2`.
- Experimental, sample, or rehearsal work stays in clone repos:
  - `C:\CorpusForge_Dev`
  - `C:\HybridRAG_V2_Dev`
- Do not let reviewer touch the main V2 store early.
- Do not let reviewer write to Forge mainline.
- Do not let multiple agents share ownership of the same production dedup state or export directory.

## Daily Start Checklist

Before running anything substantial:

1. Confirm lane ownership.
2. Confirm repo path and repo-local venv.
3. Confirm GPU assignment.
4. Confirm data source or subset path.
5. Confirm whether the lane is:
   - production
   - sample
   - clone-local rehearsal
   - provisioning
6. Update both sprint boards if scope changed:
   - `C:\CorpusForge\docs\SPRINT_SYNC.md`
   - `C:\HybridRAG_V2\docs\SPRINT_SYNC.md`

## Metadata and Staleness Rules

- Active lanes must leave a visible trail.
- If more than 10 minutes pass without a metadata write on an active lane, treat it as potentially stale and check in.
- Before any pause longer than 30 minutes, ownership change, or completion claim, the lane must:
  1. update both sprint boards
  2. write a dated evidence or handoff note
  3. record repo, branch, GPU, data path, commands run, outputs, blockers, and next step

## Evidence Packet Minimum

Every serious lane must be recoverable after a crash.

Include:

- repo path
- branch
- venv path
- hardware
- GPU assignment
- source path or subset path
- exact commands run
- output paths
- key metrics
- blocker list
- claim scope
- next step

If the lane touches GUI, also include:

- full GUI harness result
- button smash by a non-author

## Format Skip / Defer Rule

Never hide skip or defer behavior in hardcoded Python.

If a format family is out of scope for the current run:

1. make it visible in config
2. make it visible in boot or preflight output
3. write it into `skip_manifest.json`
4. explain it in `run_report.txt` or the evidence note

Required policy:

- all skip/defer decisions must be operator-visible
- reasons must be written down
- counts by format should be surfaced
- demo-only defers must be explicit, not implied

Examples:

- image-heavy demo runs may defer image formats by config
- scanned PDFs should not be hidden behind a blanket PDF skip unless that is an explicit operator decision

## OCR Rule

Before claiming OCR or scanned-document coverage, verify:

- `where.exe tesseract`
- `where.exe pdftoppm`

If either is missing:

- the lane is text-only unless proven otherwise
- do not claim OCR-ready or full format coverage
- record the gap as an environment prerequisite unless someone overclaimed

## QA Handoff Rule

Do not send QA on a scavenger hunt.

When a lane is ready, provide:

- exact claimed scope
- exact artifact paths
- exact output files expected on disk
- exact blockers still open
- exact reason the lane is ready for QA now

Completion handoff format:

```text
Ready for QA
Signed: <Agent Name> | YYYY-MM-DD HH:MM MDT
```

## Default Unblock Contracts

- reviewer unblocks reviewer by posting the exact export directory containing:
  - `chunks.jsonl`
  - `vectors.npy`
  - `manifest.json`
- reviewer unblocks mainline V2 rebuild planning by producing the accepted Forge export package on mainline.
- reviewer unblocks risky workstation claims by verifying or fixing manual prerequisites and documenting them.

## Practical Operating Guidance

- Let long production runs continue if they are still making real progress.
- Do not kill a useful overnight run unless the lost time is smaller than the restart benefit.
- Use parallel lanes to reduce schedule risk instead of forcing every requirement through one agent.
- Prefer explicit blocked states over speculative inference.
- If a lane is blocked upstream, document the exact unblock artifact and park it.

## Daily Outcome Standard

A good day is not "everyone stayed busy."

A good day means:

- each lane has a clear owner
- each lane has visible artifacts
- blockers are explicit
- QA can validate without reverse-engineering intent
- a crash would not erase the operating picture

---

Signed: CoPilot+ Coordinator | 2026-04-08 MDT
