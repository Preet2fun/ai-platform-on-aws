"""Offline accuracy scoring via Bedrock LLM-as-judge (RAGAS-equivalent metrics).

Why LLM-as-judge instead of the RAGAS library here: RAGAS 0.2+ needs Python >=3.9 and a
heavy dep tree; the AI-SDLC plan explicitly lists "LLM-as-judge via Claude on Bedrock" as a
supported scoring layer. This computes the same four metrics on a 0-1 scale so the numbers
are directly comparable and feed the same gate/report:

  - faithfulness        : is every claim in the answer supported by the retrieved context?
  - answer_relevancy    : does the answer actually address the question?
  - context_precision   : are the retrieved contexts relevant to the question (low noise)?
  - context_recall      : do the retrieved contexts cover the ground-truth answer?

Contexts: the /query API returns only citation SOURCE ids, so we reconstruct the retrieved
passage TEXT from the local corpus (ingestion/samples) by doc_id for accurate scoring.

Usage:
  python score_offline.py --records results/records.jsonl --config baseline \
      --out results/baseline.json [--emit-cloudwatch]
"""
from __future__ import annotations

import argparse, json, os, re, sys, time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lib")))
from report import aggregate, aggregate_system  # noqa: E402

# corpus lives at <usecase>/ingestion/samples — two levels up from evals/online/
SAMPLES_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "ingestion", "samples"))
JUDGE_MODEL = os.getenv("JUDGE_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")


def _doc_text(doc_id: str) -> str:
    """Map a cited doc_id (e.g. 'docs/s3-secure-configuration.md') to local corpus text."""
    name = doc_id.split("/")[-1]
    path = os.path.join(SAMPLES_DIR, name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""


def _bedrock():
    import boto3
    return boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))


def _judge(client, prompt: str) -> float:
    """Ask Claude to return a single 0-1 score. Retries on throttling with backoff."""
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
                _t.sleep(2 ** attempt)  # 1,2,4,8,16s backoff
                continue
            raise


FAITH = ("Score from 0.0 to 1.0 how well EVERY claim in the ANSWER is supported by the CONTEXT "
         "(1.0 = fully grounded, 0.0 = unsupported/hallucinated). Reply with ONLY the number.\n\n"
         "CONTEXT:\n{ctx}\n\nANSWER:\n{ans}\n\nScore:")
RELV = ("Score from 0.0 to 1.0 how directly the ANSWER addresses the QUESTION "
        "(1.0 = fully on-point, 0.0 = irrelevant). Reply with ONLY the number.\n\n"
        "QUESTION:\n{q}\n\nANSWER:\n{ans}\n\nScore:")
CPREC = ("Score from 0.0 to 1.0 how relevant the retrieved CONTEXT is to the QUESTION "
         "(1.0 = all relevant, 0.0 = all noise). Reply with ONLY the number.\n\n"
         "QUESTION:\n{q}\n\nCONTEXT:\n{ctx}\n\nScore:")
CREC = ("Score from 0.0 to 1.0 how fully the CONTEXT covers the information in the "
        "GROUND TRUTH answer (1.0 = everything needed is present, 0.0 = missing). "
        "Reply with ONLY the number.\n\nGROUND TRUTH:\n{gt}\n\nCONTEXT:\n{ctx}\n\nScore:")


def score_record(client, rec: dict) -> dict:
    # unique cited docs -> concatenated corpus text (the retrieved context)
    doc_ids = list(dict.fromkeys(rec.get("contexts", [])))
    ctx = "\n\n---\n\n".join(t for t in (_doc_text(d) for d in doc_ids) if t)[:12000]
    ans, q, gt = rec.get("answer", ""), rec.get("question", ""), rec.get("ground_truth", "")
    if not ctx:
        return {"faithfulness": 0.0, "answer_relevancy": 0.0,
                "context_precision": 0.0, "context_recall": 0.0}
    return {
        "faithfulness": _judge(client, FAITH.format(ctx=ctx, ans=ans)),
        "answer_relevancy": _judge(client, RELV.format(q=q, ans=ans)),
        "context_precision": _judge(client, CPREC.format(q=q, ctx=ctx)),
        "context_recall": _judge(client, CREC.format(gt=gt, ctx=ctx)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    ap.add_argument("--config", default="baseline")
    ap.add_argument("--out", required=True)
    ap.add_argument("--emit-cloudwatch", action="store_true")
    args = ap.parse_args()

    records = [json.loads(l) for l in open(args.records, encoding="utf-8") if l.strip()]
    client = _bedrock()
    print(f"[score] {len(records)} records · judge={JUDGE_MODEL} (concurrent)")

    scored = []
    for i, rec in enumerate(records, 1):
        s = score_record(client, rec)
        scored.append((rec, s))
        print(f"  [{i}/{len(records)}] {rec['id']:<22} "
              f"f={s['faithfulness']:.2f} ar={s['answer_relevancy']:.2f} "
              f"cp={s['context_precision']:.2f} cr={s['context_recall']:.2f}", flush=True)

    rows, per_example = [], []
    for rec, s in scored:
        rows.append(s)
        per_example.append({"id": rec["id"], "question_type": rec["question_type"],
                            "service": rec["service"], **s,
                            "latency_ms": rec.get("server_latency_ms") or rec.get("client_latency_ms", 0),
                            "is_idk": rec.get("is_idk", False)})

    scores = aggregate(rows)
    # system metrics: use client latency where server latency was absent
    sys_rows = [{"latency_ms": (r.get("server_latency_ms") or r.get("client_latency_ms", 0))} for r in records]
    system = aggregate_system(sys_rows)

    result = {"config": args.config, "ts": int(time.time()), "n": len(records),
              "scores": scores, "system": system, "per_example": per_example}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print("\n=== aggregate scores ===")
    print(json.dumps({"scores": scores, "system": system}, indent=2))

    if args.emit_cloudwatch:
        import boto3
        cw = boto3.client("cloudwatch", region_name=os.getenv("AWS_REGION", "us-east-1"))
        cw.put_metric_data(Namespace="CSHub/Eval", MetricData=[
            {"MetricName": m, "Value": v, "Unit": "None",
             "Dimensions": [{"Name": "Config", "Value": args.config}]} for m, v in scores.items()])
        print("[score] emitted to CloudWatch CSHub/Eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
