"""Unit tests for ingestion-quality metric derivations (pure, no DB)."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common import ingestion_metrics as im


def test_derive_doc_metrics_healthy():
    # stats row: n, avg, min, max, empty, small, large, null_emb
    row = (10, 900.0, 300, 1500, 0, 0, 0, 0)
    m = im.derive_doc_metrics(row, dup_n=0)
    assert m["chunk_count"] == 10.0
    assert m["avg_chunk_chars"] == 900.0
    assert m["empty_chunk_rate"] == 0.0
    assert m["null_embedding_rate"] == 0.0
    assert m["duplicate_chunk_rate"] == 0.0
    assert im.quality_problems(m) == []


def test_derive_doc_metrics_flags_problems():
    # 10 chunks: 2 empty, 1 null embedding, 4 duplicates, 5 oversized
    row = (10, 2500.0, 0, 6000, 2, 0, 5, 1)
    m = im.derive_doc_metrics(row, dup_n=4)
    assert m["empty_chunk_rate"] == 0.2
    assert m["null_embedding_rate"] == 0.1
    assert m["duplicate_chunk_rate"] == 0.4
    assert m["oversized_chunk_rate"] == 0.5
    probs = im.quality_problems(m)
    assert any("empty" in p for p in probs)
    assert any("null embeddings" in p for p in probs)
    assert any("duplicate" in p for p in probs)
    assert any("oversized" in p for p in probs)


def test_derive_doc_metrics_zero_chunks_no_divzero():
    row = (0, 0, 0, 0, 0, 0, 0, 0)
    m = im.derive_doc_metrics(row, dup_n=0)
    assert m["chunk_count"] == 0.0
    assert m["empty_chunk_rate"] == 0.0  # denom guarded


def test_derive_corpus_metrics():
    # n_docs, n_chunks, avg, empty, small, large, null_emb
    row = (16, 27, 850.0, 0, 1, 0, 0)
    m = im.derive_corpus_metrics(row)
    assert m["corpus_docs"] == 16.0
    assert m["corpus_chunks"] == 27.0
    assert m["corpus_chunks_per_doc"] == round(27 / 16, 2)
    assert m["corpus_null_embedding_rate"] == 0.0


def test_sql_builders_are_parameterized():
    # sanity: builders return strings with the expected %s placeholders
    assert "%s" in im.doc_chunk_stats_sql()
    assert im.doc_chunk_stats_sql().count("%s") == 3   # min, max, doc_id
    assert im.doc_duplicate_sql().count("%s") == 1     # doc_id
    assert "%s" in im.corpus_stats_sql()               # min, max
    assert "GROUP BY" in im.corpus_service_coverage_sql()
