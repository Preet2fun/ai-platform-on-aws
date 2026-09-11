"""Tests for structure-aware chunking."""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.chunking import chunk_text, DEFAULT_MAX_CHARS, MIN_CHARS


def test_basic_chunking_produces_chunks():
    text = "\n\n".join(f"Paragraph {i}. " + ("word " * 40) for i in range(10))
    chunks = chunk_text("doc1", text)
    assert len(chunks) >= 2
    assert all(c.doc_id == "doc1" for c in chunks)
    assert all(len(c.text) <= DEFAULT_MAX_CHARS + 250 for c in chunks)  # allow overlap tail


def test_chunk_ids_are_ordered_and_unique():
    text = "\n\n".join(("word " * 60) for _ in range(6))
    chunks = chunk_text("docX", text)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_tiny_fragments_dropped():
    chunks = chunk_text("d", "hi")
    assert chunks == []  # below MIN_CHARS


def test_oversized_paragraph_is_split():
    huge = "x" * (DEFAULT_MAX_CHARS * 3)
    chunks = chunk_text("d", huge)
    assert len(chunks) >= 2
    assert all(len(c.text) <= DEFAULT_MAX_CHARS + 5 for c in chunks)


def test_overlap_present_between_consecutive_chunks():
    text = "\n\n".join((f"s{i} " + "word " * 50) for i in range(8))
    chunks = chunk_text("d", text, max_chars=400, overlap=80)
    assert len(chunks) >= 3
