"""Online evaluation on REAL production traffic (no ground truth).

This is Step 2 + Step 3 of ONLINE-EVAL-PLAN.md, run against live Q&A captured by the
`CSHUB_QA {json}` log line that query-service/app.py emits per request.

Difference from offline/score.py:
  - Offline scores against curated ground-truth context (golden set, pre-release gate).
  - Online has NO ground truth. We can only judge the two metrics that don't need labels:
        * faithfulness      — is every claim in the answer grounded in the cited passages?
        * answer_relevancy  — does the answer address the question?
    context_precision / context_recall need labels, so they are offline-only (by design).

  - Context source (FI-6 lands the FI-4 fix for the online path): each query now emits a
    content-carrying OTel span (`rag.query`) to CloudWatch Transaction Search (the `aws/spans`
    log group) with the REAL retrieved passage text (`cshub.retrieved_context` /
    `cshub.chunk.N.text`), keyed by `cshub.request_id`. This scorer joins the Q&A record to its
    span by request_id and judges faithfulness against the ACTUAL retrieved context — the same
    rigour as offline, on live traffic. If no span/context is found (tracing off, or the record
    predates FI-6), it falls back to the self-consistency grounding check (honest but weaker).

Behavioural proxies (Step 3, no LLM) are computed directly from the log fields:
  deflection rate (is_idk), guardrail-block rate (blocked), citation coverage,
  retrieval fill, avg/p95 latency.

Usage:
  # score a JSON array of CSHUB_QA records, pulling real context from traces by request_id:
  python score_online.py --qa /tmp/manual_qa.json --config phase1-online \
      --out ../results/phase1-online.json [--emit-cloudwatch]

  # or pull the live sample straight from the trace spans (no --qa file needed):
  python score_online.py --from-traces --minutes 120 --config phase1-online \
      --out ../results/phase1-online.json [--emit-cloudwatch]
"""
from __future__ import annotations

import argparse, json, os, re, sys, time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lib")))
from report import aggregate, aggregate_system  # noqa: E402

JUDGE_MODEL = os.getenv("JUDGE_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")


def _bedrock():
    import boto3
    return boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))


# ---- FI-6: read the real retrieved context from the GenAI trace spans (aws/spans) ----
SPANS_LOG_GROUP = os.getenv("SPANS_LOG_GROUP", "aws/spans")


def _logs_client():
    import boto3
    return boto3.client("logs", region_name=os.getenv("AWS_REGION", "us-east-1"))


def _run_insights(logs, log_group: str, query: str, minutes: int) -> list[dict]:
    """Run a CloudWatch Logs Insights query and return the parsed rows."""
    import time as _t
    start = int(time.time() - minutes * 60)
    end = int(time.time())
    qid = logs.start_query(logGroupName=log_group, startTime=start, endTime=end,
                           queryString=query, limit=1000)["queryId"]
    for _ in range(30):
        r = logs.get_query_results(queryId=qid)
        if r["status"] in ("Complete", "Failed", "Cancelled"):
            break
        _t.sleep(1)
    rows = []
    for res in r.get("results", []):
        rows.append({f["field"]: f.get("value", "") for f in res})
    return rows


def _span_attr(span: dict, key: str):
    """Pull an attribute value from a parsed aws/spans record (attributes is a dict)."""
    attrs = span.get("attributes") or {}
    return attrs.get(key)


def load_trace_context(minutes: int) -> dict[str, dict]:
    """Return {request_id: {retrieved_context, answer, is_idk, question}} from rag.query spans.

    Reads the `aws/spans` log group (X-Ray Transaction Search) for our content-carrying spans
    emitted by common/tracing.py. Keyed by cshub.request_id so it can be joined to CSHUB_QA.
    """
    logs = _logs_client()
    # pull raw span JSON; filter to our content spans
    rows = _run_insights(
        logs, SPANS_LOG_GROUP,
        "fields @message | filter @message like /cshub.question/ | sort @timestamp desc",
        minutes)
    out: dict[str, dict] = {}
    for row in rows:
        try:
            span = json.loads(row.get("@message", "{}"))
        except Exception:  # noqa: BLE001
            continue
        rid = _span_attr(span, "cshub.request_id")
        ctx = _span_attr(span, "cshub.retrieved_context")
        if not rid:
            continue
        # keep the first (most recent) span per request_id
        if rid not in out:
            out[rid] = {
                "retrieved_context": ctx or "",
                "answer": _span_attr(span, "cshub.answer") or "",
                "question": _span_attr(span, "cshub.question") or "",
                "is_idk": bool(_span_attr(span, "cshub.is_idk")),
                "retrieved_count": _span_attr(span, "cshub.retrieved_count") or 0,
            }
    return out


