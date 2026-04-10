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


def test_pipeline_emits_live_stats_updates(config_chunk_only):
    p = Pipeline(config_chunk_only)
    files = sorted(Path(config_chunk_only.paths.source_dirs[0]).rglob("*"))
    files = [f for f in files if f.is_file()]
    snapshots = []

    stats = p.run(files, on_stats_update=lambda snapshot: snapshots.append(dict(snapshot)))

    assert len(snapshots) >= 2
    assert snapshots[0]["files_found"] == len(files)
    assert snapshots[-1]["files_parsed"] == stats.files_parsed
    assert snapshots[-1]["chunks_created"] == stats.chunks_created
    assert any(snapshot["chunks_created"] > 0 for snapshot in snapshots[:-1])
    assert snapshots[-1]["chunks_per_second"] >= 0.0


def test_pipeline_stop_request_packages_partial_work(config_chunk_only):
    config_chunk_only.pipeline.workers = 1
    p = Pipeline(config_chunk_only)
    files = sorted(Path(config_chunk_only.paths.source_dirs[0]).rglob("*"))
    files = [f for f in files if f.is_file()]
    stop = {"value": False}

    def on_stats_update(snapshot):
        if snapshot.get("files_parsed", 0) >= 1:
            stop["value"] = True

    stats = p.run(
        files,
        on_stats_update=on_stats_update,
        should_stop=lambda: stop["value"],
    )

    out = Path(config_chunk_only.paths.output_dir)
    exports = sorted(out.glob("export_*"))

    assert stats.stop_requested is True
    assert 0 < stats.files_parsed < len(files)
    assert stats.chunks_created > 0
    assert len(exports) >= 1


def test_pipeline_parse_stage_calls_out_cpu_io_work(config_chunk_only):
    config_chunk_only.pipeline.workers = 1
    p = Pipeline(config_chunk_only)
    files = sorted(Path(config_chunk_only.paths.source_dirs[0]).rglob("*"))
    files = [f for f in files if f.is_file()]
    stage_events = []

    p.run(files, on_stage_progress=lambda stage, current, total, detail: stage_events.append(
        (stage, current, total, detail)
    ))

    parse_details = [detail for stage, _current, _total, detail in stage_events if stage == "parse"]
    assert any("CPU/IO parse" in detail for detail in parse_details)


def test_pipeline_emits_export_stage(config_chunk_only):
    p = Pipeline(config_chunk_only)
    files = sorted(Path(config_chunk_only.paths.source_dirs[0]).rglob("*"))
    files = [f for f in files if f.is_file()]
    stage_events = []

    p.run(files, on_stage_progress=lambda stage, current, total, detail: stage_events.append(
        (stage, current, total, detail)
    ))

    export_events = [e for e in stage_events if e[0] == "export"]
    # Operator should see at least a "starting export" and a "done export" event
    assert len(export_events) >= 2, f"Expected >=2 export events, got {export_events}"
    # Final export event should mark completion
    assert any("Done" in detail for _stage, _c, _t, detail in export_events)


def test_pipeline_embed_stop_truncates_chunks_to_match_vectors(config_chunk_only, monkeypatch):
    """Cooperative stop fired mid-embed must keep chunks/vectors aligned in the export."""
    config_chunk_only.embed.enabled = True
    p = Pipeline(config_chunk_only)
    files = sorted(Path(config_chunk_only.paths.source_dirs[0]).rglob("*"))
    files = [f for f in files if f.is_file()]

    # Force the sub-batch path with a tiny sub-batch size, and stub the embedder
    # so we don't load a real model. The stub returns deterministic float16 vectors.
    class _StubEmbedder:
        dim = 8
        def embed_batch(self, texts):
            return np.zeros((len(texts), self.dim), dtype=np.float16)

    monkeypatch.setattr(p, "_get_embedder", lambda: _StubEmbedder())

    # Drop the sub-batch threshold so the loop runs even with small inputs.
    import src.pipeline as pipeline_module
    original_embed = pipeline_module.Pipeline._embed_chunks

    def _embed_with_small_batches(self, chunks, stats):
        # Monkey-replace the constant inline by re-implementing with sub_batch_size=1
        embedder = self._get_embedder()
        total = len(chunks)
        dim = embedder.dim
        sub_batch_size = 1
        self._emit_stage("embed", 0, total, "Starting embedding...")

        import tempfile, time as _t
        from pathlib import Path as _P
        mmap_path = _P(tempfile.mktemp(suffix=".dat", prefix="embed_test_"))
        vectors_mmap = np.memmap(str(mmap_path), dtype=np.float16, mode="w+", shape=(total, dim))
        embed_start = _t.time()
        offset = 0
        for batch_start in range(0, total, sub_batch_size):
            if self._check_stop(stats, f"stop mid-embed at {offset}/{total}"):
                break
            batch_end = min(batch_start + sub_batch_size, total)
            batch_texts = [c.get("enriched_text") or c["text"] for c in chunks[batch_start:batch_end]]
            batch_vectors = embedder.embed_batch(batch_texts)
            batch_count = len(batch_vectors)
            vectors_mmap[offset:offset + batch_count] = batch_vectors.astype(np.float16)
            offset += batch_count
            stats.vectors_created = offset
            self._emit_stats(stats)
        vectors = np.array(vectors_mmap[:offset], dtype=np.float16)
        del vectors_mmap
        try:
            mmap_path.unlink()
        except OSError:
            pass
        stats.vectors_created = len(vectors)
        return vectors

    monkeypatch.setattr(pipeline_module.Pipeline, "_embed_chunks", _embed_with_small_batches)

    # Stop after the first embed sub-batch posts vectors_created.
    stop = {"value": False}
    def on_stats_update(snapshot):
        if snapshot.get("vectors_created", 0) >= 1:
            stop["value"] = True

    stats = p.run(files, on_stats_update=on_stats_update, should_stop=lambda: stop["value"])

    out = Path(config_chunk_only.paths.output_dir)
    exports = sorted(out.glob("export_*"))
    assert len(exports) >= 1, "expected an export to be packaged on stop"

    chunks_file = exports[-1] / "chunks.jsonl"
    vectors_file = exports[-1] / "vectors.npy"
    assert chunks_file.exists()
    assert vectors_file.exists()

    chunk_count = sum(1 for line in chunks_file.read_text().splitlines() if line.strip())
    vec = np.load(str(vectors_file))
    assert stats.stop_requested is True
    assert chunk_count == vec.shape[0], (
        f"chunks/vectors must align after stop: chunks={chunk_count}, vectors={vec.shape[0]}"
    )
    assert vec.shape[0] >= 1
    assert vec.shape[0] < stats.chunks_created or stats.chunks_created == vec.shape[0]


