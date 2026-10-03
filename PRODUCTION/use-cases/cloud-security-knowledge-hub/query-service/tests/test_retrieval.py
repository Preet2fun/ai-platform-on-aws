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


# ---- FI-3 metadata filter (query-service side) ----

def test_dense_sql_adds_service_predicate_only_when_service_given():
    assert "metadata->>'service'" not in dense_sql(6)             # baseline unchanged
    assert "metadata->>'service' = %s" in dense_sql(6, service="iam")
    assert "WHERE metadata->>'service' = %s" in dense_sql(6, service="iam")


def test_fulltext_sql_adds_service_predicate_only_when_service_given():
    assert "metadata->>'service'" not in fulltext_sql(6)
    sql = fulltext_sql(6, service="s3")
    assert "AND metadata->>'service' = %s" in sql                 # ANDed onto the tsv WHERE
    assert "tsv @@" in sql


def test_infer_query_service():
    from common.retrieval import infer_query_service
    assert infer_query_service("How do I secure an S3 bucket?") == "s3"
    assert infer_query_service("grant an application on EC2 access via IAM roles") in {"ec2", "iam"}
    assert infer_query_service("protect Route 53 zones") == "route53"     # alias canonicalized
    assert infer_query_service("what is the meaning of life") is None


class _FakeCursor:
    """Records executed SQL; returns a scripted set of rows per call (for fallback testing)."""
    def __init__(self, row_batches):
        self._batches = list(row_batches)
        self.sqls = []
    def execute(self, sql, params=None):
        self.sqls.append(sql)
        self._current = self._batches.pop(0) if self._batches else []
    def fetchall(self):
        return self._current
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _FakeConn:
    def __init__(self, cursor): self._cursor = cursor
    def cursor(self): return self._cursor
    def close(self): pass


def _row(cid, score):
    # matches Hit construction order in dense_search: r[0]cid r[1]doc r[2]text r[3]meta r[4]score
    return (cid, "d", f"t-{cid}", {"service": "iam"}, score)


def test_dense_search_filtered_fallback_to_unfiltered(monkeypatch):
    import common.retrieval as r
    # 1st (filtered) call returns only 1 hit (< top_k=3) -> should refetch unfiltered (2nd call)
    cur = _FakeCursor([[_row("a", 0.9)], [_row("a", 0.9), _row("b", 0.8), _row("c", 0.7)]])
    monkeypatch.setattr(r, "_connect", lambda: _FakeConn(cur))
    hits = r.dense_search([0.0], top_k=3, service="iam")
    assert [h.chunk_id for h in hits] == ["a", "b", "c"]     # unfiltered result used
    assert len(cur.sqls) == 2                                 # filtered then unfiltered
    assert "metadata->>'service'" in cur.sqls[0]              # first was the filtered query
    assert "metadata->>'service'" not in cur.sqls[1]          # fallback was unfiltered


def test_dense_search_filtered_kept_when_enough(monkeypatch):
    import common.retrieval as r
    cur = _FakeCursor([[_row("a", 0.9), _row("b", 0.8), _row("c", 0.7)]])
    monkeypatch.setattr(r, "_connect", lambda: _FakeConn(cur))
    hits = r.dense_search([0.0], top_k=3, service="iam")
    assert [h.chunk_id for h in hits] == ["a", "b", "c"]
    assert len(cur.sqls) == 1                                 # no fallback needed


def test_dense_search_no_service_is_baseline_single_query(monkeypatch):
    import common.retrieval as r
    cur = _FakeCursor([[_row("a", 0.9)]])
    monkeypatch.setattr(r, "_connect", lambda: _FakeConn(cur))
    hits = r.dense_search([0.0], top_k=3)                     # Phase-1 path (no service)
    assert [h.chunk_id for h in hits] == ["a"]
    assert len(cur.sqls) == 1
    assert "metadata->>'service'" not in cur.sqls[0]          # baseline SQL unchanged


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
    monkeypatch.setattr(r, "dense_search", lambda vec, k, **kw: [_hit("a", 0.9), _hit("b", 0.8)])
    monkeypatch.setattr(r, "fulltext_search", lambda q, k, **kw: [_hit("x", 5.0), _hit("a", 4.0)])
    hits = r.hybrid_search([0.0], "some query", top_k=3)
    ids = {h.chunk_id for h in hits}
    assert "x" in ids and "a" in ids          # the full-text-only chunk is now retrievable
    assert len(hits) <= 3


def test_hybrid_search_falls_back_to_dense_when_fulltext_empty(monkeypatch):
    import common.retrieval as r
    dense = [_hit("a", 0.9), _hit("b", 0.8)]
    monkeypatch.setattr(r, "dense_search", lambda vec, k, **kw: dense)
    monkeypatch.setattr(r, "fulltext_search", lambda q, k, **kw: [])
    hits = r.hybrid_search([0.0], "q", top_k=2)
    assert [h.chunk_id for h in hits] == ["a", "b"]   # unchanged from dense


def test_hybrid_search_survives_fulltext_error(monkeypatch):
    import common.retrieval as r
    dense = [_hit("a", 0.9)]
    monkeypatch.setattr(r, "dense_search", lambda vec, k, **kw: dense)
    def boom(q, k, **kw):
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
