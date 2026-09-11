"""Step 3: Chunk cleaned text + attach metadata.

Input:  { "doc_id", "source", "clean_key", ... }
Output: adds { "chunks_key", "chunk_count" } (JSONL of chunks in the processed bucket)

Each JSONL line: { chunk_id, doc_id, chunk_text, ordinal, metadata }
"""

from __future__ import annotations

import json
import os

from common.chunking import chunk_text
from common.metadata import build_metadata

PROCESSED_BUCKET = os.getenv("PROCESSED_BUCKET", "")


def handler(event, _context=None):
    import boto3

    s3 = boto3.client("s3")
    text = s3.get_object(Bucket=PROCESSED_BUCKET, Key=event["clean_key"])["Body"].read().decode("utf-8", "ignore")

    doc_md = build_metadata(source=event.get("source", ""), text_sample=text[:4000])
    chunks = chunk_text(event["doc_id"], text, metadata=doc_md)

    lines = []
    for c in chunks:
        # enrich each chunk's metadata from its own text (service/topic can vary per chunk)
        cm = build_metadata(source=event.get("source", ""), text_sample=c.text[:2000], overrides=doc_md)
        lines.append(json.dumps({
            "chunk_id": c.chunk_id, "doc_id": c.doc_id, "chunk_text": c.text,
            "ordinal": c.ordinal, "metadata": cm,
        }))

    chunks_key = f"chunks/{event['doc_id']}.jsonl"
    s3.put_object(Bucket=PROCESSED_BUCKET, Key=chunks_key, Body=("\n".join(lines)).encode("utf-8"))
    return {**event, "chunks_key": chunks_key, "chunk_count": len(chunks), "doc_metadata": doc_md}
