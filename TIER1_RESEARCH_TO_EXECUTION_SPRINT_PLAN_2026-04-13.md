# Tier1 Research To Execution Sprint Plan 2026-04-13

## Purpose

This is a high-visibility coordinator reference copied into the Forge repo so future agents working across both repos do not lose the current Tier 1 conclusions.

The active execution of Tier 1 cleanup belongs to `HybridRAG_V2`, but `CorpusForge` still needs visibility because upstream export/integrity work and downstream Tier 1 cleanup are tightly coupled in planning and handoff.

## Frozen Conclusions

These points are treated as settled unless new evidence disproves them:

1. Tier 1 regex is a **candidate generator**, not the final truth layer.
2. `PO` is overloaded and should eventually split into:
   - `BUSINESS_PO`
   - `REPORT_ID`
3. No future full Tier 1 rerun should happen before:
   - adversarial gate pass
   - preserve-set pass
   - shadow-run review
4. Security/control namespaces must be rejected by **shape-aware** rules.
5. Ambiguous identifiers should fail closed unless there is positive business context.
6. The long-term production model is:
   - stage
   - audit
   - promote

## Why This Matters In Forge

Forge is not responsible for Tier 1 extraction, but it is still part of the same production path:

- Forge controls the upstream export shape and integrity
- V2 controls downstream import, retrieval, extraction, and evaluation
- future coordinators need one shared story across both repos

## Research Already Completed In V2

The Tier 1 research and hardening work has already been done in `HybridRAG_V2` and should be referenced there rather than recreated here.

Primary V2 references:

- `HybridRAG_V2/docs/TIER1_REGEX_ACCEPTANCE_GATE_2026-04-12.md`
- `HybridRAG_V2/docs/TIER1_REGEX_CORPUS_AUDIT_2026-04-12.md`
- `HybridRAG_V2/docs/TIER1_REGEX_CORPUS_AUDIT_2026-04-12_RERUN.md`
- `HybridRAG_V2/docs/TIER1_REGEX_GATE_RUNBOOK_2026-04-12.md`
- `HybridRAG_V2/docs/TIER1_REGEX_RESEARCH_SYNTHESIS_2026-04-12.md`
- `HybridRAG_V2/TIER1_PROACTIVE_QUALITY_PLAN_2026-04-12.md`

## Cross-Repo Plan

### Forge Responsibility

- keep export/integrity/metadata work honest
- do not overclaim downstream cleanup from upstream-only changes
- preserve the manifest and contract discipline already added

### V2 Responsibility

1. run the automated Tier 1 gate
2. run the `5,000-10,000` chunk shadow Tier 1 slice
3. approve or reject the full rerun using measured evidence
4. run one clean full Tier 1 rerun
5. rerun the 400-query baseline on the cleaned store

## What Future Coordinators Should Not Redo

Do **not** relitigate these already-researched conclusions without new hard evidence:

- the old live Tier 1 store is polluted in `PO` and `PART`
- a blind full rerun is the wrong validation mechanism
- regex-only truth is too brittle
- shape-aware blocked-namespace rules are better than naive prefix-only blocking
- staged promotion is the right long-term model

## Forge-Side Handoff Note

If a future coordinator starts in Forge and needs the current Tier 1 story, the shortest correct handoff is:

"Forge-side integrity and metadata contract work is done enough for now. The active blocker is in V2: run the Tier 1 gate, run the shadow Tier 1 slice, approve one clean full rerun only if the shadow run is clean, then rerun the 400-query baseline on the cleaned store."

## One-Paragraph Summary

The Tier 1 lane has already finished the important research. The project now knows that regex should be treated as candidate generation with validation, that shadow-run approval is mandatory before a full rerun, and that future data should follow a stage-audit-promote path. Forge keeps the upstream side honest, but the active execution lane is now in V2.
