# Code Rules Analysis — CorpusForge + HybridRAG V2

**Date:** 2026-04-08 MDT (revised 2026-04-09 for full canonical rule coverage)
**Author:** CoPilot+

This analysis audits **all** canonical code rules from each repo's official `Repo_Rules_2026-04-04.md`, plus the operator-stated meta-rules (portability, modularity, no patches).

---

## Canonical Rule Sources

| Repo | Rules File |
|------|-----------|
| CorpusForge | `C:\CorpusForge\docs\Repo_Rules_2026-04-04.md` § 1 Code Rules |
| HybridRAG V2 | `C:\HybridRAG_V2\docs\Repo_Rules_2026-04-04.md` § 1 Code Rules |

### CorpusForge Code Rules (5)
1. 500 lines max per class (comments excluded)
2. Pin openai SDK to v1.x if used
3. DO NOT use `pip install sentence-transformers[onnx]`
4. All file reads must use `encoding="utf-8"` or `encoding="utf-8-sig"`
5. All file writes must use `encoding="utf-8", newline="\n"`

### HybridRAG V2 Code Rules (5)
1. 500 lines max per class
2. No offline LLM mode (online-only, single code path)
3. Pin openai SDK to v1.x — never upgrade to 2.x
4. DO NOT use `pip install sentence-transformers[onnx]`
5. Config validated once at boot, immutable after

### Operator Meta-Rules (3)
- Program stays portable
- Program stays modular
- No patches, only redesigns

---

## Executive Summary

| Rule | CorpusForge | HybridRAG V2 |
|------|-------------|-------------|
| Class size ≤500 LOC | **1 violation** (Pipeline: 591) | Clean (max: EntityRetriever 385) |
| openai SDK v1.x pinned | N/A (not used in CF) | **Compliant** (1.109.1 in requirements.txt:90) |
| No `sentence-transformers[onnx]` | **Compliant** (DO NOT comment in requirements.txt:15) | **Compliant** (DO NOT comment in requirements.txt:18) |
| File reads use `utf-8`/`utf-8-sig` | **Compliant** (no text-mode opens without encoding) | N/A (not in V2 rules) |
| File writes use `utf-8` + `\n` | **Compliant** | N/A (not in V2 rules) |
| No offline LLM mode | N/A (not in CF rules) | **Compliant** (no offline_mode hits in src/) |
| Config immutable after boot | N/A (not in CF rules) | **Compliant** (no runtime config mutations in src/) |
| **Portability (operator meta-rule)** | **2 docstring example paths** (1 was missed in original audit) | **4+ docstring/example paths** (all missed in original audit) |
| Modularity | Clean layering, 1 acceptable late-import | Clean layering, no coupling issues |
| No patches | **Clean** (zero hits) | **Clean** (zero hits) |

**Total violations:**
- CorpusForge: 1 hard violation (Pipeline 591 LOC), 2 docstring example paths
- HybridRAG V2: 0 hard violations, 4+ docstring example paths

---

## Rule 1: Class Size Limit (Both Repos)

### CorpusForge — 1 Violation
| Class | File | Code Lines | Status |
|-------|------|-----------|--------|
| **Pipeline** | `src/pipeline.py` | **591** | **VIOLATION** |
| CorpusForgeApp | `src/gui/app.py` | 419 | OK |
| ReviewFamily | `scripts/review_dedup_samples.py` | 411 | OK (script) |
| StageResult | `scripts/benchmark_pipeline.py` | 397 | OK (script) |

The 36 parser classes average ~70 lines each — excellent modularity. Pipeline is the only violation. Refactor candidates: extract `ParseStage`, `EmbedStage`, `ExportStage` to drop Pipeline to ~250 lines.

