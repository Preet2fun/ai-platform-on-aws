"""Tests for retrieval SQL builders + RRF (no database needed)."""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.retrieval import dense_sql, fulltext_sql, reciprocal_rank_fusion, Hit, _vec_literal


def test_dense_sql_uses_pgvector_cosine():
    sql = dense_sql(6)
    assert "<=>" in sql            # pgvector cosine distance operator
    assert "::vector" in sql
    assert "LIMIT" in sql


def test_fulltext_sql_uses_tsquery():
    sql = fulltext_sql(6)
    assert "plainto_tsquery" in sql
    assert "tsv @@" in sql
    assert "ts_rank" in sql


def test_vec_literal():
    assert _vec_literal([0.1, 0.2]) == "[0.100000,0.200000]"


def _hit(cid, score):
    return Hit(cid, "doc", f"text-{cid}", score, {})


def test_rrf_merges_and_ranks():
    dense = [_hit("a", 0.9), _hit("b", 0.8), _hit("c", 0.7)]
    sparse = [_hit("b", 5.0), _hit("a", 4.0), _hit("d", 3.0)]
    merged = reciprocal_rank_fusion([dense, sparse], k=60)
    ids = [h.chunk_id for h in merged]
    # a and b appear in both lists near the top -> should outrank c/d
    assert ids[0] in {"a", "b"}
    assert set(ids) == {"a", "b", "c", "d"}
    # scores are descending
    assert all(merged[i].score >= merged[i + 1].score for i in range(len(merged) - 1))
