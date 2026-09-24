"""Bedrock embedding client (Amazon Titan Text Embeddings v2)."""

from __future__ import annotations

import json
import os
from typing import Any

EMBEDDING_MODEL_ID = os.getenv("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))


def _client():
    import boto3  # imported lazily so unit tests can run without boto3/creds

    return boto3.client("bedrock-runtime")


def embed_text(text: str, *, client: Any | None = None, dim: int = EMBEDDING_DIM) -> list[float]:
    """Return the embedding vector for a single text.

    Titan v2 request shape: {"inputText": "...", "dimensions": 1024, "normalize": true}

    Large documents produce many chunks, and embedding them in a tight loop can burst past
    Bedrock's on-demand throughput → ThrottlingException. We retry with exponential backoff so
    ingestion of big PDFs succeeds instead of failing the whole run.
    """
    import time

    c = client or _client()
    body = json.dumps({"inputText": text, "dimensions": dim, "normalize": True})
    last_err = None
    for attempt in range(6):
        try:
            resp = c.invoke_model(modelId=EMBEDDING_MODEL_ID, body=body)
            payload = json.loads(resp["body"].read())
            vec = payload["embedding"]
            if len(vec) != dim:
                raise ValueError(f"embedding dim mismatch: got {len(vec)}, expected {dim}")
            return vec
        except Exception as e:  # noqa: BLE001
            name = type(e).__name__
            if ("Throttl" in name or "TooManyRequests" in str(e)) and attempt < 5:
                time.sleep(min(2 ** attempt, 20))  # 1,2,4,8,16,20s
                last_err = e
                continue
            raise
    raise last_err  # pragma: no cover


def embed_batch(texts: list[str], *, client: Any | None = None, dim: int = EMBEDDING_DIM) -> list[list[float]]:
    """Embed a list of texts (Titan v2 is single-input; loop). Heavy batches run on Fargate."""
    c = client or _client()
    return [embed_text(t, client=c, dim=dim) for t in texts]
