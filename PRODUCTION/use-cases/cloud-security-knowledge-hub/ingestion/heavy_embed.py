"""Fargate entrypoint: embed + upsert large documents that exceed the Lambda timeout.

Reads a chunks JSONL key from S3 (env CHUNKS_KEY, PROCESSED_BUCKET), embeds every chunk,
and upserts into Aurora. Same logic as the embed_upsert Lambda, but with no time limit and
more memory/CPU for big batches. The state machine routes here when chunk_count is large.
"""

from __future__ import annotations

import json
import os

from common import db
from common.embed import embed_text


def main() -> None:
    import boto3

    bucket = os.environ["PROCESSED_BUCKET"]
    chunks_key = os.environ["CHUNKS_KEY"]
    doc_id = os.environ["DOC_ID"]
    dim = int(os.getenv("EMBEDDING_DIM", "1024"))

    s3 = boto3.client("s3")
    raw = s3.get_object(Bucket=bucket, Key=chunks_key)["Body"].read().decode("utf-8", "ignore")
    chunks = [json.loads(line) for line in raw.splitlines() if line.strip()]

    conn = db.connect()
    try:
        if chunks:
            db.upsert_document(conn, doc_id, chunks[0].get("metadata", {}))
        rows = []
        for ch in chunks:
            rows.append({
                "chunk_id": ch["chunk_id"], "doc_id": ch["doc_id"], "chunk_text": ch["chunk_text"],
                "embedding": embed_text(ch["chunk_text"], dim=dim), "metadata": ch.get("metadata", {}),
            })
        n = db.upsert_chunks(conn, rows)
        conn.commit()
        print(f"heavy-embed upserted {n} chunks for {doc_id}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
