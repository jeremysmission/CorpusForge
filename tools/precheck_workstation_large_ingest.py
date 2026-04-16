#!/usr/bin/env python
"""
CorpusForge workstation precheck for large-ingest runs.

Designed for operator use before pointing CorpusForge at a large source tree.
Prints a clear readiness summary, writes a dated text report under logs/, and
exits non-zero only on hard blockers.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config.schema import load_config


@dataclass
class CheckResult:
    level: str
    title: str
    proof: str


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _command_version(command: str, args: list[str]) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [command, *args],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = (proc.stdout or proc.stderr or "").strip().splitlines()
        first = output[0].strip() if output else f"exit={proc.returncode}"
        return proc.returncode == 0, first
    except Exception as exc:
        return False, str(exc)


def _resolve_tesseract() -> tuple[str | None, str]:
    env_path = os.getenv("TESSERACT_CMD", "").strip()
    if env_path and Path(env_path).exists():
        return env_path, "env:TESSERACT_CMD"
    found = shutil.which("tesseract") or shutil.which("tesseract.exe")
    if found:
        return found, "PATH"
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate, "fallback path"
    return None, "missing"


def _resolve_pdftoppm() -> tuple[str | None, str]:
    poppler_bin = os.getenv("HYBRIDRAG_POPPLER_BIN", "").strip()
    if poppler_bin:
        candidate = Path(poppler_bin) / "pdftoppm.exe"
        if candidate.exists():
            return str(candidate), "env:HYBRIDRAG_POPPLER_BIN"
    found = shutil.which("pdftoppm") or shutil.which("pdftoppm.exe")
    if found:
        return found, "PATH"
    candidates = [
        r"C:\tools\poppler\Library\bin\pdftoppm.exe",
        r"C:\Program Files\poppler\Library\bin\pdftoppm.exe",
        r"C:\Program Files\poppler\bin\pdftoppm.exe",
        r"C:\poppler\Library\bin\pdftoppm.exe",
        r"C:\poppler\bin\pdftoppm.exe",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate, "fallback path"
    return None, "missing"


def _disk_free_gb(path: Path) -> float:
    probe = path
    if not probe.exists():
        probe = probe.parent
    while probe and not probe.exists():
        probe = probe.parent
    if not probe:
        probe = Path.cwd()
    usage = shutil.disk_usage(probe)
    return usage.free / (1024 ** 3)


def _resolve_runtime_config_path(config_arg: str | Path) -> Path:
    path = Path(config_arg)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


def _collect_results(args: argparse.Namespace) -> tuple[list[CheckResult], dict]:
    runtime_config_path = _resolve_runtime_config_path(args.config)
    config = load_config(runtime_config_path)

    if args.source:
        config.paths.source_dirs = [str(Path(args.source).expanduser().resolve())]
    if args.output:
        config.paths.output_dir = str(Path(args.output).expanduser().resolve())
    if args.workers is not None:
        config.pipeline.workers = args.workers
    if args.ocr_mode:
        config.parse.ocr_mode = args.ocr_mode
    if args.embed_enabled is not None:
        config.embed.enabled = _parse_bool(args.embed_enabled)
    if args.enrich_enabled is not None:
        config.enrich.enabled = _parse_bool(args.enrich_enabled)
    if args.extract_enabled is not None:
        config.extract.enabled = _parse_bool(args.extract_enabled)
    if args.embed_batch_size is not None:
        config.hardware.embed_batch_size = args.embed_batch_size

    source_path = Path(config.paths.source_dirs[0]).expanduser().resolve()
    output_dir = Path(config.paths.output_dir).expanduser().resolve()
    state_db = Path(config.paths.state_db).expanduser().resolve()
    results: list[CheckResult] = []

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if (sys.version_info.major, sys.version_info.minor) == (3, 12):
        results.append(CheckResult("PASS", "Python version", f"{py_ver}"))
    else:
        results.append(CheckResult("FAIL", "Python version", f"{py_ver} (expected 3.12.x)"))

    results.append(CheckResult("PASS", "Live runtime config", str(runtime_config_path)))
    results.append(CheckResult("PASS", "Skip/defer source", str(Path(config.paths.skip_list).resolve())))

    if source_path.exists():
        kind = "directory" if source_path.is_dir() else "file"
        results.append(CheckResult("PASS", "Source path", f"{source_path} ({kind})"))
    else:
        results.append(CheckResult("FAIL", "Source path", f"missing: {source_path}"))

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        results.append(CheckResult("PASS", "Output path", str(output_dir)))
    except Exception as exc:
        results.append(CheckResult("FAIL", "Output path", f"{output_dir} ({exc})"))

    try:
        state_db.parent.mkdir(parents=True, exist_ok=True)
        results.append(CheckResult("PASS", "State DB path", str(state_db)))
    except Exception as exc:
        results.append(CheckResult("FAIL", "State DB path", f"{state_db} ({exc})"))

    logical_threads = os.cpu_count() or 0
    if config.pipeline.workers > logical_threads and logical_threads > 0:
        results.append(
            CheckResult(
                "FAIL",
                "Pipeline workers",
                f"configured={config.pipeline.workers}, logical_threads={logical_threads}",
            )
        )
    elif logical_threads and config.pipeline.workers != logical_threads:
        results.append(
            CheckResult(
                "WARNING",
                "Pipeline workers",
                f"configured={config.pipeline.workers}, logical_threads={logical_threads}",
            )
        )
    else:
        results.append(
            CheckResult(
                "PASS",
                "Pipeline workers",
                f"configured={config.pipeline.workers}, logical_threads={logical_threads}",
            )
        )

    results.append(CheckResult("PASS", "OCR mode", config.parse.ocr_mode))
    results.append(CheckResult("PASS", "Embedding", f"{'ON' if config.embed.enabled else 'OFF'}"))
    results.append(CheckResult("PASS", "Enrichment", f"{'ON' if config.enrich.enabled else 'OFF'}"))
    results.append(CheckResult("PASS", "Entity extraction", f"{'ON' if config.extract.enabled else 'OFF'}"))
    results.append(CheckResult("PASS", "Embed batch size", str(config.hardware.embed_batch_size)))

    if config.embed.enabled and config.embed.device == "cuda":
        try:
            import torch

            if torch.cuda.is_available():
                device_name = torch.cuda.get_device_name(0)
                results.append(CheckResult("PASS", "CUDA torch", device_name))
            else:
                results.append(CheckResult("FAIL", "CUDA torch", "torch.cuda.is_available() == False"))
        except Exception as exc:
            results.append(CheckResult("FAIL", "CUDA torch", str(exc)))
    else:
        results.append(CheckResult("PASS", "CUDA torch", "not required for this run shape"))

    ocr_mode = str(config.parse.ocr_mode).strip().lower()

    tesseract_path, tesseract_source = _resolve_tesseract()
    if ocr_mode == "skip":
        results.append(CheckResult("PASS", "Image OCR runtime", "not required because OCR mode=skip"))
    elif tesseract_path:
        ok, proof = _command_version(tesseract_path, ["--version"])
        level = "PASS" if ok else ("FAIL" if ocr_mode == "force" else "WARNING")
        env_note = ""
        if tesseract_source == "fallback path" and not os.getenv("TESSERACT_CMD", "").strip():
            env_note = " | runtime uses fallback path because TESSERACT_CMD is not set"
        results.append(
            CheckResult(
                level,
                "Image OCR runtime",
                f"Tesseract via {tesseract_source}: {tesseract_path} | {proof}{env_note}",
            )
        )
    else:
        level = "FAIL" if ocr_mode == "force" else "WARNING"
        results.append(
            CheckResult(
                level,
                "Image OCR runtime",
                "no usable Tesseract found on PATH, TESSERACT_CMD, or fallback locations; image OCR will degrade",
            )
        )

    pdftoppm_path, pdftoppm_source = _resolve_pdftoppm()
    if ocr_mode == "skip":
        results.append(CheckResult("PASS", "Scanned-PDF OCR runtime", "not required because OCR mode=skip"))
    elif pdftoppm_path:
        ok, proof = _command_version(pdftoppm_path, ["-h"])
        level = "PASS" if ok else ("FAIL" if ocr_mode == "force" else "WARNING")
        env_note = ""
        if pdftoppm_source == "fallback path" and not os.getenv("HYBRIDRAG_POPPLER_BIN", "").strip():
            env_note = " | runtime uses fallback path because HYBRIDRAG_POPPLER_BIN is not set"
        results.append(
            CheckResult(
                level,
                "Scanned-PDF OCR runtime",
                f"pdftoppm via {pdftoppm_source}: {pdftoppm_path} | {proof}{env_note}",
            )
        )
    else:
        level = "FAIL" if ocr_mode == "force" else "WARNING"
        results.append(
            CheckResult(
                level,
                "Scanned-PDF OCR runtime",
                "no usable pdftoppm.exe found on PATH, HYBRIDRAG_POPPLER_BIN, or fallback locations; scanned-PDF OCR is unavailable",
            )
        )

    output_free_gb = _disk_free_gb(output_dir)
    if output_free_gb < 20:
        results.append(CheckResult("WARNING", "Free disk on output drive", f"{output_free_gb:.1f} GB"))
    else:
        results.append(CheckResult("PASS", "Free disk on output drive", f"{output_free_gb:.1f} GB"))

    env_snapshot = {
        "TESSERACT_CMD": os.getenv("TESSERACT_CMD", ""),
        "HYBRIDRAG_POPPLER_BIN": os.getenv("HYBRIDRAG_POPPLER_BIN", ""),
        "HYBRIDRAG_OCR_MODE": os.getenv("HYBRIDRAG_OCR_MODE", ""),
        "HYBRIDRAG_DOCLING_MODE": os.getenv("HYBRIDRAG_DOCLING_MODE", ""),
        "HTTP_PROXY": os.getenv("HTTP_PROXY", ""),
        "HTTPS_PROXY": os.getenv("HTTPS_PROXY", ""),
        "NO_PROXY": os.getenv("NO_PROXY", ""),
    }

    summary = {
        "runtime_config": str(runtime_config_path),
        "skip_defer_source": str(Path(config.paths.skip_list).resolve()),
        "source_path": str(source_path),
        "output_dir": str(output_dir),
        "state_db": str(state_db),
        "workers": config.pipeline.workers,
        "logical_threads": logical_threads,
        "ocr_mode": config.parse.ocr_mode,
        "embed_enabled": config.embed.enabled,
        "enrich_enabled": config.enrich.enabled,
        "extract_enabled": config.extract.enabled,
        "embed_batch_size": config.hardware.embed_batch_size,
        "defer_extensions": list(config.parse.defer_extensions),
        "env": env_snapshot,
    }
    return results, summary


def _render_report(results: list[CheckResult], summary: dict, report_path: Path) -> str:
    fail_count = sum(1 for item in results if item.level == "FAIL")
    warn_count = sum(1 for item in results if item.level == "WARNING")
    overall = "FAIL" if fail_count else "PASS"

    lines = [
        "=" * 68,
        "CorpusForge Workstation Large-Ingest Precheck",
        "=" * 68,
        f"Timestamp: {datetime.now().isoformat(timespec='seconds')}",
        f"Report:    {report_path}",
        "",
        "Effective run settings:",
        f"  Runtime cfg:    {summary['runtime_config']}",
        f"  Skip/defer src: {summary['skip_defer_source']}",
        f"  Source:         {summary['source_path']}",
        f"  Output:         {summary['output_dir']}",
        f"  State DB:       {summary['state_db']}",
        f"  Workers:        {summary['workers']} (logical threads detected: {summary['logical_threads']})",
        f"  OCR mode:       {summary['ocr_mode']}",
        f"  Defer ext:      {', '.join(summary['defer_extensions']) if summary['defer_extensions'] else '(none)'}",
        f"  Embedding:      {'ON' if summary['embed_enabled'] else 'OFF'}",
        f"  Enrichment:     {'ON' if summary['enrich_enabled'] else 'OFF'}",
        f"  Extraction:     {'ON' if summary['extract_enabled'] else 'OFF'}",
        f"  Embed batch:    {summary['embed_batch_size']}",
        "",
        "Environment snapshot:",
    ]
    for key, value in summary["env"].items():
        lines.append(f"  {key}={value}")
    lines.extend(["", "Checks:"])
    for item in results:
        lines.append(f"  {item.level}: {item.title}")
        lines.append(f"    proof: {item.proof}")
    lines.extend(
        [
            "",
            f"Warnings: {warn_count}",
            f"Failures: {fail_count}",
            f"RESULT: {overall}",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Precheck a workstation before a large CorpusForge ingest."
    )
    parser.add_argument("--config", default=str(PROJECT_ROOT / "config" / "config.yaml"))
    parser.add_argument("--source")
    parser.add_argument("--output")
    parser.add_argument("--workers", type=int)
    parser.add_argument("--ocr-mode")
    parser.add_argument("--embed-enabled")
    parser.add_argument("--enrich-enabled")
    parser.add_argument("--extract-enabled")
    parser.add_argument("--embed-batch-size", type=int)
    args = parser.parse_args()

    results, summary = _collect_results(args)
    report_dir = PROJECT_ROOT / "logs"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"precheck_workstation_{datetime.now():%Y%m%d_%H%M%S}.txt"
    report_text = _render_report(results, summary, report_path)
    report_path.write_text(report_text, encoding="utf-8", newline="\n")
    print(report_text, end="")
    return 2 if any(item.level == "FAIL" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
