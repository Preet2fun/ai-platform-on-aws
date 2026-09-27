"""Retrieval from Aurora.

Phase 1 baseline: dense-only ANN over pgvector (cosine).
Phase 2 (flagged): hybrid = dense + full-text (tsvector) merged with Reciprocal Rank Fusion.

SQL is built by pure functions so it can be unit-tested without a database.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

DB_ENDPOINT = os.getenv("DB_ENDPOINT", "")
DB_NAME = os.getenv("DB_NAME", "cshub")
DB_SECRET_ARN = os.getenv("DB_SECRET_ARN", "")


@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    text: str
    score: float
    metadata: dict[str, Any]


# ---- SQL builders (pure, testable) ----

def dense_sql(top_k: int) -> str:
    """Dense ANN query (cosine distance -> similarity). Params: (vec_literal, top_k)."""
    return (
        "SELECT chunk_id, doc_id, chunk_text, metadata, "
        "1 - (embedding <=> %s::vector) AS score "
        "FROM chunks ORDER BY embedding <=> %s::vector LIMIT %s"
    )


def fulltext_sql(top_k: int) -> str:
    """Sparse full-text query (Phase 2). Params: (query_text, query_text, top_k)."""
    return (
        "SELECT chunk_id, doc_id, chunk_text, metadata, "
        "ts_rank(tsv, plainto_tsquery('english', %s)) AS score "
        "FROM chunks WHERE tsv @@ plainto_tsquery('english', %s) "
        "ORDER BY score DESC LIMIT %s"
    )


def reciprocal_rank_fusion(ranked_lists: list[list[Hit]], k: int = 60) -> list[Hit]:
    """Merge multiple ranked lists (Phase 2). score(d) = Σ 1/(k + rank_i(d))."""
    agg: dict[str, float] = {}
    by_id: dict[str, Hit] = {}
    for lst in ranked_lists:
        for rank, hit in enumerate(lst):
            agg[hit.chunk_id] = agg.get(hit.chunk_id, 0.0) + 1.0 / (k + rank + 1)
            by_id[hit.chunk_id] = hit
    ordered = sorted(agg.items(), key=lambda x: x[1], reverse=True)
    out = []
    for cid, s in ordered:
        h = by_id[cid]
        out.append(Hit(h.chunk_id, h.doc_id, h.text, s, h.metadata))
    return out


# ---- DB access (runtime) ----

def _credentials() -> dict[str, str]:
    import boto3

    sm = boto3.client("secretsmanager")
    sec = json.loads(sm.get_secret_value(SecretId=DB_SECRET_ARN)["SecretString"])
    return {"user": sec["username"], "password": sec["password"]}


def _connect():
    import psycopg

    c = _credentials()
    return psycopg.connect(host=DB_ENDPOINT, dbname=DB_NAME, user=c["user"],
                           password=c["password"], sslmode="require", connect_timeout=10)


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def dense_search(query_vec: list[float], top_k: int) -> list[Hit]:
    v = _vec_literal(query_vec)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(dense_sql(top_k), (v, v, top_k))
            return [Hit(r[0], r[1], r[2], float(r[4]), r[3] or {}) for r in cur.fetchall()]
    finally:
        conn.close()


def hybrid_search(query_vec: list[float], query_text: str, top_k: int,
                  *, candidate_k: int | None = None) -> list[Hit]:
    """Phase-2 hybrid retrieval: dense (pgvector) + sparse (full-text) merged with RRF.

    Fetches a wider candidate pool from EACH retriever (`candidate_k`, default 2*top_k) so RRF
    has enough to fuse, then returns the top_k fused hits. Full-text is non-fatal: if it errors
    or returns nothing (e.g. a query with no lexical overlap), we fall back to the dense list so
    hybrid never does worse than dense on availability.
    """
    ck = candidate_k or max(top_k, top_k * 2)
    dense = dense_search(query_vec, ck)
    try:
        sparse = fulltext_search(query_text, ck)
    except Exception:  # noqa: BLE001 - full-text must never break retrieval
        sparse = []
    if not sparse:
        return dense[:top_k]
    fused = reciprocal_rank_fusion([dense, sparse])
    return fused[:top_k]


def fulltext_search(query_text: str, top_k: int) -> list[Hit]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(fulltext_sql(top_k), (query_text, query_text, top_k))
            return [Hit(r[0], r[1], r[2], float(r[4]), r[3] or {}) for r in cur.fetchall()]
    finally:
        conn.close()
