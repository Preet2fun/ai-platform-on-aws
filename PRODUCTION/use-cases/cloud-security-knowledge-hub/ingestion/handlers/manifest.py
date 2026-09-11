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

ARTIFACTS_BUCKET = os.getenv("ARTIFACTS_BUCKET", "")


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

    conn = db.connect()
    try:
        db_count = db.count_chunks(conn, event["doc_id"])
    finally:
        conn.close()

    passed, problems = run_checks(event, db_count)
    manifest = {
        "doc_id": event["doc_id"],
        "source": event.get("source"),
        "chunk_count": event.get("chunk_count"),
        "upserted": event.get("upserted"),
        "db_count": db_count,
        "checks_passed": passed,
        "problems": problems,
        "ts": int(time.time()),
    }
    key = f"manifests/{event['doc_id']}.json"
    boto3.client("s3").put_object(
        Bucket=ARTIFACTS_BUCKET, Key=key, Body=json.dumps(manifest, indent=2).encode("utf-8")
    )
    if not passed:
        raise RuntimeError(f"ingestion checks failed for {event['doc_id']}: {problems}")
    return {**event, "manifest_key": key, "checks_passed": passed}
