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
import uuid

from common import bedrock
from common.config import get_settings
from common.prompt import build_prompt, citations_payload, split_final_answer
from common import retrieval
from common import tracing


def _resp(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"content-type": "application/json"},
            "body": json.dumps(body)}


# Prefix lets CloudWatch Logs Insights filter the Q&A record cleanly:
#   fields @timestamp, @message | filter @message like /CSHUB_QA/
_QA_LOG_PREFIX = "CSHUB_QA"


def _log_qa(request_id: str, question: str, result: dict, s) -> None:
    """Emit ONE structured JSON log line per query — the data source for online eval.

    This is the C0 prerequisite from ONLINE-EVAL-PLAN.md: without a record of production Q&A
    there is nothing to sample/score after release. It is a plain stdout write (captured by
    CloudWatch) — no extra network call, so query latency is unaffected. Answer is truncated
    to keep log lines bounded; full answer already went to the user.
    """
    try:
        answer = result.get("answer", "") or ""
        record = {
            "type": "qa",
            "request_id": request_id,
            "ts": int(time.time()),
            "question": question[:1000],
            "answer": answer[:2000],
            "answer_chars": len(answer),
            "citations": [c.get("doc_id") for c in result.get("citations", [])],
            "retrieved": result.get("retrieved", 0),
            "latency_ms": result.get("latency_ms", 0),
            "blocked": result.get("blocked"),
            "is_idk": "don't have enough information" in answer.lower(),
            "model_id": s.generation_model_id,
            "flags": {
                "hybrid": s.enable_hybrid, "rerank": s.enable_rerank,
                "query_transform": s.enable_query_transform,
                "chain_of_note": s.enable_chain_of_note, "crag": s.enable_crag,
            },
        }
        print(f"{_QA_LOG_PREFIX} {json.dumps(record)}")
    except Exception as e:  # noqa: BLE001 - logging must never break the response
        print(f"qa log failed (non-fatal): {e}")


def _parse_question(event: dict) -> str:
    body = event.get("body") or "{}"
    if isinstance(body, str):
        body = json.loads(body)
    q = (body.get("question") or "").strip()
    if not q:
        raise ValueError("missing 'question'")
    return q