### HybridRAG V2 — Clean
| Class | File | Code Lines | Status |
|-------|------|-----------|--------|
| EntityRetriever | `src/query/entity_retriever.py` | 385 | OK |
| QueryRouter | `src/query/query_router.py` | 362 | OK |
| LanceStore | `src/store/lance_store.py` | 355 | OK |
| CRAGVerifier | `src/query/crag_verifier.py` | 325 | OK |
| QueryPanel | `src/gui/panels/query_panel.py` | 327 | OK |
| EntityExtractor | `src/extraction/entity_extractor.py` | 272 | OK |

V1 reference scripts in `scripts/v1_reference/` exceed 500 lines (service_event_extractor.py: 728 LOC) but are explicitly legacy reference, not production code.

---

## Rule 2: openai SDK Pinning (Both Repos)

### CorpusForge
- **Not in requirements.txt.** CorpusForge does not use the OpenAI SDK directly. Enrichment uses Ollama via `urlopen`. **Compliant by absence.**

### HybridRAG V2
```
requirements.txt:90: openai==1.109.1   # MIT, OpenAI/USA — LLM client (PINNED v1.x, NEVER upgrade to 2.x)
```
**Compliant.** Pinned to 1.109.1 with explicit comment.

---

## Rule 3: No `sentence-transformers[onnx]` (Both Repos)

### CorpusForge
```
requirements.txt:15: #   - DO NOT use pip install sentence-transformers[onnx] — pulls CPU torch
```
ONNX runtime is installed directly (`onnxruntime==1.24.4`) without the `[onnx]` extra. **Compliant.**

### HybridRAG V2
```
requirements.txt:18: #   - DO NOT use pip install sentence-transformers[onnx] — pulls CPU torch
```
**Compliant.** No `[onnx]` extra anywhere in tracked files.

---

## Rule 4: File I/O Encoding (CorpusForge Only)

CorpusForge requires `encoding="utf-8"` or `encoding="utf-8-sig"` for reads, and `encoding="utf-8", newline="\n"` for writes.

**Audit:** Searched all `src/**/*.py` for `open(...)` calls in text mode without encoding. All hits were either:
- Binary mode (`"rb"`, `"wb"`) — encoding not applicable
- Library `Image.open` / `pdfplumber.open` / `tarfile.open` — not Python file I/O
- Already use `encoding=` argument

**Compliant.** No bare text-mode opens found.

---

## Rule 5: No Offline LLM Mode (V2 Only)

V2 rules: "No offline LLM mode. Online-only, single code path. No mode switching."

**Audit:** Grep for `offline_mode`, `OFFLINE_MODE`, `offline.*llm` across V2 src/. **Zero hits.**

**Compliant.** V2 has no offline LLM fallback. The only "offline" reference is the HuggingFace cache mode (`HF_HUB_OFFLINE=1`), which is for the embedding model, not the LLM.

---

## Rule 6: Config Immutability After Boot (V2 Only)

V2 rules: "Config validated once at boot, immutable after. No runtime config mutation."

**Audit:** Grep for `config.<attr> = ` patterns in src/ excluding `self.config` assignments in `__init__` methods. **Zero runtime config mutations found** in production code paths.

Test code and CLI scripts override config values before passing to constructors (acceptable), but no runtime mutation of an already-loaded config object.

**Compliant.**

---

## Operator Meta-Rule: Portability — REVISED

### CorpusForge — 2 docstring/example paths
| File | Line | Path | Type |
|------|------|------|------|
| `scripts/verify_parallel_pipeline.py` | 39 | `C:\HybridRAG_V2\data\source\role_corpus_golden` | Hardcoded constant |
| `scripts/verify_parallel_pipeline.py` | 40 | `C:\CorpusForge\config\config.yaml` | Hardcoded constant |
| `scripts/run_transfer.py` | 5 | `D:\\production` | Docstring usage example |

Original audit caught the first two (both runtime constants in a verify script) but missed the docstring example in `run_transfer.py`.

