# Critical E2E Gate

This is the blocking end-to-end gate for production-critical operator workflows.

It exists because narrow lane QA and targeted tests were not enough. The system
must be proven through the actual operator paths and on-disk artifacts.

## Automated Gate

Run from [RUN_CRITICAL_E2E_GATE.bat](C:\CorpusForge\RUN_CRITICAL_E2E_GATE.bat).

Automated checks:

1. Forge workstation precheck
2. Forge dedup-only portable copy
3. Forge normal embed-enabled pipeline export
4. Forge cooperative stop with durable checkpoint
5. Forge compatible rerun/resume from checkpoint
6. V2 import into LanceDB
7. V2 retrieval smoke against imported data
8. V2 API health and query endpoint status

Artifacts:

- JSON report under `C:\CorpusForge\data\critical_e2e_gate\<timestamp>\report.json`
- Markdown report under `C:\CorpusForge\data\critical_e2e_gate\<timestamp>\report.md`

Latest full-pass artifact:

- `C:\CorpusForge\data\critical_e2e_gate\20260410_183757\report.json`
- `C:\CorpusForge\data\critical_e2e_gate\20260410_183757\report.md`

Latest result:

- `PASS` on all automated gates
- V2 live query path passed using saved Windows Credential Manager entries already on this machine
- live Forge embed proof showed `vectors_created > 0` before parse completed
- stop/resume proof showed checkpoint files on disk, a rerun resume event, and a clean `22 chunks / 22 vectors` export

Result policy:

- `PASS`: proved
- `BLOCKED`: environment/service dependency missing; not signoff-ready
- `FAIL`: code or workflow failure

## Manual Blocking Checks

These are still required before a full promotion/signoff. They are not allowed
to hide behind the automated gate.

1. GUI settings save/load
   Code path:
   - [launch_gui.py](C:\CorpusForge\src\gui\launch_gui.py)
   - [settings_panel.py](C:\CorpusForge\src\gui\settings_panel.py)
   What to prove:
   - change workers / OCR / embed toggle / embed batch
   - save
   - close GUI
   - relaunch GUI
   - settings persist and precheck sees the same values

2. GUI button smash
   Code path:
   - [test_gui_button_smash.py](C:\CorpusForge\tests\test_gui_button_smash.py)
   What to prove manually:
   - start/stop
   - dedup-only
   - precheck
   - window resize / scroll behavior
   - no misleading status text

3. Installer clean-venv path
   Code path:
   - [INSTALL_WORKSTATION.bat](C:\CorpusForge\INSTALL_WORKSTATION.bat)
   - [setup_workstation_2026-04-06.ps1](C:\CorpusForge\tools\setup_workstation_2026-04-06.ps1)
   What to prove:
   - clean `.venv`
   - install without Docling
   - install with Docling
   - CUDA torch still valid
   - Poppler/Tesseract warnings are honest

4. Real V2 live query path
   Code path:
   - [server.py](C:\HybridRAG_V2\src\api\server.py)
   - [routes.py](C:\HybridRAG_V2\src\api\routes.py)
   What to prove:
   - imported Forge export
   - `/health` returns loaded counts
   - `/query` returns 200 with configured LLM
   - `/query/stream` streams tokens in the configured environment

## Minimum Signoff Rule

Do not call the system end-to-end validated unless:

1. automated gate is `PASS` except for explicitly documented environment-only `BLOCKED` items
2. manual blocking checks above are completed
3. the report artifact path is attached to the handoff
