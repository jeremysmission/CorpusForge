## CorpusForge — CoPilot+.md

Auto-loaded rules for all agents working in this repo.

### Project

CorpusForge is the ingest pipeline that turns raw documents into query-ready exports for HybridRAG V2. It handles: download, hash, dedup, parse, chunk, enrich, embed, extract entities, and export.

- **Repo:** C:\CorpusForge
- **Venv:** `.venv` (Python 3.12+, torch CUDA cu128)
- **Demo target:** 2026-05-02
- **Cross-repo dependency:** HybridRAG V2 (C:\HybridRAG_V2) consumes chunk exports from this repo
- **Sprint sync:** `docs/SPRINT_SYNC.md` (keep all 3 copies in sync — review board + both repos)

### Code Rules

- **500 lines max per class** (comments/docstrings excluded)
- **Config validated once at boot, immutable after** — no runtime config mutation
- **Single config, no modes** — one hardware preset, machine overrides via `config.local.yaml`
- **DO NOT install `sentence-transformers[onnx]`** — it pulls CPU-only torch, nuking the CUDA wheel
- **CUDA-only embedding** — CPU/ONNX is fallback only
- **No openai SDK** — enricher uses stdlib urllib to talk to Ollama
- **phi4:14b ($0 local) for contextual enrichment** — runs via Ollama
- **GLiNER on CPU** — entity extraction uses batch inference, no GPU needed
- **Lazy model loading** — embedder, enricher, extractor only init when their stage runs
- **Use `encoding="utf-8-sig"` for reads** (corporate files may have BOM)
- **Use `encoding="utf-8", newline="\n"` for writes**

### Config Architecture

```
config/config.yaml          # Base config (committed, single source of truth)
config/config.local.yaml    # Machine-specific overrides (gitignored)
config/skip_list.yaml       # Format skip rules (deferred, placeholder, OCR sidecar)
```

Key tunable settings (override per-machine in config.local.yaml):
- `pipeline.workers` — parallel parse threads (Beast: 16)
- `enrich.max_concurrent` — concurrent Ollama requests (Beast: 3)
- `extract.batch_size` — GLiNER batch inference size (Beast: 32)
- `hardware.embed_batch_size` — GPU embedding batch (Beast: 256)
- `hardware.gpu_index` — which GPU for compute (Beast: 0)

### Dependency Policy

- All new packages: **MIT, Apache 2.0, or BSD** licensed
- All new packages: **USA or NATO ally** country of origin
- **Banned packages:** LangChain, ChromaDB, PyMuPDF (AGPL), sentence-transformers[onnx]
- Check HybridRAG V2's `docs/Requested_Waivers_2026-04-04.md` — shared waiver covers both repos

### Git Rules

- **Sanitize before every remote push:** `python sanitize_before_push.py --apply` then commit, then push
- **Never commit:** `.env`, `credentials.json`, `*.key`, `*.pem`, secrets, large data files
- **Never amend published commits** — create new commits
- **Never force-push** main/master without explicit approval
- **No AI attribution** — use "CoPilot+" only, commits by Jeremy Randall only
- **Sign all review board posts:** `Signed: Agent N (Role) | CorpusForge | YYYY-MM-DD | [Time MDT]`

### Testing

- **77+ tests in `tests/`** — run with `.venv/Scripts/python.exe -m pytest tests/ -v`
- Test on real hardware with real data — virtual-only misses cascading GPU issues
- GUI testing follows V2's QA_GUI_HARNESS protocol (Tiers A-D)

### GPU Rules

- Beast: dual 3090 FE (24GB each). GPU 0 = idle/compute, GPU 1 = display
- Always check `nvidia-smi` before GPU work, pick the lesser-used GPU
- GPU selector runs at pipeline startup (`src/gpu_selector.py`)

### Pipeline Architecture

```
Source files → Hash/Dedup → Skip check → Parallel parse (N workers)
  → Chunk (1200/200) → Enrich (phi4 via Ollama) → Embed (nomic on GPU)
  → Extract entities (GLiNER on CPU) → Export (chunks.jsonl + vectors.npy + entities.jsonl)
```

**Entry points:**
- CLI: `python scripts/run_pipeline.py --input data/source/ --full-reindex`
- GUI: `python scripts/boot.py`

**Export structure:**
```
data/output/export_YYYYMMDD_HHMM/
  chunks.jsonl      # chunk text + metadata
  vectors.npy       # float16 [N, 768]
  entities.jsonl    # GLiNER entity candidates
  manifest.json     # run metadata + stats
  run_report.txt    # human-readable summary
  skip_manifest.json # skipped files with reasons
```

### Related Docs

- `GUIDE.md` — development rules and workstation setup
- `docs/SPRINT_SYNC.md` — cross-repo sprint coordination
- `docs/CHUNK_EXPORT_FOR_AWS_TESTING.md` — export schema and proof results
