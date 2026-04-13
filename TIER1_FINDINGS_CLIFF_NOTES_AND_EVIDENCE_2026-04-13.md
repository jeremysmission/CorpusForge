# Tier1 Findings Cliff Notes And Evidence 2026-04-13

## Purpose

This is a Forge-side visibility copy of the Tier 1 findings summary so future cross-repo coordinators do not have to reconstruct the state of the cleanup lane.

The active execution lives in `HybridRAG_V2`, but the evidence trail matters in Forge because upstream/downstream handoffs are part of the same production story.

## Cliff Notes

1. The old V2 live Tier 1 store was polluted enough that `PO` and `PART` could not be treated as trustworthy business-facing fields.
2. The project already did the important research. Future coordinators should not restart the argument from zero.
3. The agreed execution model is:
   - run the regex gate
   - run a `5,000-10,000` chunk shadow Tier 1 slice
   - approve or reject the full rerun
   - only then run one clean full Tier 1 rerun
4. Future deltas should eventually follow:
   - stage
   - audit
   - promote

## Primary Evidence Lives In V2

Reference these V2 docs:

- `HybridRAG_V2/docs/TIER1_REGEX_ACCEPTANCE_GATE_2026-04-12.md`
- `HybridRAG_V2/docs/TIER1_REGEX_CORPUS_AUDIT_2026-04-12.md`
- `HybridRAG_V2/docs/TIER1_REGEX_CORPUS_AUDIT_2026-04-12_RERUN.md`
- `HybridRAG_V2/docs/TIER1_REGEX_GATE_RUNBOOK_2026-04-12.md`
- `HybridRAG_V2/docs/TIER1_REGEX_RESEARCH_SYNTHESIS_2026-04-12.md`
- `HybridRAG_V2/TIER1_RESEARCH_TO_EXECUTION_SPRINT_PLAN_2026-04-13.md`

## Repo-History Proof Points

Key V2 commits already landed:

- `34b64d8` Tighten Tier 1 PO and part boundary guards
- `d0476bb` docs: audit tier1 PO and PART confusion sets
- `54eadec` docs: add tier1 regex corpus rerun audit
- `f3bafb7` Add Tier 1 regex pre-rerun gate
- `a45e62f` strengthen tier1 regex gate curated cases
- `1620084` docs: formalize tier1 regex acceptance gate
- `e94d704` docs: add Tier 1 regex research synthesis

## One-Paragraph Forge-Side Summary

Forge-side integrity and metadata work are no longer the main blocker. The active blocker is in V2: execute the already-researched Tier 1 cleanup path once, cleanly. The current evidence base already proves the old Tier 1 store was polluted, the hardening work exists, and external research supports a gate-plus-shadow-run approach before any full rerun. Future coordinators should treat that as the current truth unless they have stronger evidence.
