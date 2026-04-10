# Changelog

This file retroactively tracks notable changes from git metadata for `CorpusForge`.

The repo did not use formal release tags or semantic versions during the initial buildout, so the historical sections below are grouped by commit date. Future revisions should keep `Unreleased` at the top and cut explicit versions only when a meaningful integrated change lands.

## Unreleased

- Revision policy and formal version tagging not yet started.

## 2026-04-09

### Added

- Workstation runbooks, precheck flow, and clean Run 6 handoff materials.
- Short morning operator quickstart for the handoff path.

### Changed

- Hashed-state persistence was added so successful hash work can survive restarts.
- Runtime configuration was simplified around the active `config/config.yaml` path.

### Notes

- This is the latest committed history point as of `2026-04-09T18:45:39-06:00` (`734b98b`).

## 2026-04-08

### Added

- Operator quickstart and run-history support.
- Concurrent GLiNER extraction control through config.
- Recovery action plan refresh and a GUI/CLI dedup-only guide.
- Sprint 6 bulk-transfer, dedup-fix, GUI-progress, and sanitizer work.

### Changed

- CPU reservation logic was hardened with affinity, priority, thread caps, and later QA fixes.
- Sprint 6 fixes tightened sanitizer behavior, GUI extraction handling, dedup behavior, and GLiNER wiring.

## 2026-04-07

### Added

- Dedup accounting hardening, skip-state audit workflow, dedup-review workflow, and format-coverage policy.
- New Sprint 2 and subsequent work on lazy model init, config-driven formats, enrichment pre-flight, and GPU selection.
- GUI settings panel with worker, toggle, and chunk controls.
- OCR sidecar junk filtering based on prior-system lessons.
- Expanded test suite, headless-mode hardening, and E2E chunk-export proof.
- Sprint 3 enrichment stdlib rewrite, GLiNER extraction, parallel workers, format coverage, and `--strip-enrichment`.
- Full exposure of worker and batch controls in both `config.yaml` and the GUI.
- Reset-to-defaults support, GUI button-smash coverage, audit tooling, run history, and Task Scheduler support.

### Changed

- GUI settings validation and rapid-click handling were hardened.
- This day marks the shift from basic pipeline operation into a configurable operator surface.

## 2026-04-06

### Added

- Recovery dedup stage and GUI.
- Workstation setup hardening, offline torch recovery, and CUDA fallback paths.
- Dedup review tooling and multiple workstation runbooks.
- Installer pause/assessment controls and a fast AWS probe profile.

### Changed

- Install and workstation prep became explicit operational lanes rather than scattered notes.

## 2026-04-05

### Added

- Contextual enrichment pipeline with chunk preambles.
- Fifteen additional parsers and dependency expansion to reach 50+ format coverage.
- Tkinter GUI with live pipeline stats.
- Parallel 8-worker pipeline and throughput controls.

### Changed

- Requirements were corrected for embedding dependencies.
- Early benchmark and compatibility work established the first practical high-throughput ingestion path.

## 2026-04-04

### Added

- Initial repo, walking-skeleton sprint plan, config schemas, minimal pipeline, and boot validation.
- Sprint 1 parser stack, hash/dedup path, and dispatcher foundation.
- Initial remote-push sanitization step.

### Changed

- The repo moved from a minimal ingest skeleton to a real multi-format pipeline on day one.

## Notes

- This is a retroactive changelog assembled from commit metadata on `2026-04-09`.
- Historical entries are grouped by milestone day because the repo did not yet maintain formal semantic-version releases.
- Repeated sanitize and sprint-sync commits are retained in the appendix for auditability, but summarized into the adjacent workday section above.

## Appendix: Commit Metadata Ledger