def records_from_traces(minutes: int) -> list[dict]:
    """Build CSHUB_QA-shaped records directly from trace spans (no --qa file needed)."""
    ctx = load_trace_context(minutes)
    recs = []
    for rid, s in ctx.items():
        # count chunks referenced in the joined context blob as a retrieved proxy
        recs.append({
            "request_id": rid,
            "question": s["question"],
            "answer": s["answer"],
            "citations": [],  # doc_ids live per-chunk on the span; not needed for scoring
            "retrieved": int(s["retrieved_count"] or 0),
            "latency_ms": 0,  # latency comes from CSHUB_QA logs / CloudWatch, not the span text
            "blocked": None,
            "is_idk": s["is_idk"],
            "model_id": "",
            "_retrieved_context": s["retrieved_context"],
        })
    return recs


def _judge(client, prompt: str) -> float:
    """Single 0-1 score from Claude. Backoff on throttling (sequential by design)."""
    import time as _t
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 10, "temperature": 0,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    })
    for attempt in range(6):
        try:
            resp = client.invoke_model(modelId=JUDGE_MODEL, body=body)
            txt = "".join(b.get("text", "") for b in json.loads(resp["body"].read()).get("content", []))
            m = re.search(r"[01](?:\.\d+)?", txt)
            return max(0.0, min(1.0, float(m.group(0)))) if m else 0.0
        except Exception as e:  # noqa: BLE001
            if "Throttl" in str(e) and attempt < 5:
                _t.sleep(2 ** attempt)
                continue
            raise


# Online judge prompts — no ground truth. Faithfulness is judged as internal grounding:
# does the answer make only claims it also attributes to its citations, and avoid
# unsupported / fabricated specifics? Relevancy is standard.
FAITH_ONLINE = (
    "You are auditing a RAG assistant's answer for GROUNDING on AWS security topics.\n"
    "Score 0.0-1.0 how well the ANSWER stays grounded: it should make only claims that are "
    "consistent with well-established AWS security facts and that it attributes to numbered "
    "citations [n], with NO fabricated APIs, parameters, or specifics. An answer that "
    "correctly says it lacks information should score 1.0 (it invents nothing). "
    "Reply with ONLY the number.\n\nQUESTION:\n{q}\n\nANSWER:\n{ans}\n\nScore:")
RELV_ONLINE = (
    "Score from 0.0 to 1.0 how directly the ANSWER addresses the QUESTION "
    "(1.0 = fully on-point, 0.0 = irrelevant). A truthful 'I don't have enough information' "
    "to an out-of-scope question is ON-POINT and should score high. "
    "Reply with ONLY the number.\n\nQUESTION:\n{q}\n\nANSWER:\n{ans}\n\nScore:")
# Real-context faithfulness (FI-6): judge against the ACTUAL retrieved passages from the span.
FAITH_GROUNDED = (
    "Score from 0.0 to 1.0 how well EVERY claim in the ANSWER is supported by the retrieved "
    "CONTEXT (1.0 = fully grounded in the context, 0.0 = unsupported/hallucinated). An answer "
    "that correctly says it lacks information scores 1.0 (it invents nothing). "
    "Reply with ONLY the number.\n\nCONTEXT:\n{ctx}\n\nANSWER:\n{ans}\n\nScore:")


def _norm(rec: dict) -> dict:
    """Accept either a raw CSHUB_QA log object or a pre-shaped record."""
    return {
        "request_id": rec.get("request_id", ""),
        "question": rec.get("question", ""),
        "answer": rec.get("answer", ""),
        "citations": rec.get("citations", []) or [],
        "retrieved": rec.get("retrieved", 0) or 0,
        "latency_ms": rec.get("latency_ms", 0) or 0,
        "blocked": rec.get("blocked"),
        "is_idk": bool(rec.get("is_idk", False)),
        "model_id": rec.get("model_id", ""),
        "_retrieved_context": rec.get("_retrieved_context", ""),
    }


def score_record(client, rec: dict) -> dict:
    """Judge faithfulness + relevancy. Faithfulness uses REAL retrieved context when the span
    provided it (FI-6/FI-4 fix), else falls back to the self-consistency check."""
    q, ans = rec["question"], rec["answer"]
    ctx = (rec.get("_retrieved_context") or "").strip()
    if ctx:
        faith = _judge(client, FAITH_GROUNDED.format(ctx=ctx[:12000], ans=ans))
        basis = "retrieved_context"
    else:
        faith = _judge(client, FAITH_ONLINE.format(q=q, ans=ans))
        basis = "self_consistency"
    return {
        "faithfulness": faith,
        "answer_relevancy": _judge(client, RELV_ONLINE.format(q=q, ans=ans)),
        "faithfulness_basis": basis,
    }