def run_pipeline(question: str, s=None, request_id: str = "") -> dict:
    """Pure-ish orchestration (clients created inside). Returns the response payload.

    Wrapped in a GenAI content span (FI-6): the trace records the question, the exact retrieved
    chunks (id + text + score), and the answer, so online eval can score against real retrieved
    context. Tracing is optional/non-fatal (see common/tracing.py) — it never alters the answer.
    """
    s = s or get_settings()
    t0 = time.time()

    with tracing.span("rag.query") as sp:
        tracing.record_question(sp, request_id, question, s.generation_model_id)

        # 1) input guardrails
        gin = bedrock.apply_guardrail(question, "INPUT")
        if gin["blocked"]:
            tracing.record_answer(sp, gin["text"], blocked="input")
            return {"answer": gin["text"], "citations": [], "blocked": "input"}

        # 2) query set — Phase-2 Stage 3: multi-query expansion (enable_query_transform)
        #   Broaden recall by also searching reworded variants; the reranker sorts the merged pool.
        queries = [question]
        if s.enable_query_transform:
            variants = bedrock.expand_query(question, s.query_transform_n)
            queries += variants
            tracing.set_attr(sp, "cshub.query_variants", len(variants))

        # 3) retrieval (per query) + merge/dedup by chunk_id
        #   baseline: dense-only (pgvector cosine top-K)
        #   Phase-2 Stage 1: hybrid = dense + full-text merged with RRF (enable_hybrid)
        #   Phase-2 Stage 2: rerank a WIDER candidate pool down to top-K (enable_rerank)
        #   FI-3: metadata filter — restrict retrieval to the query's service (enable_metadata_filter)
        svc_filter = retrieval.infer_query_service(question) if s.enable_metadata_filter else None
        tracing.set_attr(sp, "cshub.metadata_filter", svc_filter or "none")
        fetch_k = s.rerank_candidate_k if s.enable_rerank else s.top_k
        merged: dict = {}
        for q in queries:
            qv = bedrock.embed_query(q, dim=s.embedding_dim)
            qhits = retrieval.hybrid_search(qv, q, fetch_k, service=svc_filter) if s.enable_hybrid \
                else retrieval.dense_search(qv, fetch_k, service=svc_filter)
            for h in qhits:
                if h.chunk_id not in merged:
                    merged[h.chunk_id] = h
        hits = list(merged.values())[: s.merged_candidate_cap]
        if s.enable_query_transform:
            tracing.set_attr(sp, "cshub.merged_candidates", len(hits))

        if s.enable_rerank:
            tracing.set_attr(sp, "cshub.rerank_candidates", len(hits))
            hits = bedrock.rerank(question, hits, s.top_k, model_id=s.rerank_model_id)
        else:
            # no reranker: order the merged pool by retrieval score before truncating
            hits = sorted(hits, key=lambda h: getattr(h, "score", 0.0), reverse=True)[: s.top_k]
        mode = ("hybrid" if s.enable_hybrid else "dense") \
            + ("+mdfilter" if svc_filter else "") \
            + ("+qt" if s.enable_query_transform else "") \
            + ("+rerank" if s.enable_rerank else "") \
            + ("+crag" if s.enable_crag else "")
        tracing.set_attr(sp, "cshub.retrieval_mode", mode)
        tracing.record_retrieval(sp, hits)   # <-- attaches the real retrieved passage text

        # 3b) CRAG (Phase-2 Stage 5): grade the retrieved context via the reranker's top
        #     relevance score; if it's below the floor, take the corrective action (honest IDK)
        #     instead of letting the model stretch thin context into a shaky answer.
        #     Requires rerank (that's the grade source); otherwise CRAG no-ops.
        if s.enable_crag and s.enable_rerank and hits:
            grade = float(getattr(hits[0], "score", 0.0) or 0.0)
            tracing.set_attr(sp, "cshub.crag_grade", grade)
            if grade < s.crag_min_relevance:
                tracing.set_attr(sp, "cshub.crag_action", "idk")
                answer = "I don't have enough information to answer that from the knowledge base."
                tracing.record_answer(sp, answer, blocked=None, is_idk=True)
                return {"answer": answer, "citations": [], "blocked": None,
                        "retrieved": len(hits), "latency_ms": int((time.time() - t0) * 1000)}
            tracing.set_attr(sp, "cshub.crag_action", "answer")

        # 4) build cited prompt (Phase-2 Stage 4: Chain-of-Note adds a per-passage notes step)
        prompt, citations = build_prompt(question, hits, chain_of_note=s.enable_chain_of_note)
        tracing.set_attr(sp, "cshub.chain_of_note", s.enable_chain_of_note)

        # 5) generate (CoN emits notes + answer, so allow more output tokens)
        raw = bedrock.generate(prompt, max_tokens=1536 if s.enable_chain_of_note else 1024)
        if s.enable_chain_of_note:
            answer = split_final_answer(raw)          # user sees only the post-marker answer
            tracing.set_attr(sp, "cshub.con_notes", raw[:2000])   # notes kept for observability
        else:
            answer = raw

        # 6) output guardrails
        gout = bedrock.apply_guardrail(answer, "OUTPUT")
        if gout["blocked"]:
            tracing.record_answer(sp, gout["text"], blocked="output")
            return {"answer": gout["text"], "citations": [], "blocked": "output"}

        is_idk = "don't have enough information" in (answer or "").lower()
        tracing.record_answer(sp, answer, blocked=None, is_idk=is_idk)
        return {
            "answer": answer,
            "citations": citations_payload(citations),
            "blocked": None,
            "retrieved": len(hits),
            "latency_ms": int((time.time() - t0) * 1000),
        }


def handler(event, _context=None):
    request_id = str(uuid.uuid4())
    try:
        question = _parse_question(event)
    except (ValueError, json.JSONDecodeError) as e:
        return _resp(400, {"error": str(e), "request_id": request_id})
    try:
        s = get_settings()
        result = run_pipeline(question, s, request_id=request_id)
        _log_qa(request_id, question, result, s)          # online-eval data source
        return _resp(200, {**result, "request_id": request_id})
    except Exception as e:  # noqa: BLE001 - surface a safe error, log detail
        print(f"query error [{request_id}]: {e}")
        return _resp(500, {"error": "internal error", "request_id": request_id})
