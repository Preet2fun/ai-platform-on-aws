"""Step 5: Write an ingestion manifest + run ingestion-quality checks.

Input:  { "doc_id", "source", "chunk_count", "upserted", ... }
Output: adds { "manifest_key", "checks_passed" }

Checks (fail the run if any fail): chunks were produced, all embedded rows upserted, and the
DB row count for the doc matches. The manifest is the audit record for the ingestion (see
AI-SDLC-AND-EVALS.md: "ingestion manifest must pass before the index is promoted").
"""

from __future__ import annotations

import json
import os
import time

from common import db
from common import ingestion_metrics as im

ARTIFACTS_BUCKET = os.getenv("ARTIFACTS_BUCKET", "")
METRICS_NAMESPACE = os.getenv("INGEST_METRICS_NAMESPACE", "CSHub/Ingestion")


def _emit_metrics(doc_metrics: dict, corpus_metrics: dict) -> None:
    """Emit ingestion-quality metrics to CloudWatch (continuous monitoring). Non-fatal."""
    try:
        import boto3
        cw = boto3.client("cloudwatch")
        data = []
        # per-doc quality rates
        for k in ("chunk_count", "avg_chunk_chars", "empty_chunk_rate",
                  "undersized_chunk_rate", "oversized_chunk_rate",
                  "null_embedding_rate", "duplicate_chunk_rate"):
            if k in doc_metrics:
                data.append({"MetricName": k, "Value": float(doc_metrics[k]), "Unit": "None"})
        # corpus-wide snapshot
        for k in ("corpus_docs", "corpus_chunks", "corpus_avg_chunk_chars",
                  "corpus_empty_chunk_rate", "corpus_null_embedding_rate",
                  "corpus_chunks_per_doc", "services_covered"):
            if k in corpus_metrics:
                data.append({"MetricName": k, "Value": float(corpus_metrics[k]), "Unit": "None"})
        # CloudWatch accepts max 1000/call; we have <20
        if data:
            cw.put_metric_data(Namespace=METRICS_NAMESPACE, MetricData=data)
    except Exception as e:  # noqa: BLE001 - monitoring must never fail ingestion
        print(f"metric emit failed (non-fatal): {e}")


def run_checks(event, db_count: int) -> tuple[bool, list[str]]:
    problems = []
    if event.get("chunk_count", 0) <= 0:
        problems.append("no chunks produced")
    if event.get("upserted", 0) != event.get("chunk_count", 0):
        problems.append(f"upserted {event.get('upserted')} != chunk_count {event.get('chunk_count')}")
    if db_count != event.get("chunk_count", 0):
        problems.append(f"db count {db_count} != chunk_count {event.get('chunk_count')}")
    return (len(problems) == 0), problems


def handler(event, _context=None):
    import boto3

    # --- integrity check (gates the run) + quality metrics (advisory) ---
    conn = db.connect()
    try:
        db_count = db.count_chunks(conn, event["doc_id"])
        # QUALITY layer: per-doc + corpus-wide ingestion metrics (non-fatal)
        try:
            doc_metrics = im.compute_doc_metrics(conn, event["doc_id"])
            corpus_metrics = im.compute_corpus_metrics(conn)
        except Exception as e:  # noqa: BLE001 - quality metrics must never fail ingestion
            print(f"ingestion quality metrics failed (non-fatal): {e}")
            doc_metrics, corpus_metrics = {}, {}
    finally:
        conn.close()

    passed, problems = run_checks(event, db_count)

    manifest = {
        "doc_id": event["doc_id"],
        "source": event.get("source"),
        "chunk_count": event.get("chunk_count"),
        "upserted": event.get("upserted"),
        "db_count": db_count,
        "checks_passed": passed,          # INTEGRITY gate (fails the run)
        "problems": problems,
        "quality": doc_metrics,           # QUALITY metrics (advisory)
        "quality_problems": doc_metrics.get("quality_problems", []),
        "corpus": corpus_metrics,         # corpus-wide snapshot
        "ts": int(time.time()),
    }
    key = f"manifests/{event['doc_id']}.json"
    boto3.client("s3").put_object(
        Bucket=ARTIFACTS_BUCKET, Key=key, Body=json.dumps(manifest, indent=2).encode("utf-8")
    )

    # continuous monitoring: push quality metrics to CloudWatch (non-fatal)
    _emit_metrics(doc_metrics, corpus_metrics)

    if not passed:
        raise RuntimeError(f"ingestion checks failed for {event['doc_id']}: {problems}")
    return {**event, "manifest_key": key, "checks_passed": passed,
            "quality_problems": doc_metrics.get("quality_problems", [])}