| Timestamp | SHA | Subject |
|---|---:|---|
| `2026-04-04T18:35:32-06:00` | `52845ee` | Initial CorpusForge repo: nightly ingest pipeline for HybridRAG V2 |
| `2026-04-04T18:57:22-06:00` | `e31796b` | Add unified Walking Skeleton sprint plan across both repos |
| `2026-04-04T21:33:57-06:00` | `36d17f9` | Sprint 0: config schemas, minimal pipeline, boot validation |
| `2026-04-04T21:34:28-06:00` | `8e39361` | Sanitize for remote push |
| `2026-04-04T21:45:07-06:00` | `8db89ab` | Sprint 1: 21-format parser stack, hash/dedup, dispatcher |
| `2026-04-05T10:50:49-06:00` | `a633be3` | feat: contextual enrichment pipeline — phi4:14b chunk preambles for 67% retrieval improvement |
| `2026-04-05T12:05:38-06:00` | `a42a573` | feat: 15 new parsers + skip-list infrastructure — 50+ format coverage |
| `2026-04-05T12:21:38-06:00` | `7a03fc0` | feat: add 8 parser dependencies (xlrd, olefile, ezdxf, dpkt, vsdx, etc.) for 50+ format coverage |
| `2026-04-05T12:59:10-06:00` | `76a0bf4` | feat: CorpusForge Tkinter GUI — pipeline monitor with live stats |
| `2026-04-05T15:03:19-06:00` | `73f9b37` | feat: parallel 8-worker pipeline, workstation setup scripts, compatibility fixes |
| `2026-04-05T15:35:11-06:00` | `ed6eb80` | fix: add einops to requirements — required by nomic-embed-text trust_remote_code |
| `2026-04-05T18:41:38-06:00` | `933d57d` | sprint6: benchmark pipeline controls for throughput runs |
| `2026-04-06T08:00:34-06:00` | `97e9585` | feat: add recovery dedup stage and GUI |
| `2026-04-06T08:24:01-06:00` | `34f1936` | install: harden workstation setup lane |
| `2026-04-06T08:24:33-06:00` | `22ad3e9` | docs: sanitize workstation install guide |
| `2026-04-06T10:34:57-06:00` | `6e84d80` | install: clarify torch proxy failures |
| `2026-04-06T10:50:19-06:00` | `732eb12` | install: add blackwell torch recovery lane |
| `2026-04-06T12:05:03-06:00` | `62a812d` | install: fix workstation setup and offline torch recovery |
| `2026-04-06T12:22:27-06:00` | `84219d1` | install: add cu124 to cu128 torch fallback |
| `2026-04-06T17:27:05-06:00` | `5f9a394` | docs: rename root guide and add workstation notes |
| `2026-04-06T18:11:42-06:00` | `9a47623` | docs: add dedup review tool and guide |
| `2026-04-06T18:36:20-06:00` | `414fa54` | docs: carry forward proven workstation setup lessons |
| `2026-04-06T19:24:27-06:00` | `04b30eb` | docs: add workstation laptop chunk vetting runbook |
| `2026-04-06T19:51:51-06:00` | `573b076` | tools: pause root workstation installer on exit |
| `2026-04-06T20:22:18-06:00` | `093ce56` | tools: align workstation setup with assessment pause |
| `2026-04-06T21:17:28-06:00` | `c66861f` | config: add fast aws probe profile |
| `2026-04-07T07:50:47-06:00` | `941ed7a` | Harden Forge operator dedup accounting |
| `2026-04-07T07:52:51-06:00` | `a268923` | Add legacy skip-state audit workflow |
| `2026-04-07T07:53:50-06:00` | `0c1aef8` | Document approved dedup review workflow |
| `2026-04-07T07:54:44-06:00` | `8f8c176` | Document Forge format coverage policy |
| `2026-04-07T20:17:19-06:00` | `9ad69b5` | sprint: new Sprint 2 (unblock chunking + config formats + GUI settings) |
| `2026-04-07T20:40:07-06:00` | `60ea28b` | feat: lazy model init, config-driven formats, enrichment pre-flight, GPU selection |
| `2026-04-07T20:51:57-06:00` | `babb163` | feat: GUI settings panel with workers, toggles, chunk params |
| `2026-04-07T20:53:04-06:00` | `6cf1e7f` | feat: config.local.yaml support for machine-specific overrides |
| `2026-04-07T20:55:35-06:00` | `8b33f8e` | feat: OCR sidecar junk filter — 17 patterns from V1 lesson |
| `2026-04-07T21:23:42-06:00` | `ff950bb` | feat: 77 tests + headless mode hardening |
| `2026-04-07T21:31:00-06:00` | `aad89c7` | docs: chunk export guide for AWS AI enrichment testing |
| `2026-04-07T21:44:37-06:00` | `0cd2fc6` | sprint 2.4: E2E chunk export proof — 198 files, 17695 chunks, vectors match |
| `2026-04-07T21:47:30-06:00` | `4d2d483` | sanitize: clean SPRINT_SYNC.md before remote push |
| `2026-04-07T22:22:50-06:00` | `969a2a0` | feat: Sprint 3 — enrichment stdlib rewrite, GLiNER extraction, parallel workers |
| `2026-04-07T22:25:40-06:00` | `49d2f65` | feat: Sprint 3 slices 3.3+3.4 — run report, format coverage, --strip-enrichment |
| `2026-04-07T22:26:23-06:00` | `3a80490` | sprint 3: all slices DONE, sync + sanitize SPRINT_SYNC.md |
| `2026-04-07T22:39:17-06:00` | `68e7635` | feat: expose all worker/batch controls in config.yaml and GUI |
| `2026-04-07T22:40:25-06:00` | `1782e61` | fix: GUI settings validation + rapid-click debounce |
| `2026-04-07T22:46:03-06:00` | `fb53d73` | feat: Reset to Defaults button in GUI settings panel |
| `2026-04-07T23:20:39-06:00` | `35465f8` | feat: Sprint 4 — CLAUDE.md, GUI button smash, audit tool, run history, Task Scheduler |
| `2026-04-08T01:07:42-06:00` | `7a3db63` | feat: Sprint 5 — operator quickstart doc + run history |
| `2026-04-08T05:55:08-06:00` | `deed970` | feat: concurrent GLiNER extraction — extract.max_concurrent config |
| `2026-04-08T07:56:04-06:00` | `cd714ab` | docs: recovery action plan + sprint sync + dedup guides |
| `2026-04-08T07:57:22-06:00` | `91d71e8` | docs: dedup-only pass operator guide — GUI and CLI instructions |
| `2026-04-08T12:15:18-06:00` | `cacceab` | feat: Sprint 6 — bulk transfer, dedup fix, GUI progress, sanitizer |
| `2026-04-08T12:16:51-06:00` | `ca46fbf` | fix: 3-layer CPU reservation — affinity + priority + thread cap |
| `2026-04-08T19:16:20-06:00` | `5b35900` | fix: QA fixes for Sprint 6 — sanitizer, GUI extraction, dedup, gliner |
| `2026-04-09T07:32:07-06:00` | `81ac857` | Ship workstation runbooks, precheck, and clean Run 6 handoff |
| `2026-04-09T07:38:51-06:00` | `d08e224` | Add short morning operator quickstart |
| `2026-04-09T18:45:39-06:00` | `734b98b` | Persist hashed state and simplify runtime config |