def behavioural_proxies(recs: list[dict]) -> dict:
    n = len(recs) or 1
    idk = sum(1 for r in recs if r["is_idk"])
    blocked = sum(1 for r in recs if r["blocked"])
    with_cites = sum(1 for r in recs if len(r["citations"]) > 0)
    full_retrieval = sum(1 for r in recs if r["retrieved"] >= 6)
    lat = sorted(r["latency_ms"] for r in recs if r["latency_ms"])
    p95 = lat[max(0, int(round(0.95 * (len(lat) - 1))))] if lat else 0
    return {
        "n": len(recs),
        "deflection_rate": round(idk / n, 4),
        "guardrail_block_rate": round(blocked / n, 4),
        "citation_coverage": round(with_cites / n, 4),
        "full_retrieval_rate": round(full_retrieval / n, 4),
        "avg_latency_ms": round(sum(lat) / len(lat), 1) if lat else 0,
        "p95_latency_ms": p95,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qa", help="JSON array of CSHUB_QA records")
    ap.add_argument("--from-traces", action="store_true",
                    help="Build the sample straight from rag.query trace spans (no --qa file).")
    ap.add_argument("--minutes", type=int, default=120,
                    help="Look-back window for trace lookups (default 120).")
    ap.add_argument("--config", default="phase1-online")
    ap.add_argument("--out", required=True)
    ap.add_argument("--emit-cloudwatch", action="store_true")
    args = ap.parse_args()

    if args.from_traces:
        recs = [_norm(r) for r in records_from_traces(args.minutes) if r.get("question")]
        print(f"[online] {len(recs)} records built from trace spans (last {args.minutes}m)")
    else:
        if not args.qa:
            print("error: provide --qa <file> or --from-traces", file=sys.stderr)
            return 2
        raw = json.load(open(args.qa, encoding="utf-8"))
        recs = [_norm(r) for r in raw if r.get("question")]
        # FI-6: enrich each record with the REAL retrieved context from its trace span.
        try:
            ctx_by_rid = load_trace_context(args.minutes)
            joined = sum(1 for r in recs if ctx_by_rid.get(r["request_id"], {}).get("retrieved_context"))
            for r in recs:
                c = ctx_by_rid.get(r["request_id"])
                if c and c.get("retrieved_context"):
                    r["_retrieved_context"] = c["retrieved_context"]
            print(f"[online] joined real retrieved context from traces for {joined}/{len(recs)} records")
        except Exception as e:  # noqa: BLE001
            print(f"[online] trace-context join skipped ({e}); using self-consistency fallback")

    client = _bedrock()
    print(f"[online] {len(recs)} live records · judge={JUDGE_MODEL} (sequential)")

    per_example, rows = [], []
    grounded_n = 0
    for i, rec in enumerate(recs, 1):
        s = score_record(client, rec)
        if s.get("faithfulness_basis") == "retrieved_context":
            grounded_n += 1
        # aggregate() only averages numeric fields; keep the basis label out of it
        rows.append({"faithfulness": s["faithfulness"], "answer_relevancy": s["answer_relevancy"]})
        per_example.append({
            "request_id": rec["request_id"], "question": rec["question"],
            "is_idk": rec["is_idk"], "blocked": rec["blocked"],
            "citations": len(rec["citations"]), "retrieved": rec["retrieved"],
            "latency_ms": rec["latency_ms"], **s,
        })
        print(f"  [{i}/{len(recs)}] f={s['faithfulness']:.2f} "
              f"ar={s['answer_relevancy']:.2f} [{s.get('faithfulness_basis')}]  "
              f"{rec['question'][:52]}", flush=True)

    quality = aggregate(rows, metrics=["faithfulness", "answer_relevancy"])
    proxies = behavioural_proxies(recs)
    proxies["grounded_on_real_context"] = f"{grounded_n}/{len(recs)}"

    result = {"config": args.config, "ts": int(time.time()), "n": len(recs),
              "quality": quality, "proxies": proxies, "per_example": per_example}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print("\n=== online quality (LLM-judge, no ground truth) ===")
    print(json.dumps(quality, indent=2))
    print("=== behavioural proxies ===")
    print(json.dumps(proxies, indent=2))

    if args.emit_cloudwatch:
        import boto3
        cw = boto3.client("cloudwatch", region_name=os.getenv("AWS_REGION", "us-east-1"))
        md = [{"MetricName": m, "Value": v, "Unit": "None",
               "Dimensions": [{"Name": "Config", "Value": args.config}]}
              for m, v in quality.items()]
        md += [{"MetricName": k, "Value": float(v), "Unit": "None",
                "Dimensions": [{"Name": "Config", "Value": args.config}]}
               for k, v in proxies.items()
               if k != "n" and isinstance(v, (int, float))]
        cw.put_metric_data(Namespace="CSHub/OnlineEval", MetricData=md)
        print(f"[online] emitted {len(md)} metrics to CloudWatch CSHub/OnlineEval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