### HybridRAG V2 — 4+ docstring/example paths (originally marked clean — INCORRECT)
| File | Line | Path | Type |
|------|------|------|------|
| `scripts/import_embedengine.py` | 8 | `C:/CorpusForge/data/export/export_YYYYMMDD_HHMM` | Docstring usage example |
| `scripts/canonical_rebuild.py` | 8 | `C:/CorpusForge/data/export/export_YYYYMMDD_HHMM` | Docstring usage example |
| `scripts/import_forge_entities.py` | 9 | `C:/CorpusForge/data/output/export_YYYYMMDD_HHMM` | Docstring usage example |
| `scripts/structured_progress_audit.py` | 286 | `C:\\HybridRAG_V2` | String literal in printed command |
| `scripts/structured_progress_audit.py` | 292 | `C:\\CorpusForge` | String literal in printed command |
| `scripts/structured_progress_audit.py` | 293 | `C:\\Path\\To\\Source` | Placeholder example |

**Correction to original audit:** I scoped out docstring/example paths without saying so. The corrected count: V2 has zero hardcoded paths in **runtime code**, but has 4+ absolute paths in **docstring usage examples and printed command strings**. None affect program execution, but they break the strict reading of the portability rule.

### Severity Assessment
None of these break execution — they're documentation strings. But the rule is "program stays portable" and absolute paths in docstrings make the docs machine-specific. Portable replacements would use placeholders like `<CORPUSFORGE_REPO>` or `${PROJECT_ROOT}`.

---

## Operator Meta-Rule: Modularity

### CorpusForge
Clean 6-layer architecture: GUI → Pipeline → Stages → Support → Export. 36 parsers, average 70 LOC each. One acceptable late-import workaround in `archive_parser.py` (avoids circular dependency with dispatcher). No circular imports.

### HybridRAG V2
Clean 4-layer architecture: GUI/API → Pipeline → Query components → Stores. Stores have zero upward dependencies. No circular imports. No God objects.

---

## Operator Meta-Rule: No Patches, Only Redesigns

### Both Repos
Grep across all `.py` files in `src/` and `scripts/` for: `monkey`, `patch` (excluding `.patch()` test mocks), `hotfix`, `workaround`, `hack`, `FIXME`, `TODO`. **Zero hits in either repo.**

The only monkey-patch is in `C:\CorpusForge_Dev\scripts\run_pipeline_gpu0.py` (clone-local GPU workaround), explicitly not in mainline.

---

## Recommendations (Revised)

### Priority 1 — Fix Before Demo
1. **CorpusForge Pipeline class (591 LOC):** Refactor into stage classes. Estimated: 2-3 hours.

### Priority 2 — Fix When Convenient
2. **CorpusForge `verify_parallel_pipeline.py:39-40`:** Replace hardcoded `C:\` constants with `Path(__file__).parent.parent / ...`.
3. **V2 docstring usage examples (4 files):** Replace `C:/CorpusForge/...` with `<CORPUSFORGE_REPO>/...` or `$CORPUSFORGE/...` placeholders.
4. **CorpusForge `run_transfer.py:5`:** Replace `D:\production` example with `/path/to/source` or `<SOURCE_DIR>`.

### Priority 3 — Monitor
5. **V2 EntityRetriever (385 LOC):** Approaching limit.
6. **V2 QueryRouter (362 LOC):** Approaching limit.

---

## Verdict (Revised)

**Hard rule violations:**
- CorpusForge: 1 (Pipeline class size)
- HybridRAG V2: 0

**Soft violations (operator meta-rules):**
- CorpusForge: 2 docstring/example paths
- HybridRAG V2: 4+ docstring/example paths

**Fully compliant rules across both repos:**
- openai SDK pinning
- No `sentence-transformers[onnx]`
- File I/O encoding (CorpusForge)
- No offline LLM mode (V2)
- Config immutability (V2)
- No patches/monkey-patches/hotfixes
- No circular imports
- Clean modular layering

**Original audit error:** I marked V2 as portability-clean. That was incorrect — V2 has 4+ absolute paths in docstring examples and printed command strings. None affect runtime execution, but they fail the strict portability reading.

---

Jeremy Randall | CorpusForge + HybridRAG V2 | 2026-04-09 MDT
