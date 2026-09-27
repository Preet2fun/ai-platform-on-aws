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


def test_hybrid_search_fuses_dense_and_sparse(monkeypatch):
    import common.retrieval as r
    # dense misses the answering chunk "x"; sparse (full-text) surfaces it -> fusion recovers it
    monkeypatch.setattr(r, "dense_search", lambda vec, k: [_hit("a", 0.9), _hit("b", 0.8)])
    monkeypatch.setattr(r, "fulltext_search", lambda q, k: [_hit("x", 5.0), _hit("a", 4.0)])
    hits = r.hybrid_search([0.0], "some query", top_k=3)
    ids = {h.chunk_id for h in hits}
    assert "x" in ids and "a" in ids          # the full-text-only chunk is now retrievable
    assert len(hits) <= 3


def test_hybrid_search_falls_back_to_dense_when_fulltext_empty(monkeypatch):
    import common.retrieval as r
    dense = [_hit("a", 0.9), _hit("b", 0.8)]
    monkeypatch.setattr(r, "dense_search", lambda vec, k: dense)
    monkeypatch.setattr(r, "fulltext_search", lambda q, k: [])
    hits = r.hybrid_search([0.0], "q", top_k=2)
    assert [h.chunk_id for h in hits] == ["a", "b"]   # unchanged from dense


def test_hybrid_search_survives_fulltext_error(monkeypatch):
    import common.retrieval as r
    dense = [_hit("a", 0.9)]
    monkeypatch.setattr(r, "dense_search", lambda vec, k: dense)
    def boom(q, k):
        raise RuntimeError("fulltext down")
    monkeypatch.setattr(r, "fulltext_search", boom)
    hits = r.hybrid_search([0.0], "q", top_k=3)     # non-fatal: falls back to dense
    assert [h.chunk_id for h in hits] == ["a"]


# ---- rerank (Phase-2 Stage 2) ----

class _FakeRerankClient:
    """Mimics bedrock-agent-runtime.rerank: returns a fixed reranked index order."""
    def __init__(self, order):
        self.order = order
    def rerank(self, **kwargs):
        n = kwargs["rerankingConfiguration"]["bedrockRerankingConfiguration"]["numberOfResults"]
        return {"results": [{"index": i, "relevanceScore": 1.0 - j * 0.1}
                            for j, i in enumerate(self.order[:n])]}


def test_rerank_reorders_and_truncates(monkeypatch):
    from common import bedrock
    # candidate pool where the answering chunk "d" is LAST from retrieval (buried/crowded)
    cands = [_hit("a", 0.9), _hit("b", 0.8), _hit("c", 0.7), _hit("d", 0.6)]
    # reranker judges "d" most relevant -> should be lifted to the front
    fake = _FakeRerankClient(order=[3, 0, 1, 2])
    out = bedrock.rerank("q", cands, top_k=2, client=fake)
    assert [h.chunk_id for h in out] == ["d", "a"]   # reranked + truncated to top_k


def test_rerank_nonfatal_returns_input_order_on_error(monkeypatch):
    from common import bedrock
    cands = [_hit("a", 0.9), _hit("b", 0.8), _hit("c", 0.7)]
    class _Boom:
        def rerank(self, **kw):
            raise RuntimeError("no model access")
    out = bedrock.rerank("q", cands, top_k=2, client=_Boom())
    assert [h.chunk_id for h in out] == ["a", "b"]   # falls back to retrieval order, truncated


def test_rerank_empty_hits():
    from common import bedrock
    assert bedrock.rerank("q", [], top_k=5, client=object()) == []


def test_rerank_overwrites_score_with_relevance(monkeypatch):
    # rerank must set each returned Hit.score to the reranker relevanceScore (CRAG grade source)
    from common import bedrock
    cands = [_hit("a", 0.11), _hit("b", 0.22)]
    class _C:
        def rerank(self, **kw):
            return {"results": [{"index": 1, "relevanceScore": 0.83},
                                {"index": 0, "relevanceScore": 0.12}]}
    out = bedrock.rerank("q", cands, top_k=2, client=_C())
    assert [h.chunk_id for h in out] == ["b", "a"]
    assert out[0].score == 0.83 and out[1].score == 0.12   # dense scores replaced


# ---- query expansion (Phase-2 Stage 3) ----

def test_expand_query_parses_lines(monkeypatch):
    from common import bedrock
    monkeypatch.setattr(bedrock, "generate",
                        lambda prompt, **kw: "1. how to attach an IAM role to EC2\n"
                                             "2. EC2 instance profile credentials\n"
                                             "grant AWS access to an app on EC2")
    out = bedrock.expand_query("How should I grant an app on EC2 access to AWS services?", n=3)
    assert len(out) == 3
    assert "how to attach an IAM role to EC2" in out          # numbering stripped
    assert all(not v[0].isdigit() for v in out)               # no leading list numbers


def test_expand_query_dedupes_and_caps(monkeypatch):
    from common import bedrock
    monkeypatch.setattr(bedrock, "generate",
                        lambda prompt, **kw: "same query\nSAME QUERY\nother query\nthird query")
    out = bedrock.expand_query("q", n=2)
    assert out == ["same query", "other query"]              # deduped (case-insensitive), capped at n


def test_expand_query_nonfatal_on_error(monkeypatch):
    from common import bedrock
    def boom(prompt, **kw):
        raise RuntimeError("model down")
    monkeypatch.setattr(bedrock, "generate", boom)
    assert bedrock.expand_query("q", n=3) == []               # falls back to no variants
