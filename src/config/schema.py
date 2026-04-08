"""
CorpusForge configuration schema.

Single config, no modes. Validated once at boot, immutable after.
Priority: config.yaml values -> Pydantic defaults.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class PathsConfig(BaseModel):
    """File system paths used by the pipeline."""

    source_dirs: list[str] = Field(
        default=["data/source"],
        description="Directories containing raw source files to process.",
    )
    output_dir: str = Field(
        default="data/output",
        description="Where export packages are written for V2 consumption.",
    )
    state_db: str = Field(
        default="data/file_state.sqlite3",
        description="SQLite database tracking file hashes and processing state.",
    )
    landing_zone: str = Field(
        default="data/source",
        description="Local directory where downloaded files are staged.",
    )
    skip_list: str = Field(
        default="config/skip_list.yaml",
        description="YAML file defining formats and conditions to skip (hash only).",
    )


class ChunkConfig(BaseModel):
    """Chunking parameters — ported from V1 (1200/200/sentence boundary)."""

    size: int = Field(default=1200, ge=100, le=10000, description="Target chunk size in characters.")
    overlap: int = Field(default=200, ge=0, description="Character overlap between consecutive chunks.")
    max_heading_len: int = Field(default=160, ge=10, description="Max line length to consider as a heading.")

    @model_validator(mode="after")
    def overlap_less_than_size(self) -> "ChunkConfig":
        if self.overlap >= self.size:
            raise ValueError(f"overlap ({self.overlap}) must be less than size ({self.size})")
        return self


class ParseConfig(BaseModel):
    """Parser settings."""

    timeout_seconds: int = Field(default=60, ge=5, description="Per-file parse timeout.")
    ocr_mode: str = Field(
        default="auto",
        description="OCR mode: 'skip' | 'auto' | 'force'. 'auto' detects scanned PDFs.",
    )
    max_chars_per_file: int = Field(default=5_000_000, ge=1000, description="Clamp file text to this length.")
    defer_extensions: list[str] = Field(
        default_factory=list,
        description="Extensions to hash and skip for this run even if a parser exists.",
    )

    @field_validator("ocr_mode")
    @classmethod
    def validate_ocr_mode(cls, v: str) -> str:
        allowed = {"skip", "auto", "force"}
        if v not in allowed:
            raise ValueError(f"ocr_mode must be one of {allowed}, got '{v}'")
        return v

    @field_validator("defer_extensions")
    @classmethod
    def normalize_defer_extensions(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            ext = (value or "").strip().lower()
            if not ext:
                continue
            if not ext.startswith("."):
                ext = f".{ext}"
            normalized.append(ext)
        return list(dict.fromkeys(normalized))


class EmbedConfig(BaseModel):
    """Embedding model and batching settings."""

    enabled: bool = Field(default=True, description="Enable embedding stage. Disable for chunk-only exports.")
    model_name: str = Field(
        default="nomic-ai/nomic-embed-text-v1.5",
        description="HuggingFace model ID for sentence-transformers.",
    )
    dim: int = Field(default=768, description="Embedding vector dimensions.")
    device: str = Field(
        default="cuda",
        description="Compute device: 'cuda' or 'cpu'.",
    )
    max_batch_tokens: int = Field(
        default=49152,
        description="Token budget per embedding batch (6x nomic context window).",
    )
    dtype: str = Field(
        default="float16",
        description="Embedding precision: 'float16' | 'float32'.",
    )

    @field_validator("device")
    @classmethod
    def validate_device(cls, v: str) -> str:
        allowed = {"cuda", "cpu"}
        if v not in allowed:
            raise ValueError(f"device must be one of {allowed}, got '{v}'")
        return v


class EnrichConfig(BaseModel):
    """Contextual enrichment via phi4:14B on local Ollama."""

    enabled: bool = Field(default=True, description="Enable contextual enrichment stage.")
    ollama_url: str = Field(
        default="http://127.0.0.1:11434",
        description="Ollama API base URL (loopback only).",
    )
    model: str = Field(default="phi4:14b-q4_K_M", description="Ollama model tag for enrichment.")
    max_chunk_chars: int = Field(
        default=500,
        description="Max chars of chunk text sent to enrichment model (for speed).",
    )
    max_concurrent: int = Field(
        default=2,
        ge=1, le=8,
        description="Concurrent enrichment requests to Ollama. "
                    "Higher = faster but needs more GPU VRAM. Beast: 2-3. "
                    "Set per-machine in config.local.yaml.",
    )


class ExtractConfig(BaseModel):
    """First-pass entity extraction via GLiNER2."""

    enabled: bool = Field(default=False, description="Enable GLiNER2 NER stage (requires waiver).")
    model_name: str = Field(
        default="urchade/gliner_multi-v2.1",
        description="GLiNER model for zero-shot NER.",
    )
    entity_types: list[str] = Field(
        default=[
            "PART_NUMBER", "PERSON", "SITE", "DATE",
            "ORGANIZATION", "FAILURE_MODE", "ACTION",
        ],
        description="Entity labels for GLiNER extraction.",
    )
    min_confidence: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="Minimum GLiNER confidence to include in candidates.",
    )
    batch_size: int = Field(
        default=16,
        ge=1, le=128,
        description="Batch size for GLiNER inference. Higher = faster but more RAM. "
                    "Beast: 16, workstation: 20-32. Set per-machine in config.local.yaml.",
    )


class PipelineConfig(BaseModel):
    """Pipeline orchestration settings."""

    full_reindex: bool = Field(default=False, description="Process all files, not just new/changed.")
    max_files: Optional[int] = Field(default=None, ge=1, description="Limit files processed per run (for testing).")
    log_level: str = Field(default="INFO", description="Logging level.")
    workers: int = Field(default=8, ge=1, le=32, description="Parallel parser threads. GPU embed runs on main thread.")
    stale_future_timeout: int = Field(default=120, ge=30, description="Seconds before watchdog kills a hung parser.")
    embed_flush_batch: int = Field(default=512, ge=32, description="Chunks accumulated before flushing to GPU embed.")


class HardwarePreset(BaseModel):
    """Hardware-specific overrides."""

    gpu_index: int = Field(default=0, description="Primary GPU index for compute (0=compute, 1=display).")
    embed_batch_size: int = Field(default=256, ge=1, description="Embedding batch size hint.")


# ---------------------------------------------------------------------------
# Top-level config
# ---------------------------------------------------------------------------

class ForgeConfig(BaseModel):
    """
    CorpusForge top-level configuration.

    Single config, no modes. One hardware preset selected at boot.
    """

    model_config = {"extra": "forbid"}

    paths: PathsConfig = Field(default_factory=PathsConfig)
    chunk: ChunkConfig = Field(default_factory=ChunkConfig)
    parse: ParseConfig = Field(default_factory=ParseConfig)
    embed: EmbedConfig = Field(default_factory=EmbedConfig)
    enrich: EnrichConfig = Field(default_factory=EnrichConfig)
    extract: ExtractConfig = Field(default_factory=ExtractConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    hardware: HardwarePreset = Field(default_factory=HardwarePreset)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Override wins on conflicts."""
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: str | Path = "config/config.yaml") -> ForgeConfig:
    """
    Load and validate CorpusForge configuration from YAML.

    Loading order:
      1. config.yaml (base, committed to git)
      2. config.local.yaml (machine-specific overrides, gitignored)

    config.local.yaml is optional and only overrides the keys it defines.
    Use it for machine-specific settings like workers, GPU index, paths.

    Falls back to Pydantic defaults for any missing fields.
    """
    path = Path(config_path)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()

    if path.exists():
        with open(path, encoding="utf-8-sig") as f:
            raw = yaml.safe_load(f) or {}
    else:
        print(f"[WARN] Config file not found at {path}, using defaults.", file=sys.stderr)
        raw = {}

    # Apply config.local.yaml overrides if present (gitignored, machine-specific)
    local_path = path.parent / "config.local.yaml"
    if local_path.exists():
        with open(local_path, encoding="utf-8-sig") as f:
            local_raw = yaml.safe_load(f) or {}
        if local_raw:
            raw = _deep_merge(raw, local_raw)
            print(f"[INFO] Applied local overrides from {local_path}", file=sys.stderr)

    paths = raw.setdefault("paths", {})
    path_keys = ("source_dirs", "output_dir", "state_db", "landing_zone", "skip_list")
    for key in path_keys:
        if key not in paths:
            continue
        value = paths[key]
        if key == "source_dirs":
            resolved_dirs: list[str] = []
            for entry in value or []:
                entry_path = Path(entry)
                if not entry_path.is_absolute():
                    entry_path = (PROJECT_ROOT / entry_path).resolve()
                resolved_dirs.append(str(entry_path))
            paths[key] = resolved_dirs
            continue

        entry_path = Path(value)
        if not entry_path.is_absolute():
            paths[key] = str((PROJECT_ROOT / entry_path).resolve())

    return ForgeConfig(**raw)
