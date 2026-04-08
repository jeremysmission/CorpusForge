"""End-to-end pipeline tests — chunk-only and full pipeline on real files."""
import json
from pathlib import Path

import numpy as np
import pytest

from src.config.schema import load_config
from src.pipeline import Pipeline


@pytest.fixture
def source_dir(tmp_path):
    """Create a temp source dir with test files."""
    src = tmp_path / "source"
    src.mkdir()
    (src / "report.txt").write_text(
        "Quarterly Maintenance Report\n\n"
        "Station: Riverside Observatory\n"
        "Date: 2024-03-15\n\n"
        "The transmitter output power was measured at 1.2 kW nominal.\n"
        "Field technician Mike Torres performed the inspection.\n"
        "Parts replaced: WR-4471 RF Connector (x2).\n"
        "Status: All systems operational.\n"
    )
    (src / "email.txt").write_text(
        "From: ravi.patel@example.com\n"
        "Subject: CH3 Noise Issue Workaround\n\n"
        "Team,\n\nThe workaround for the CH3 noise issue is to bypass\n"
        "the secondary filter bank. This was validated on site.\n"
    )
    (src / "data.csv").write_text(
        "part_number,description,status\n"
        "WR-4471,RF Connector,IN STOCK\n"
        "PO-2024-0501,Power Supply,IN TRANSIT\n"
    )
    return src


@pytest.fixture
def config_chunk_only(source_dir, tmp_path):
    """Config for chunk-only mode (no models loaded)."""
    c = load_config()
    c.embed.enabled = False
    c.enrich.enabled = False
    c.extract.enabled = False
    c.pipeline.full_reindex = True
    c.paths.source_dirs = [str(source_dir)]
    c.paths.output_dir = str(tmp_path / "output")
    c.paths.state_db = str(tmp_path / "state.sqlite3")
    return c


# --- chunk-only mode ---

def test_chunk_only_produces_chunks(config_chunk_only):
    p = Pipeline(config_chunk_only)
    files = sorted(Path(config_chunk_only.paths.source_dirs[0]).rglob("*"))
    files = [f for f in files if f.is_file()]
    stats = p.run(files)
    assert stats.files_parsed == 3
    assert stats.chunks_created > 0
    assert stats.vectors_created == 0  # No embedding
    assert stats.chunks_enriched == 0  # No enrichment
    assert len(stats.errors) == 0


def test_chunk_only_writes_jsonl(config_chunk_only):
    p = Pipeline(config_chunk_only)
    files = sorted(Path(config_chunk_only.paths.source_dirs[0]).rglob("*"))
    files = [f for f in files if f.is_file()]
    p.run(files)

    out = Path(config_chunk_only.paths.output_dir)
    exports = sorted(out.glob("export_*"))
    assert len(exports) >= 1

    chunks_file = exports[-1] / "chunks.jsonl"
    assert chunks_file.exists()

    chunks = [json.loads(line) for line in chunks_file.read_text().splitlines() if line.strip()]
    assert len(chunks) > 0

    # Verify chunk schema
    for c in chunks:
        assert "chunk_id" in c
        assert "text" in c
        assert "source_path" in c
        assert "chunk_index" in c
        assert "text_length" in c
        assert len(c["text"]) > 0


def test_chunk_only_manifest(config_chunk_only):
    p = Pipeline(config_chunk_only)
    files = sorted(Path(config_chunk_only.paths.source_dirs[0]).rglob("*"))
    files = [f for f in files if f.is_file()]
    p.run(files)

    out = Path(config_chunk_only.paths.output_dir)
    exports = sorted(out.glob("export_*"))
    manifest = json.loads((exports[-1] / "manifest.json").read_text())
    assert manifest["chunk_count"] > 0


def test_chunk_only_no_vectors_file(config_chunk_only):
    p = Pipeline(config_chunk_only)
    files = sorted(Path(config_chunk_only.paths.source_dirs[0]).rglob("*"))
    files = [f for f in files if f.is_file()]
    p.run(files)

    out = Path(config_chunk_only.paths.output_dir)
    exports = sorted(out.glob("export_*"))
    vectors_file = exports[-1] / "vectors.npy"
    if vectors_file.exists():
        v = np.load(str(vectors_file))
        assert v.shape[0] == 0  # Empty array OK


# --- incremental mode ---

def test_incremental_skips_unchanged(config_chunk_only):
    config_chunk_only.pipeline.full_reindex = False
    p = Pipeline(config_chunk_only)
    files = sorted(Path(config_chunk_only.paths.source_dirs[0]).rglob("*"))
    files = [f for f in files if f.is_file()]

    # First run processes all
    stats1 = p.run(files)
    assert stats1.files_parsed == 3

    # Second run should skip all (unchanged)
    p2 = Pipeline(config_chunk_only)
    stats2 = p2.run(files)
    assert stats2.files_parsed == 0


# --- sidecar filtering in pipeline ---

def test_pipeline_skips_sidecar_files(config_chunk_only, source_dir):
    # Add sidecar junk files
    (source_dir / "report_djvu.xml").write_text("<djvu>junk</djvu>")
    (source_dir / "report_hocr.html").write_text("<html>ocr junk</html>")
    (source_dir / "report_meta.xml").write_text("<meta>junk</meta>")

    p = Pipeline(config_chunk_only)
    files = sorted(Path(config_chunk_only.paths.source_dirs[0]).rglob("*"))
    files = [f for f in files if f.is_file()]

    stats = p.run(files)
    assert stats.files_parsed == 3  # Only real files
    assert stats.files_skipped >= 3  # Sidecar files skipped


# --- enrichment fail-loud ---

def test_pipeline_fails_loud_bad_ollama(config_chunk_only):
    config_chunk_only.enrich.enabled = True
    config_chunk_only.enrich.ollama_url = "http://127.0.0.1:59999"
    with pytest.raises(RuntimeError, match="Enrichment is enabled but not available"):
        Pipeline(config_chunk_only)


def test_pipeline_ok_enrichment_disabled(config_chunk_only):
    config_chunk_only.enrich.enabled = False
    p = Pipeline(config_chunk_only)  # Should not raise
    assert p is not None
