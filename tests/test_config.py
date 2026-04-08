"""Tests for configuration loading, validation, and local overrides."""
import tempfile
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
    }))
    c = load_config(str(cfg))
    assert c.chunk.size == 800
    assert c.chunk.overlap == 100
    assert c.pipeline.workers == 4


def test_load_config_local_override(tmp_path):
    base = tmp_path / "config.yaml"
    base.write_text(yaml.dump({
        "pipeline": {"workers": 8, "log_level": "INFO"},
        "chunk": {"size": 1200},
    }))
    local = tmp_path / "config.local.yaml"
    local.write_text(yaml.dump({
        "pipeline": {"workers": 16},
    }))
    c = load_config(str(base))
    assert c.pipeline.workers == 16
    assert c.pipeline.log_level == "INFO"
    assert c.chunk.size == 1200


def test_load_config_no_local_file(tmp_path):
    base = tmp_path / "config.yaml"
    base.write_text(yaml.dump({"pipeline": {"workers": 12}}))
    c = load_config(str(base))
    assert c.pipeline.workers == 12


# --- validation ---

def test_chunk_overlap_must_be_less_than_size():
    with pytest.raises(Exception):
        ForgeConfig(chunk={"size": 100, "overlap": 200})


def test_ocr_mode_rejects_invalid():
    with pytest.raises(Exception):
        ForgeConfig(parse={"ocr_mode": "banana"})


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
