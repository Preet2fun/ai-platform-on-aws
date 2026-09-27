"""Bedrock clients: embed (Titan v2), generate (Claude), guardrails, and (Phase 2) rerank."""

from __future__ import annotations

import json
import os
from typing import Any

EMBEDDING_MODEL_ID = os.getenv("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
GENERATION_MODEL_ID = os.getenv("GENERATION_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
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


_EXPAND_PROMPT = (
    "You rewrite a user's AWS security question into {n} alternative search queries that would "
    "retrieve relevant documentation. Vary the wording and surface synonyms / concrete AWS "
    "terms (service names, feature names, mechanisms) the answer likely uses, WITHOUT changing "
    "the meaning. Return ONLY the {n} queries, one per line, no numbering, no extra text.\n\n"
    "Question: {q}\n\nQueries:"
)


def expand_query(question: str, n: int = 3, *, client: Any | None = None) -> list[str]:
    """Multi-query expansion (Phase-2 Stage 3): return up to `n` reworded query variants.

    NON-FATAL: on any error returns [] so the caller falls back to the original question only.
    The original question is NOT included here — the caller always retrieves it plus these.
    """
    if n <= 0:
        return []
    try:
        txt = generate(_EXPAND_PROMPT.format(n=n, q=question[:1000]), client=client, max_tokens=256)
        variants = []
        for line in (txt or "").splitlines():
            v = line.strip().lstrip("0123456789.-) ").strip()
            if v and v.lower() != question.strip().lower():
                variants.append(v)
        # de-dupe, preserve order, cap at n
        seen, out = set(), []
        for v in variants:
            k = v.lower()
            if k not in seen:
                seen.add(k)
                out.append(v)
        return out[:n]
    except Exception as e:  # noqa: BLE001 - transform must never break the query
        print(f"query expansion failed (non-fatal, using original only): {e}")
        return []


RERANK_MODEL_ID = os.getenv("RERANK_MODEL_ID", "cohere.rerank-v3-5:0")


def _agent_rt():
    import boto3

    return boto3.client("bedrock-agent-runtime")


def rerank(query: str, hits: list, top_k: int, *, model_id: str | None = None,
           client: Any | None = None) -> list:
    """Re-order candidate `hits` by true query-relevance using a Bedrock rerank model.

    `hits` are retrieval.Hit objects (need `.text`). Returns the top_k hits in reranked order.
    NON-FATAL: on any error (model access, throttling, empty input) returns `hits[:top_k]`
    unchanged, so reranking can never break a query — it only ever re-orders.

    Phase-2 Stage 2 (FI-5): dense/hybrid retrieval can bury the right chunk under many similar
    vectors; a cross-encoder reranker scores each candidate against the query directly and lifts
    the genuinely relevant passage regardless of vector crowding.
    """
    if not hits:
        return []
    mid = model_id or RERANK_MODEL_ID
    region = os.getenv("AWS_REGION", "us-east-1")
    model_arn = f"arn:aws:bedrock:{region}::foundation-model/{mid}"
    try:
        c = client or _agent_rt()
        sources = [
            {"type": "INLINE",
             "inlineDocumentSource": {"type": "TEXT",
                                      "textDocument": {"text": (getattr(h, "text", "") or "")[:4000]}}}
            for h in hits
        ]
        resp = c.rerank(
            queries=[{"type": "TEXT", "textQuery": {"text": query[:2000]}}],
            sources=sources,
            rerankingConfiguration={
                "type": "BEDROCK_RERANKING_MODEL",
                "bedrockRerankingConfiguration": {
                    "numberOfResults": min(top_k, len(hits)),
                    "modelConfiguration": {"modelArn": model_arn},
                },
            },
        )
        reranked = []
        for r in resp.get("results", []):
            i = r["index"]
            if 0 <= i < len(hits):
                h = hits[i]
                # overwrite the stale dense score with the reranker's relevance score, so
                # downstream (CRAG grading + trace spans) sees the true query-relevance.
                try:
                    h.score = float(r.get("relevanceScore", h.score))
                except Exception:  # noqa: BLE001
                    pass
                reranked.append(h)
        return reranked[:top_k] if reranked else hits[:top_k]
    except Exception as e:  # noqa: BLE001 - rerank must never break the response
        print(f"rerank failed (non-fatal, using retrieval order): {e}")
        return hits[:top_k]


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
