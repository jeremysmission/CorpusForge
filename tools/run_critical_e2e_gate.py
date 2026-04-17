#!/usr/bin/env python
"""
Critical end-to-end operator gate across CorpusForge and HybridRAG V2.

What it does for the operator:
  One button that runs the ENTIRE critical path end-to-end, across both
  repos, using real files on disk. It exists to prevent the exact failure
  mode that burned the 700GB run: workflows that were only "mostly
  validated" on narrow slices and broke when exercised as a whole.

Automated gate coverage (each returns PASS or FAIL):
  1. Forge workstation precheck
  2. Forge dedup-only portable copy
  3. Forge normal embed-enabled pipeline export
  4. Forge cooperative stop with durable checkpoint
  5. Forge compatible rerun/resume from checkpoint
  6. V2 import into LanceDB
  7. V2 retrieval smoke against imported data
  8. V2 API health and query endpoint status

How to read the result:
  PASS (exit 0)     All gates green -- safe to proceed.
  BLOCKED (exit 3)  Everything green EXCEPT the live /query endpoint,
                    because an LLM key/endpoint is missing. Operator must
                    configure OPENAI / Azure creds, then re-run.
  FAIL (exit 2)     At least one gate actually failed. Read the report
                    and fix the offending stage BEFORE any new ingest.

When to run it:
  - Before / after major code changes that touch the ingest pipeline
  - As a pre-release gate before an overnight big run
  - Any time a reviewer asks "is this really end-to-end clean?"

Inputs:
  --source    Forge source folder for the gate run.
  --v2-root   HybridRAG V2 repo root (default C:\\HybridRAG_V2).

Outputs:
  data/critical_e2e_gate/<timestamp>/report.json  machine-readable report
  data/critical_e2e_gate/<timestamp>/report.md    human-readable report
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config.schema import load_config
from src.gui.launch_gui import DedupOnlyRunner
from src.gui.safe_after import drain_ui_queue
from src.pipeline import Pipeline


@dataclass
class GateResult:
    """One gate's outcome: PASS/FAIL/BLOCKED, human summary, and machine 'proof' data."""
    status: str
    summary: str
    proof: dict


class _ImmediateRoot:
    """Stand-in for a tkinter root that runs scheduled callbacks immediately (used for headless gate runs)."""
    def after(self, _ms, fn, *args):
        """Invoke fn(*args) right away instead of scheduling it for later."""
        fn(*args)
        return None


class _DedupHarnessApp:
    """Minimal in-memory stand-in for the GUI app, so the dedup-only runner can work headlessly inside this gate."""
    def __init__(self):
        """Create empty log/stats buffers and a 'root' that runs callbacks immediately."""
        self.root = _ImmediateRoot()
        self.logs: list[tuple[str, str]] = []
        self.stats: dict = {}
        self.message: str = ""

    def append_log(self, message: str, level: str = "INFO"):
        """Record a log line so the gate can inspect what the runner said."""
        self.logs.append((level, message))

    def update_dedup_only_stats(self, stats: dict):
        """Receive interim stats from the dedup runner (called as it makes progress)."""
        self.stats = dict(stats)

    def dedup_only_finished(self, stats: dict, message: str = ""):
        """Receive the final stats + message when the dedup runner finishes."""
        self.stats = dict(stats)
        self.message = message


