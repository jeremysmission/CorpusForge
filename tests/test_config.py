"""Tests for configuration loading and validation."""
from pathlib import Path

import pytest
import yaml

from src.config.schema import load_config, ForgeConfig, _deep_merge


# --- deep merge ---

def test_deep_merge_override_scalar():
    base = {"a": 1, "b": 2}
    override = {"b": 99}
    assert _deep_merge(base, override) == {"a": 1, "b": 99}


def test_deep_merge_nested():
    base = {"pipeline": {"workers": 8, "log_level": "INFO"}}
    override = {"pipeline": {"workers": 16}}
    result = _deep_merge(base, override)
    assert result["pipeline"]["workers"] == 16
    assert result["pipeline"]["log_level"] == "INFO"


def test_deep_merge_adds_new_keys():
    base = {"a": 1}
    override = {"b": 2}
    assert _deep_merge(base, override) == {"a": 1, "b": 2}


def test_deep_merge_empty_override():
    base = {"a": 1}
    assert _deep_merge(base, {}) == {"a": 1}


# --- config loading ---

def test_load_config_defaults():
    """Config loads with Pydantic defaults when file missing."""
    c = load_config("/nonexistent/config.yaml")
    assert c.chunk.size == 1200
    assert c.chunk.overlap == 200
    assert c.pipeline.workers == 8
    assert c.embed.dim == 768


def test_load_config_from_yaml(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.dump({
        "chunk": {"size": 800, "overlap": 100},
        "pipeline": {"workers": 4},
        "nightly_delta": {"transfer_workers": 6},
    }))
    c = load_config(str(cfg))
    assert c.chunk.size == 800
    assert c.chunk.overlap == 100
    assert c.pipeline.workers == 4
    assert c.nightly_delta.transfer_workers == 6


def test_load_config_uses_single_explicit_file(tmp_path):
    base = tmp_path / "config.yaml"
    base.write_text(yaml.dump({
        "pipeline": {"workers": 12, "log_level": "INFO"},
        "chunk": {"size": 1200},
    }))
    c = load_config(str(base))
    assert c.pipeline.workers == 12
    assert c.pipeline.log_level == "INFO"
    assert c.chunk.size == 1200


def test_load_config_normalizes_defer_extensions(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.dump({
        "parse": {"defer_extensions": [".dwg", "jpg", ".sao", "rsf", ".jpg"]},
    }))
    c = load_config(str(cfg))
    assert c.parse.defer_extensions == [".dwg", ".jpg", ".sao", ".rsf"]


def test_load_config_resolves_nightly_delta_paths(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.dump({
        "nightly_delta": {
            "source_root": "relative_source",
            "mirror_root": "relative_mirror",
            "transfer_state_db": "relative_transfer.sqlite3",
            "manifest_dir": "relative_manifests",
            "pipeline_output_dir": "relative_output",
            "pipeline_state_db": "relative_state.sqlite3",
            "pipeline_log_dir": "relative_logs",
            "stop_file": "relative_stop.flag",
        },
    }))
    c = load_config(str(cfg))
    assert Path(c.nightly_delta.source_root).is_absolute()
    assert Path(c.nightly_delta.mirror_root).is_absolute()
    assert Path(c.nightly_delta.transfer_state_db).is_absolute()
    assert Path(c.nightly_delta.manifest_dir).is_absolute()
    assert Path(c.nightly_delta.pipeline_output_dir).is_absolute()
    assert Path(c.nightly_delta.pipeline_state_db).is_absolute()
    assert Path(c.nightly_delta.pipeline_log_dir).is_absolute()
    assert Path(c.nightly_delta.stop_file).is_absolute()


def test_task_start_time_normalizes_and_validates():
    c = ForgeConfig(nightly_delta={"task_start_time": "2:5"})
    assert c.nightly_delta.task_start_time == "02:05"

    with pytest.raises(Exception):
        ForgeConfig(nightly_delta={"task_start_time": "25:00"})


# --- validation ---

def test_chunk_overlap_must_be_less_than_size():
    with pytest.raises(Exception):
        ForgeConfig(chunk={"size": 100, "overlap": 200})


def test_ocr_mode_rejects_invalid():
    with pytest.raises(Exception):
        ForgeConfig(parse={"ocr_mode": "banana"})


def test_docling_mode_rejects_invalid():
    with pytest.raises(Exception):
        ForgeConfig(parse={"docling_mode": "banana"})


def test_embed_device_rejects_invalid():
    with pytest.raises(Exception):
        ForgeConfig(embed={"device": "tpu"})


def test_workers_range():
    c = ForgeConfig(pipeline={"workers": 1})
    assert c.pipeline.workers == 1
    c = ForgeConfig(pipeline={"workers": 32})
    assert c.pipeline.workers == 32
    with pytest.raises(Exception):
        ForgeConfig(pipeline={"workers": 0})


def test_embed_enabled_field():
    c = ForgeConfig(embed={"enabled": False})
    assert c.embed.enabled is False
    c = ForgeConfig(embed={"enabled": True})
    assert c.embed.enabled is True
