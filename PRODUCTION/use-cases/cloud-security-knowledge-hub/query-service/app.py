"""Query service Lambda — Phase 1 baseline online pipeline.

  input guardrails -> embed query -> dense retrieval (pgvector) -> build prompt
  -> Claude generation (cited) -> output guardrails -> response

Phase-2 stages (hybrid+RRF, rerank, query transform, Chain-of-Note, CRAG) are gated behind
feature flags in Settings and wired at the marked hook points so each can be added and
A/B-measured against the baseline without restructuring.

API Gateway (HTTP API, proxy 2.0) event: JSON body { "question": "..." }.
"""

from __future__ import annotations

import json
import time

from common import bedrock
from common.config import get_settings
from common.prompt import build_prompt, citations_payload
from common import retrieval


def _resp(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"content-type": "application/json"},
            "body": json.dumps(body)}


def _parse_question(event: dict) -> str:
    body = event.get("body") or "{}"
    if isinstance(body, str):
        body = json.loads(body)
    q = (body.get("question") or "").strip()
    if not q:
        raise ValueError("missing 'question'")
    return q


def run_pipeline(question: str, s=None) -> dict:
    """Pure-ish orchestration (clients created inside). Returns the response payload."""
    s = s or get_settings()
    t0 = time.time()

    # 1) input guardrails
    gin = bedrock.apply_guardrail(question, "INPUT")
    if gin["blocked"]:
        return {"answer": gin["text"], "citations": [], "blocked": "input"}

    # 2) embed query
    qvec = bedrock.embed_query(question, dim=s.embedding_dim)

    # (Phase 2 hook) query transformation would expand `question` into multiple queries here.

    # 3) retrieval  — baseline: dense only
    hits = retrieval.dense_search(qvec, s.top_k)
    # (Phase 2 hook) if s.enable_hybrid: merge dense + fulltext via RRF
    # (Phase 2 hook) if s.enable_rerank: Cohere Rerank the candidates
    # (Phase 2 hook) if s.enable_chain_of_note: per-chunk notes before generation
    # (Phase 2 hook) if s.enable_crag: grade hits, refine/fallback if weak

    # 4) build cited prompt
    prompt, citations = build_prompt(question, hits)

    # 5) generate
    answer = bedrock.generate(prompt)

    # 6) output guardrails
    gout = bedrock.apply_guardrail(answer, "OUTPUT")
    if gout["blocked"]:
        return {"answer": gout["text"], "citations": [], "blocked": "output"}

    return {
        "answer": answer,
        "citations": citations_payload(citations),
        "blocked": None,
        "retrieved": len(hits),
        "latency_ms": int((time.time() - t0) * 1000),
    }


def handler(event, _context=None):
    try:
        question = _parse_question(event)
    except (ValueError, json.JSONDecodeError) as e:
        return _resp(400, {"error": str(e)})
    try:
        return _resp(200, run_pipeline(question))
    except Exception as e:  # noqa: BLE001 - surface a safe error, log detail
        print(f"query error: {e}")
        return _resp(500, {"error": "internal error"})
