"""Bedrock clients: embed (Titan v2), generate (Claude), guardrails, and (Phase 2) rerank."""

from __future__ import annotations

import json
import os
from typing import Any

EMBEDDING_MODEL_ID = os.getenv("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
GENERATION_MODEL_ID = os.getenv("GENERATION_MODEL_ID", "anthropic.claude-sonnet-4-5-20250929-v1:0")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
GUARDRAIL_ID = os.getenv("GUARDRAIL_ID", "")
GUARDRAIL_VERSION = os.getenv("GUARDRAIL_VERSION", "DRAFT")


def _rt():
    import boto3

    return boto3.client("bedrock-runtime")


def embed_query(text: str, *, client: Any | None = None, dim: int = EMBEDDING_DIM) -> list[float]:
    c = client or _rt()
    body = json.dumps({"inputText": text, "dimensions": dim, "normalize": True})
    resp = c.invoke_model(modelId=EMBEDDING_MODEL_ID, body=body)
    return json.loads(resp["body"].read())["embedding"]


def generate(prompt: str, *, client: Any | None = None, max_tokens: int = 1024) -> str:
    """Claude generation via the Messages API on Bedrock."""
    c = client or _rt()
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    })
    resp = c.invoke_model(modelId=GENERATION_MODEL_ID, body=body)
    payload = json.loads(resp["body"].read())
    return "".join(blk.get("text", "") for blk in payload.get("content", []))


def apply_guardrail(text: str, source: str, *, client: Any | None = None) -> dict[str, Any]:
    """Apply a Bedrock Guardrail to input ('INPUT') or output ('OUTPUT').

    Returns {"action", "blocked", "text"}. No-op (allow) if no guardrail configured, so the
    baseline runs even before guardrails are set up.
    """
    if not GUARDRAIL_ID:
        return {"action": "NONE", "blocked": False, "text": text}
    c = client or _rt()
    resp = c.apply_guardrail(
        guardrailIdentifier=GUARDRAIL_ID,
        guardrailVersion=GUARDRAIL_VERSION,
        source=source,  # 'INPUT' or 'OUTPUT'
        content=[{"text": {"text": text}}],
    )
    action = resp.get("action", "NONE")
    blocked = action == "GUARDRAIL_INTERVENED"
    out = text
    if blocked:
        outs = resp.get("outputs", [])
        out = outs[0]["text"] if outs else "This request was blocked by content policy."
    return {"action": action, "blocked": blocked, "text": out}
