"""Step 4: Embed chunks and upsert into Aurora (dense pgvector + text; tsv via trigger).

Input:  { "doc_id", "chunks_key", "chunk_count", "doc_metadata", ... }
Output: adds { "upserted" }

For very large docs, the state machine can route to the Fargate heavy-embed task instead;
this Lambda handles typical documents (chunk_count under a threshold) within its timeout.
"""

from __future__ import annotations

import json
import os

from common import db
from common.embed import embed_text

PROCESSED_BUCKET = os.getenv("PROCESSED_BUCKET", "")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))


def handler(event, _context=None):
    import boto3

    s3 = boto3.client("s3")
    raw = s3.get_object(Bucket=PROCESSED_BUCKET, Key=event["chunks_key"])["Body"].read().decode("utf-8", "ignore")
    chunks = [json.loads(line) for line in raw.splitlines() if line.strip()]

    conn = db.connect()
    try:
        db.upsert_document(conn, event["doc_id"], event.get("doc_metadata", {}))
        rows = []
        for ch in chunks:
            vec = embed_text(ch["chunk_text"], dim=EMBEDDING_DIM)
            rows.append({
                "chunk_id": ch["chunk_id"], "doc_id": ch["doc_id"],
                "chunk_text": ch["chunk_text"], "embedding": vec, "metadata": ch.get("metadata", {}),
            })
        upserted = db.upsert_chunks(conn, rows)
        conn.commit()
    finally:
        conn.close()

    return {**event, "upserted": upserted}
