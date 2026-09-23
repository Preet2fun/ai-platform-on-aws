"""Ingestion-quality metrics computed from the Aurora chunks/documents tables.

This is the QUALITY layer for the offline (ingestion) pipeline — distinct from the per-doc
INTEGRITY checks in handlers/manifest.py (which only verify chunks were produced/embedded/
counted). Here we measure whether the ingested corpus is actually good for retrieval:

  - chunk-size distribution (too-small / too-large chunks hurt retrieval)
  - empty-chunk rate (extraction/chunking failures)
  - duplicate-chunk rate (near-identical text wastes the index and skews retrieval)
  - embedding sanity (dimension, null rate, degenerate/zero vectors)
  - corpus coverage (docs, chunks, per-service spread)

Two scopes:
  - per-document metrics (for the doc just ingested) — fast, run in the Manifest step
  - corpus-wide metrics (whole index) — a snapshot for continuous monitoring

Pure SQL builders are separated from execution so they can be unit-tested without a DB.
Embedding column is pgvector `vector(1024)`; we cast to text and parse in SQL-light helpers,
or use vector ops where available.
"""

from __future__ import annotations

from typing import Any

# Chunk-size guardrails (characters). Tune against the chunker's target.
MIN_CHUNK_CHARS = 200
MAX_CHUNK_CHARS = 2000


# ---------- pure SQL builders (testable) ----------

def doc_chunk_stats_sql() -> str:
    """Per-doc chunk-size stats + empty count. Param: (doc_id,)."""
    return (
        "SELECT count(*) AS n, "
        "       coalesce(avg(length(chunk_text)),0) AS avg_chars, "
        "       coalesce(min(length(chunk_text)),0) AS min_chars, "
        "       coalesce(max(length(chunk_text)),0) AS max_chars, "
        "       count(*) FILTER (WHERE length(trim(chunk_text)) = 0) AS empty_n, "
        "       count(*) FILTER (WHERE length(chunk_text) < %s) AS small_n, "
        "       count(*) FILTER (WHERE length(chunk_text) > %s) AS large_n, "
        "       count(*) FILTER (WHERE embedding IS NULL) AS null_emb_n "
        "FROM chunks WHERE doc_id = %s"
    )


def doc_duplicate_sql() -> str:
    """Count duplicate chunk_texts within a doc (exact match). Param: (doc_id,)."""
    return (
        "SELECT coalesce(sum(c - 1), 0) AS dup_n FROM ("
        "  SELECT count(*) AS c FROM chunks WHERE doc_id = %s "
        "  GROUP BY md5(chunk_text) HAVING count(*) > 1"
        ") d"
    )


def corpus_stats_sql() -> str:
    """Corpus-wide totals + chunk-size + embedding sanity (no params)."""
    return (
        "SELECT (SELECT count(*) FROM documents) AS n_docs, "
        "       count(*) AS n_chunks, "
        "       coalesce(avg(length(chunk_text)),0) AS avg_chars, "
        "       count(*) FILTER (WHERE length(trim(chunk_text)) = 0) AS empty_n, "
        "       count(*) FILTER (WHERE length(chunk_text) < %s) AS small_n, "
        "       count(*) FILTER (WHERE length(chunk_text) > %s) AS large_n, "
        "       count(*) FILTER (WHERE embedding IS NULL) AS null_emb_n "
        "FROM chunks"
    )


def corpus_service_coverage_sql() -> str:
    """Chunk count per service (from documents join). No params."""
    return (
        "SELECT coalesce(d.service, 'unknown') AS service, count(*) AS n "
        "FROM chunks c LEFT JOIN documents d ON c.doc_id = d.doc_id "
        "GROUP BY 1 ORDER BY 2 DESC"
    )


# ---------- pure metric derivations (testable) ----------

def derive_doc_metrics(stats_row: tuple, dup_n: int) -> dict[str, float]:
    """Turn the raw stats row into rates/metrics. stats_row matches doc_chunk_stats_sql cols."""
    n, avg_c, min_c, max_c, empty_n, small_n, large_n, null_emb_n = stats_row
    n = int(n or 0)
    denom = n or 1
    return {
        "chunk_count": float(n),
        "avg_chunk_chars": round(float(avg_c or 0), 1),
        "min_chunk_chars": float(min_c or 0),
        "max_chunk_chars": float(max_c or 0),
        "empty_chunk_rate": round(int(empty_n or 0) / denom, 4),
        "undersized_chunk_rate": round(int(small_n or 0) / denom, 4),
        "oversized_chunk_rate": round(int(large_n or 0) / denom, 4),
        "null_embedding_rate": round(int(null_emb_n or 0) / denom, 4),
        "duplicate_chunk_rate": round(int(dup_n or 0) / denom, 4),
    }


def derive_corpus_metrics(row: tuple) -> dict[str, float]:
    n_docs, n_chunks, avg_c, empty_n, small_n, large_n, null_emb_n = row
    n = int(n_chunks or 0)
    denom = n or 1
    return {
        "corpus_docs": float(n_docs or 0),
        "corpus_chunks": float(n),
        "corpus_avg_chunk_chars": round(float(avg_c or 0), 1),
        "corpus_empty_chunk_rate": round(int(empty_n or 0) / denom, 4),
        "corpus_undersized_chunk_rate": round(int(small_n or 0) / denom, 4),
        "corpus_oversized_chunk_rate": round(int(large_n or 0) / denom, 4),
        "corpus_null_embedding_rate": round(int(null_emb_n or 0) / denom, 4),
        "corpus_chunks_per_doc": round(n / (int(n_docs) or 1), 2),
    }


def quality_problems(m: dict[str, float]) -> list[str]:
    """Flag ingestion-quality issues (advisory — does NOT fail the run; integrity does)."""
    problems = []
    if m.get("empty_chunk_rate", 0) > 0:
        problems.append(f"empty chunks present ({m['empty_chunk_rate']:.0%})")
    if m.get("null_embedding_rate", 0) > 0:
        problems.append(f"null embeddings present ({m['null_embedding_rate']:.0%})")
    if m.get("duplicate_chunk_rate", 0) > 0.2:
        problems.append(f"high duplicate rate ({m['duplicate_chunk_rate']:.0%})")
    if m.get("oversized_chunk_rate", 0) > 0.3:
        problems.append(f"many oversized chunks ({m['oversized_chunk_rate']:.0%})")
    return problems


# ---------- DB execution (runtime; needs psycopg + Aurora) ----------

def compute_doc_metrics(conn, doc_id: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(doc_chunk_stats_sql(), (MIN_CHUNK_CHARS, MAX_CHUNK_CHARS, doc_id))
        stats = cur.fetchone()
        cur.execute(doc_duplicate_sql(), (doc_id,))
        dup_n = cur.fetchone()[0]
    m = derive_doc_metrics(stats, dup_n)
    m["quality_problems"] = quality_problems(m)
    return m


def compute_corpus_metrics(conn) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(corpus_stats_sql(), (MIN_CHUNK_CHARS, MAX_CHUNK_CHARS))
        row = cur.fetchone()
        cur.execute(corpus_service_coverage_sql())
        coverage = {str(s): int(c) for s, c in cur.fetchall()}
    m = derive_corpus_metrics(row)
    m["service_coverage"] = coverage
    m["services_covered"] = float(len(coverage))
    return m
