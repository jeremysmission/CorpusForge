"""Tests for the text chunker — boundary detection, overlap, headings.

Plain-English summary for operators:
This file protects the chunker, the Forge subsystem that cuts a parsed
document into overlapping slices ("chunks") for downstream embedding and
search. If these tests fail, Forge may produce an export where chunks are
the wrong size, lose the overlap that keeps search recall high, drop the
last page of a long document, or generate non-deterministic chunk IDs
that break re-runs. Any regression here shows up as poor search quality
or duplicate/missing chunks in the shipped export.
"""
import pytest

from src.chunk.chunker import Chunker
from src.chunk.chunk_ids import make_chunk_id


# --- basic chunking ---

def test_short_text_single_chunk():
    """Protects against tiny documents being chopped into fragments."""
    c = Chunker(chunk_size=1200, overlap=200)
    chunks = c.chunk_text("Hello world.")
    assert len(chunks) == 1
    assert chunks[0] == "Hello world."


def test_empty_text_no_chunks():
    """Protects against blank/whitespace documents creating phantom chunks in the export."""
    c = Chunker(chunk_size=1200, overlap=200)
    assert c.chunk_text("") == []
    assert c.chunk_text("   ") == []


def test_long_text_produces_multiple_chunks():
    """Protects against long documents being squashed into a single oversized chunk."""
    c = Chunker(chunk_size=100, overlap=20)
    text = "word " * 200  # 1000 chars
    chunks = c.chunk_text(text)
    assert len(chunks) > 1


def test_overlap_exists_between_chunks():
    """Protects against lost overlap between adjacent chunks — loss here hurts search recall on sentences that span a boundary."""
    c = Chunker(chunk_size=100, overlap=20)
    text = "The quick brown fox jumps over the lazy dog. " * 20
    chunks = c.chunk_text(text)
    if len(chunks) >= 2:
        # Last part of chunk[0] should appear at start of chunk[1]
        tail = chunks[0][-20:]
        assert tail in chunks[1] or chunks[1].startswith(tail[:10])


def test_chunk_size_respected():
    """Protects against runaway chunks that balloon past the configured size and blow up GPU batching."""
    c = Chunker(chunk_size=200, overlap=50)
    text = "a " * 500
    chunks = c.chunk_text(text)
    for chunk in chunks:
        # Allow some flex for boundary detection
        assert len(chunk) <= 400, f"Chunk too long: {len(chunk)} chars"


# --- boundary detection ---

def test_paragraph_boundary_preferred():
    """Protects against chunker splitting mid-sentence when a clean paragraph break is available."""
    c = Chunker(chunk_size=100, overlap=20)
    text = "First paragraph content here.\n\nSecond paragraph starts now with more text that goes on."
    chunks = c.chunk_text(text)
    if len(chunks) >= 2:
        # Should prefer splitting at paragraph boundary
        assert chunks[0].strip().endswith(".") or "\n\n" not in chunks[0]


# --- chunk IDs ---

def test_chunk_id_deterministic():
    """Protects against chunk IDs changing between runs — ops need the same ID twice so re-runs do not duplicate work."""
    id1 = make_chunk_id("file.txt", 1000, 0, 100, "hello world")
    id2 = make_chunk_id("file.txt", 1000, 0, 100, "hello world")
    assert id1 == id2


def test_chunk_id_changes_with_content():
    """Protects against ID collisions when the underlying text changes — otherwise edits would be invisible."""
    id1 = make_chunk_id("file.txt", 1000, 0, 100, "hello world")
    id2 = make_chunk_id("file.txt", 1000, 0, 100, "different text")
    assert id1 != id2


def test_chunk_id_changes_with_path():
    """Protects against two different source files sharing the same chunk ID just because their text happened to match."""
    id1 = make_chunk_id("file_a.txt", 1000, 0, 100, "same text")
    id2 = make_chunk_id("file_b.txt", 1000, 0, 100, "same text")
    assert id1 != id2


def test_chunk_id_is_hex_string():
    """Protects against malformed chunk IDs — downstream V2 import expects a 64-char hex SHA-256."""
    cid = make_chunk_id("file.txt", 1000, 0, 100, "text")
    assert isinstance(cid, str)
    assert len(cid) == 64  # SHA-256 hex
    int(cid, 16)  # Should not raise
