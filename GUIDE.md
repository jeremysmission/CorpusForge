# CorpusForge Guide

## Project Overview

CorpusForge is the ingest pipeline that turns raw source documents into query-ready export packages consumed by HybridRAG V2. It handles download, hash/dedup, parsing, chunking, enrichment, embedding, extraction, and export.

## Pipeline

Download -> Hash/Dedup -> Parse -> Chunk -> Enrich -> Embed -> Extract -> Export

## Development Rules

- **500 lines max per class** where practical
- **Use `encoding=\"utf-8-sig\"` for file reads** when dealing with corporate files that may include a BOM
- **Use `encoding=\"utf-8\", newline=\"\\n\"` for file writes**
- **Do not install `sentence-transformers[onnx]` because it can replace CUDA torch**
- **Set `NO_PROXY=127.0.0.1,localhost` in batch and script contexts that need local service access**
- **Set `PYTHONUTF8=1` in workstation batch and script contexts**
- **Use `--trusted-host` flags where corporate proxy behavior requires them**

## Companion Repo

HybridRAG V2 consumes the export packages produced here.

## GPU Notes

- Prefer the less busy GPU when launching heavy embedding or enrichment work
- Check `nvidia-smi` before long-running jobs

## Daily Workstation Reminders

- Use the repo venv explicitly: `.\.venv\Scripts\python.exe` and `.\.venv\Scripts\pip.exe`
- If package installs fail at work, set session proxy vars first:
  - `$env:HTTP_PROXY = "http://centralproxy.northgrum.com:80"`
  - `$env:HTTPS_PROXY = "http://centralproxy.northgrum.com:80"`
  - `$env:NO_PROXY = "127.0.0.1,localhost"`
- On work networks, the durable pip layer is repo-local `.venv\pip.ini`, not memory of a one-off shell session
- `pip-system-certs` is per repo `.venv`; a working install in another repo does not carry over here
- If torch is missing, verify with:
  - `.\.venv\Scripts\pip.exe show torch`
  - `.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available())"`
- If `HybridRAG_V2` already has a working torch install on the same machine, use the copy fallback before re-troubleshooting internet installs

## Installer Standard

All new workstation install, repair, and setup scripts must follow this rule:

- detect first
- repair only what is missing or broken
- preserve working components
- verify the result explicitly

Minimum expectations:

- detect machine Python, repo `.venv`, pip, proxy, GPU, and key dependencies before installing
- detect drift between global Python and repo `.venv`
- detect working installs and skip unnecessary reinstalls
- write repo-local pip config when workstation proxy behavior requires it
- install large packages in grouped, retryable steps when the workstation network is fragile
- use repo-local interpreters and tools explicitly
- fail with a specific diagnosis instead of generic package errors
- do not hide critical install output during bootstrap and repair steps
- end with a real verification block, not just a completed message

Do not use blind shotgun install methods for workstation setup.

## Related Docs

- [WORKSTATION_SETUP_2026-04-06.md](/C:/CorpusForge/docs/WORKSTATION_SETUP_2026-04-06.md)
- [DEDUP_RECOVERY_PLAN_2026-04-06.md](/C:/HybridRAG_V2/docs/DEDUP_RECOVERY_PLAN_2026-04-06.md)
