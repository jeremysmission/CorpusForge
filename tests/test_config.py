"""Tests for configuration loading and validation."""
from argparse import Namespace
from pathlib import Path

import pytest
import yaml

from src.config.schema import load_config, ForgeConfig, _deep_merge
from tools.precheck_workstation_large_ingest import _collect_results


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


def test_live_runtime_config_points_skip_rules_at_config_yaml():
    config = load_config("config/config.yaml")
    expected = (Path(__file__).resolve().parent.parent / "config" / "config.yaml").resolve()
    assert Path(config.paths.skip_list).resolve() == expected


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


def test_precheck_reports_runtime_and_skip_defer_sources(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.dump({
        "paths": {
            "source_dirs": [str(tmp_path / "source")],
            "output_dir": str(tmp_path / "output"),
            "state_db": str(tmp_path / "state.sqlite3"),
            "skip_list": str(cfg),
        },
        "embed": {"enabled": False},
        "enrich": {"enabled": False},
        "extract": {"enabled": False},
        "parse": {"defer_extensions": [".sao", ".rsf"]},
    }))
    (tmp_path / "source").mkdir()

    results, summary = _collect_results(Namespace(
        config=str(cfg),
        source=None,
        output=None,
        workers=None,
        ocr_mode=None,
        embed_enabled="0",
        enrich_enabled="0",
        extract_enabled="0",
        embed_batch_size=None,
    ))

    titles = {item.title for item in results}
    assert "Live runtime config" in titles
    assert "Skip/defer source" in titles
    assert summary["runtime_config"].endswith("config.yaml")
    assert summary["skip_defer_source"].endswith("config.yaml")


def test_precheck_resolves_runtime_config_against_project_root_when_cwd_differs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    results, summary = _collect_results(Namespace(
        config="config/config.yaml",
        source=str(tmp_path),
        output=str(tmp_path / "output"),
        workers=1,
        ocr_mode="auto",
        embed_enabled="0",
        enrich_enabled="0",
        extract_enabled="0",
        embed_batch_size=8,
    ))

    expected = (Path(__file__).resolve().parent.parent / "config" / "config.yaml").resolve()
    assert summary["runtime_config"] == str(expected)
    live_runtime_entries = [item for item in results if item.title == "Live runtime config"]
    assert len(live_runtime_entries) == 1
    assert live_runtime_entries[0].proof == str(expected)


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