def test_pipeline_skips_extraction_when_stopped(config_chunk_only, monkeypatch):
    """Stop during embed should also skip GLiNER extraction so we don't burn time on a doomed run."""
    config_chunk_only.embed.enabled = True
    config_chunk_only.extract.enabled = True

    # Stub embedder + extractor so we don't load real models.
    class _StubEmbedder:
        dim = 8
        def embed_batch(self, texts):
            return np.zeros((len(texts), self.dim), dtype=np.float16)

    extract_called = {"value": False}
    class _StubExtractor:
        def extract_entities(self, chunks):
            extract_called["value"] = True
            return []

    p = Pipeline(config_chunk_only)
    monkeypatch.setattr(p, "_get_embedder", lambda: _StubEmbedder())
    monkeypatch.setattr(p, "_get_extractor", lambda: _StubExtractor())

    files = sorted(Path(config_chunk_only.paths.source_dirs[0]).rglob("*"))
    files = [f for f in files if f.is_file()]

    # Mark stop_requested before extraction by stopping immediately after parse.
    stop = {"value": False}
    def on_stats_update(snapshot):
        if snapshot.get("chunks_created", 0) >= 1:
            stop["value"] = True

    stats = p.run(files, on_stats_update=on_stats_update, should_stop=lambda: stop["value"])

    assert stats.stop_requested is True
    assert extract_called["value"] is False, (
        "Entity extraction must be skipped after a cooperative stop"
    )


def test_pipeline_stop_before_embed_does_not_ship_mismatched_export(config_chunk_only, monkeypatch):
    """QA H1: when embed is enabled but stop fires before embed runs, the
    pipeline must NOT write a chunks+vectors export with mismatched lengths.
    Ship nothing instead and report export_dir="" so the GUI tells the truth."""
    config_chunk_only.embed.enabled = True
    config_chunk_only.extract.enabled = False

    class _StubEmbedder:
        dim = 8
        def embed_batch(self, texts):
            raise AssertionError("embed should not be called when stop fires before embed")

    p = Pipeline(config_chunk_only)
    monkeypatch.setattr(p, "_get_embedder", lambda: _StubEmbedder())

    files = sorted(Path(config_chunk_only.paths.source_dirs[0]).rglob("*"))
    files = [f for f in files if f.is_file()]

    # Trip stop once parse produces the first chunk — before embed runs.
    stop = {"value": False}
    def on_stats_update(snapshot):
        if snapshot.get("chunks_created", 0) >= 1:
            stop["value"] = True

    stats = p.run(files, on_stats_update=on_stats_update, should_stop=lambda: stop["value"])

    out = Path(config_chunk_only.paths.output_dir)
    exports = sorted(out.glob("export_*"))

    assert stats.stop_requested is True
    assert stats.export_dir == "", (
        f"No export should have been written when embed was stopped before running; "
        f"got export_dir={stats.export_dir!r}"
    )
    assert len(exports) == 0, (
        f"No export_* directory should exist on disk; found {exports}"
    )
    # chunks_created must be zeroed so the GUI does not claim chunks were shipped
    assert stats.chunks_created == 0
    # V2 import contract: any export we DO write must have aligned chunks+vectors.
    # Here we wrote none, so there is nothing to mis-align.


def test_pipeline_stop_before_dedup_reports_no_export(config_chunk_only):
    """QA H2: stop-before-dedup must return with export_dir='' so the GUI does
    not falsely log 'completed work was packaged'."""
    p = Pipeline(config_chunk_only)
    files = sorted(Path(config_chunk_only.paths.source_dirs[0]).rglob("*"))
    files = [f for f in files if f.is_file()]

    stats = p.run(files, should_stop=lambda: True)

    out = Path(config_chunk_only.paths.output_dir)
    exports = sorted(out.glob("export_*"))

    assert stats.stop_requested is True
    assert stats.export_dir == "", f"expected empty export_dir, got {stats.export_dir!r}"
    assert len(exports) == 0, f"no export should exist on disk; found {exports}"
    assert stats.chunks_created == 0
    assert stats.files_parsed == 0


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


def test_pipeline_env_overrides_parser_modes(config_chunk_only, monkeypatch):
    monkeypatch.setenv("HYBRIDRAG_DOCLING_MODE", "prefer")
    monkeypatch.setenv("HYBRIDRAG_OCR_MODE", "skip")
    config_chunk_only.parse.docling_mode = "off"
    config_chunk_only.parse.ocr_mode = "auto"

    Pipeline(config_chunk_only)

    assert config_chunk_only.parse.docling_mode == "prefer"
    assert config_chunk_only.parse.ocr_mode == "skip"
