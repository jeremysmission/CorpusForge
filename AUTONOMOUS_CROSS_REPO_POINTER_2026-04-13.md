# Autonomous Cross Repo Pointer 2026-04-13

## Purpose

This is the Forge-side visibility pointer for unattended work while the user is away.

The active Beast-side critical path is currently in `HybridRAG_V2`, not Forge.

## Active Execution Reference

Use this V2 document as the live coordinator/work log:

- `HybridRAG_V2/AUTONOMOUS_EXECUTION_PLAN_AND_STATUS_2026-04-13.md`

## Forge-Side Parallel Work

If a workstation is available and healthy, the best Forge-side parallel work is:

1. update `C:\CorpusForge`
2. run `INSTALL_WORKSTATION.bat`
3. run `PRECHECK_WORKSTATION_700GB.bat`
4. if `RESULT: PASS`, run the approved Phase 1 headless rerun
5. run `scripts/check_export_integrity.py`
6. validate the export with V2 dry-run import

Primary Forge references:

- [docs/FORGE_DESKTOP_RERUN_PACKET_2026-04-12.md](./docs/FORGE_DESKTOP_RERUN_PACKET_2026-04-12.md)
- [docs/FORGE_EXPORT_INTEGRITY_CHECKLIST_2026-04-12.md](./docs/FORGE_EXPORT_INTEGRITY_CHECKLIST_2026-04-12.md)

## Short Summary

Forge-side integrity and rerun instructions are already in place. The current Beast-side blocker is the V2 Tier 1 shadow-run approval path.
