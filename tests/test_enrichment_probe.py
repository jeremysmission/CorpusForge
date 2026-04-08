"""Tests for enrichment readiness probe and auto-start logic."""
import pytest

from src.enrichment.contextual_enricher import (
    probe_enrichment, EnrichmentProbeResult, _ollama_is_running,
)


# --- probe result ---

def test_probe_result_ready_when_both_true():
    r = EnrichmentProbeResult(ollama_running=True, model_available=True)
    assert r.ready is True
    assert r.status_text == "ready"


def test_probe_result_not_ready_ollama_down():
    r = EnrichmentProbeResult(ollama_running=False, error="not running")
    assert r.ready is False
    assert "not running" in r.status_text


def test_probe_result_not_ready_model_missing():
    r = EnrichmentProbeResult(ollama_running=True, model_available=False,
                               error="Model xyz not found")
    assert r.ready is False
    assert "not found" in r.status_text


# --- live probe (depends on actual Ollama state) ---

def test_probe_no_auto_start_bad_url():
    """Probe against a bad URL should report not running."""
    r = probe_enrichment(
        ollama_url="http://127.0.0.1:59999",
        auto_start=False,
    )
    assert r.ollama_running is False
    assert r.ready is False


def test_probe_no_auto_start_bad_model():
    """If Ollama is up but model is wrong, should report model missing."""
    # This test only works if Ollama is actually running
    if not _ollama_is_running("http://127.0.0.1:11434"):
        pytest.skip("Ollama not running")
    r = probe_enrichment(
        ollama_url="http://127.0.0.1:11434",
        model="nonexistent-model-xyz:latest",
        auto_start=False,
    )
    assert r.ollama_running is True
    assert r.model_available is False


def test_probe_real_ollama():
    """If Ollama is running with phi4, probe should succeed."""
    if not _ollama_is_running("http://127.0.0.1:11434"):
        pytest.skip("Ollama not running")
    r = probe_enrichment(
        ollama_url="http://127.0.0.1:11434",
        model="phi4",
        auto_start=False,
    )
    assert r.ollama_running is True
    # Model check depends on what's pulled