def _write_json(path: Path, payload: dict) -> None:
    """Write a dict to disk as indented JSON (UTF-8, trailing newline)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _run_precheck(source: Path, output_dir: Path) -> GateResult:
    """Gate 1: shell out to the workstation precheck tool and return PASS/FAIL."""
    cmd = [
        str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"),
        str(PROJECT_ROOT / "tools" / "precheck_workstation_large_ingest.py"),
        "--config", str(PROJECT_ROOT / "config" / "config.yaml"),
        "--source", str(source),
        "--output", str(output_dir),
        "--workers", "1",
        "--ocr-mode", "auto",
        "--embed-enabled", "1",
        "--enrich-enabled", "0",
        "--extract-enabled", "0",
        "--embed-batch-size", "256",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    report_line = ""
    result_line = ""
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    for line in combined.splitlines():
        if line.startswith("Report:"):
            report_line = line.split("Report:", 1)[1].strip()
        if line.startswith("RESULT:"):
            result_line = line.split("RESULT:", 1)[1].strip()
    status = "PASS" if proc.returncode == 0 and result_line == "PASS" else "FAIL"
    return GateResult(
        status=status,
        summary=f"precheck {result_line or ('exit ' + str(proc.returncode))}",
        proof={
            "command": cmd,
            "returncode": proc.returncode,
            "result_line": result_line,
            "report_path": report_line,
        },
    )


def _run_dedup_only(source: Path, output_root: Path) -> GateResult:
    """Gate 2: run the dedup-only mode end-to-end and confirm it produced a portable copy folder."""
    # CORPUSFORGE_HEADLESS=1 tells the GUI helpers to skip any tkinter calls.
    os.environ["CORPUSFORGE_HEADLESS"] = "1"
    app = _DedupHarnessApp()
    config = load_config(PROJECT_ROOT / "config" / "config.yaml")
    config.paths.state_db = str(output_root / "dedup_state.sqlite3")
    runner = DedupOnlyRunner(app, config)
    runner._run(str(source), str(output_root), copy_sources=True)
    drain_ui_queue()

    output_dir = Path(app.stats.get("output_dir", ""))
    canonical_path = output_dir / "canonical_files.txt"
    report_path = output_dir / "dedup_report.json"
    portable_dir = output_dir / "deduped_sources"

    copied_files = list(portable_dir.rglob("*")) if portable_dir.exists() else []
    status = (
        "PASS"
        if output_dir.exists()
        and canonical_path.exists()
        and report_path.exists()
        and portable_dir.exists()
        and any(p.is_file() for p in copied_files)
        else "FAIL"
    )
    return GateResult(
        status=status,
        summary=app.message or "dedup-only finished",
        proof={
            "output_dir": str(output_dir),
            "canonical_files_exists": canonical_path.exists(),
            "dedup_report_exists": report_path.exists(),
            "portable_copy_dir": str(portable_dir),
            "portable_files_copied": sum(1 for p in copied_files if p.is_file()),
            "stats": app.stats,
        },
    )


def _build_forge_config(source: Path, output_dir: Path, state_db: Path, *, embed_flush_batch: int) -> object:
    """Build a Forge config tuned for the gate: 1 worker, embed on, enrich/extract off, isolated paths."""
    config = load_config(PROJECT_ROOT / "config" / "config.yaml")
    config.paths.source_dirs = [str(source)]
    config.paths.output_dir = str(output_dir)
    config.paths.state_db = str(state_db)
    config.pipeline.full_reindex = True
    config.pipeline.workers = 1
    config.pipeline.embed_flush_batch = embed_flush_batch
    config.embed.enabled = True
    config.enrich.enabled = False
    config.extract.enabled = False
    return config


def _run_forge_normal(source: Path, run_root: Path) -> GateResult:
    """Gate 3: run the full Forge pipeline once and confirm chunks, vectors, and live progress events."""
    output_dir = run_root / "output"
    state_db = run_root / "state.sqlite3"
    stage_events: list[tuple[str, int, int, str]] = []
    snapshots: list[dict] = []
    files = sorted([p for p in source.rglob("*") if p.is_file()])
    config = _build_forge_config(source, output_dir, state_db, embed_flush_batch=1)
    stats = Pipeline(config).run(
        files,
        on_stage_progress=lambda stage, current, total, detail: stage_events.append(
            (stage, current, total, detail)
        ),
        on_stats_update=lambda snapshot: snapshots.append(dict(snapshot)),
    )
    export_dir = Path(stats.export_dir)
    chunks_path = export_dir / "chunks.jsonl"
    vectors_path = export_dir / "vectors.npy"
    chunk_count = 0
    vector_rows = 0
    vector_dim = 0
    if chunks_path.exists():
        chunk_count = sum(1 for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip())
    if vectors_path.exists():
        import numpy as np
        vectors = np.load(str(vectors_path))
        vector_rows = int(vectors.shape[0])
        vector_dim = int(vectors.shape[1]) if vectors.ndim == 2 else 0
    early_live_snapshot = next(
        (
            snap for snap in snapshots
            if snap.get("vectors_created", 0) > 0 and snap.get("files_parsed", 0) < len(files)
        ),
        None,
    )
    status = (
        "PASS"
        if export_dir.exists()
        and chunk_count > 0
        and chunk_count == vector_rows
        and early_live_snapshot is not None
        else "FAIL"
    )
    return GateResult(
        status=status,
        summary="forge normal run",
        proof={
            "source": str(source),
            "output_dir": str(output_dir),
            "export_dir": str(export_dir),
            "files": len(files),
            "chunks": chunk_count,
            "vectors": vector_rows,
            "vector_dim": vector_dim,
            "early_live_snapshot": early_live_snapshot,
            "first_stage_events": stage_events[:20],
            "stats": stats.to_dict(),
        },
    )


def _run_forge_stop_resume(source: Path, run_root: Path) -> GateResult:
    """Gates 4+5: run Forge, request a stop mid-run, then run again and confirm it resumes from the checkpoint."""
    files = sorted([p for p in source.rglob("*") if p.is_file()])
    output_dir = run_root / "output"
    state_db = run_root / "state.sqlite3"
    checkpoint_dir = output_dir / "_checkpoint_active"

    stop_flag = {"value": False}
    stop_config = _build_forge_config(source, output_dir, state_db, embed_flush_batch=999999)
    stop_events: list[tuple[str, int, int, str]] = []

    def _on_stop_stats(snapshot: dict) -> None:
        if snapshot.get("files_parsed", 0) >= 1:
            stop_flag["value"] = True

    stopped = Pipeline(stop_config).run(
        files,
        on_stage_progress=lambda stage, current, total, detail: stop_events.append(
            (stage, current, total, detail)
        ),
        on_stats_update=_on_stop_stats,
        should_stop=lambda: stop_flag["value"],
    )

    checkpoint_files = sorted(p.name for p in checkpoint_dir.iterdir()) if checkpoint_dir.exists() else []

    resume_config = _build_forge_config(source, output_dir, state_db, embed_flush_batch=1)
    resume_events: list[tuple[str, int, int, str]] = []
    resumed = Pipeline(resume_config).run(
        files,
        on_stage_progress=lambda stage, current, total, detail: resume_events.append(
            (stage, current, total, detail)
        ),
    )

    export_dir = Path(resumed.export_dir)
    chunks_path = export_dir / "chunks.jsonl"
    vectors_path = export_dir / "vectors.npy"
    chunk_count = 0
    vector_rows = 0
    if chunks_path.exists():
        chunk_count = sum(1 for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip())
    if vectors_path.exists():
        import numpy as np
        vectors = np.load(str(vectors_path))
        vector_rows = int(vectors.shape[0])

    resumed_event = next(
        (
            event for event in resume_events
            if event[0] == "parse" and "Resumed " in event[3]
        ),
        None,
    )

    status = (
        "PASS"
        if stopped.stop_requested
        and checkpoint_files
        and resumed_event is not None
        and export_dir.exists()
        and chunk_count == vector_rows
        else "FAIL"
    )
    return GateResult(
        status=status,
        summary="forge stop/resume run",
        proof={
            "stop_stats": stopped.to_dict(),
            "checkpoint_dir": str(checkpoint_dir),
            "checkpoint_files": checkpoint_files,
            "resume_event": resumed_event,
            "resumed_stats": resumed.to_dict(),
            "export_dir": str(export_dir),
            "chunks": chunk_count,
            "vectors": vector_rows,
            "stop_stage_events": stop_events[:20],
            "resume_stage_events": resume_events[:20],
        },
    )


def _run_v2_gate(export_dir: Path, run_root: Path, v2_root: Path) -> GateResult:
    """Gates 6-8: import the Forge export into V2, do a retrieval smoke, and hit the /health + /query endpoints."""
    python_exe = v2_root / ".venv" / "Scripts" / "python.exe"
    script = r"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

import yaml

V2_ROOT = Path(sys.argv[1])
EXPORT_DIR = Path(sys.argv[2])
RUN_ROOT = Path(sys.argv[3])
sys.path.insert(0, str(V2_ROOT))

from fastapi.testclient import TestClient

from scripts.import_embedengine import load_export
from src.api.server import create_app
from src.config.schema import load_config
from src.query.embedder import Embedder
from src.query.vector_retriever import VectorRetriever
from src.store.lance_store import LanceStore

RUN_ROOT.mkdir(parents=True, exist_ok=True)
config_path = RUN_ROOT / "config.e2e.yaml"
lance_db = RUN_ROOT / "lancedb"
entity_db = RUN_ROOT / "entities.sqlite3"

cfg = {
    "paths": {
        "lance_db": str(lance_db),
        "entity_db": str(entity_db),
        "embedengine_output": str(EXPORT_DIR),
        "site_vocabulary": str(V2_ROOT / "config" / "site_vocabulary.yaml"),
    },
    "llm": {
        "provider": "auto",
    },
}
config_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

chunks, vectors, manifest, skip_manifest = load_export(EXPORT_DIR)
store = LanceStore(str(lance_db))
inserted = store.ingest_chunks(chunks, vectors)
store.create_fts_index()
store_count = store.count()

query_text = ""
top_source = ""
top_chunk_id = ""
retrieval_count = 0
if chunks:
    words = [w for w in chunks[0].get("text", "").split() if len(w) >= 4]
    query_text = " ".join(words[:12]) or chunks[0].get("text", "")[:120]
    embedder = Embedder(
        model_name="nomic-ai/nomic-embed-text-v1.5",
        dim=768,
        device="cuda",
    )
    retriever = VectorRetriever(store, embedder, top_k=3)
    results = retriever.search(query_text, top_k=3)
    retrieval_count = len(results)
    if results:
        top_source = results[0].source_path
        top_chunk_id = results[0].chunk_id

app = create_app(str(config_path))
client = TestClient(app)
health = client.get("/health")
query_resp = client.post("/query", json={"query": query_text or "test", "top_k": 3})
stream_resp = client.post("/query/stream", json={"query": query_text or "test", "top_k": 3})

payload = {
    "inserted": inserted,
    "store_count": store_count,
    "query_text": query_text,
    "retrieval_count": retrieval_count,
    "top_source": top_source,
    "top_chunk_id": top_chunk_id,
    "health_status": health.status_code,
    "health_body": health.json(),
    "query_status": query_resp.status_code,
    "query_body": query_resp.json() if "application/json" in query_resp.headers.get("content-type", "") else query_resp.text,
    "stream_status": stream_resp.status_code,
    "stream_head": stream_resp.text[:400],
    "llm_env_present": {
        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY", "")),
        "AZURE_OPENAI_API_KEY": bool(os.getenv("AZURE_OPENAI_API_KEY", "")),
        "AZURE_OPENAI_ENDPOINT": bool(os.getenv("AZURE_OPENAI_ENDPOINT", "")),
    },
}
print(json.dumps(payload))
"""
    proc = subprocess.run(
        [str(python_exe), "-", str(v2_root), str(export_dir), str(run_root)],
        cwd=str(v2_root),
        input=script,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        return GateResult(
            status="FAIL",
            summary="v2 import/retrieval failed",
            proof={
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            },
        )
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    payload = json.loads(lines[-1])
    if payload["query_status"] == 200:
        status = "PASS"
        summary = "v2 import, retrieval, api health, and query passed"
    elif payload["query_status"] == 503:
        status = "BLOCKED"
        summary = "v2 import/retrieval passed, but live query is blocked by missing LLM configuration"
    else:
        status = "FAIL"
        summary = f"unexpected /query status {payload['query_status']}"
    return GateResult(status=status, summary=summary, proof=payload)


def _render_markdown(results: dict[str, GateResult], report_json: Path) -> str:
    """Render the final gate results as a Markdown doc for a human reviewer."""
    lines = [
        "# Critical E2E Gate",
        "",
        f"- Timestamp: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Report JSON: `{report_json}`",
        "",
        "| Gate | Status | Summary |",
        "|---|---|---|",
    ]
    for name, result in results.items():
        lines.append(f"| {name} | {result.status} | {result.summary} |")
    lines.append("")
    lines.append("## Details")
    for name, result in results.items():
        lines.append("")
        lines.append(f"### {name}")
        lines.append(f"- Status: `{result.status}`")
        lines.append(f"- Summary: {result.summary}")
        lines.append("```json")
        lines.append(json.dumps(result.proof, indent=2, ensure_ascii=False))
        lines.append("```")
    return "\n".join(lines) + "\n"


def main() -> int:
    """Run every gate in order, write the JSON + Markdown reports, and return 0 (PASS) / 2 (FAIL) / 3 (BLOCKED)."""
    parser = argparse.ArgumentParser(description="Run the critical operator E2E gate.")
    parser.add_argument(
        "--source",
        default=str(PROJECT_ROOT / "data" / "smoke_pipeline_doc_realhw" / "source"),
        help="Forge source folder for the gate.",
    )
    parser.add_argument(
        "--v2-root",
        default=r"C:\HybridRAG_V2",
        help="HybridRAG V2 repo root.",
    )
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    v2_root = Path(args.v2_root).expanduser().resolve()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = PROJECT_ROOT / "data" / "critical_e2e_gate" / timestamp
    run_root.mkdir(parents=True, exist_ok=True)

    results: dict[str, GateResult] = {}
    results["forge_precheck"] = _run_precheck(source, run_root / "precheck_output")
    results["forge_dedup_only"] = _run_dedup_only(source, run_root / "dedup_only")
    results["forge_normal_pipeline"] = _run_forge_normal(source, run_root / "forge_normal")
    results["forge_stop_resume"] = _run_forge_stop_resume(source, run_root / "forge_stop_resume")

    export_dir = Path(results["forge_normal_pipeline"].proof.get("export_dir", ""))
    if export_dir.exists():
        results["v2_import_retrieval_api"] = _run_v2_gate(export_dir, run_root / "v2_gate", v2_root)
    else:
        results["v2_import_retrieval_api"] = GateResult(
            status="FAIL",
            summary="skipped because forge normal export did not materialize",
            proof={},
        )

    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "v2_root": str(v2_root),
        "results": {name: asdict(result) for name, result in results.items()},
    }
    report_json = run_root / "report.json"
    report_md = run_root / "report.md"
    _write_json(report_json, report)
    report_md.write_text(_render_markdown(results, report_json), encoding="utf-8", newline="\n")

    print(json.dumps(report, indent=2, ensure_ascii=False))

    terminal_states = {result.status for result in results.values()}
    if "FAIL" in terminal_states:
        return 2
    if "BLOCKED" in terminal_states:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
