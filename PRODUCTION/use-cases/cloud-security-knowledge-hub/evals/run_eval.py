"""Eval runner: score the query pipeline against the golden set with RAGAS.

Flow:
  load golden set -> for each item, run the query pipeline (records answer + retrieved
  contexts) -> score with RAGAS (faithfulness, answer_relevancy, context_precision,
  context_recall) -> aggregate -> compare vs baseline -> apply the quality gate ->
  write results + a markdown delta report.

Usage:
  python run_eval.py --golden golden/golden.jsonl --config baseline \
      --out results/baseline.json [--baseline results/baseline.json] [--emit-cloudwatch]

Notes:
  - RAGAS + a Bedrock LLM/embeddings are required to actually score (imported lazily).
  - The pipeline call uses query-service `run_pipeline`; set the same env the Lambda uses.
  - `--emit-cloudwatch` pushes aggregate scores as custom metrics (namespace CSHub/Eval)
    so online dashboards can track offline eval trends too.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

# make sibling packages importable when run from this dir
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "query-service")))

from gate import evaluate_gate           # noqa: E402
from report import aggregate, aggregate_system, render_markdown  # noqa: E402


def load_golden(path: str) -> list[dict]:
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def run_pipeline_for(question: str) -> dict:
    """Call the query-service pipeline. Returns {answer, contexts:[...]}.

    Imported lazily so unit tests of gate/report don't need boto3/psycopg.
    """
    import app  # query-service/app.py

    result = app.run_pipeline(question)
    # reconstruct contexts from citations for RAGAS (answer already includes them)
    contexts = [c.get("source") or c.get("doc_id") for c in result.get("citations", [])]
    return {"answer": result.get("answer", ""), "contexts": contexts,
            "latency_ms": result.get("latency_ms", 0)}


def score_with_ragas(records: list[dict]) -> list[dict]:
    """Score each record with RAGAS. Returns per-example metric rows.

    Requires `ragas` + a Bedrock-backed LLM/embeddings wrapper. Imported lazily.
    """
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall

    ds = Dataset.from_dict({
        "question": [r["question"] for r in records],
        "answer": [r["answer"] for r in records],
        "contexts": [r["contexts"] for r in records],
        "ground_truth": [r.get("ground_truth", "") for r in records],
    })
    res = evaluate(ds, metrics=[faithfulness, answer_relevancy, context_precision, context_recall])
    df = res.to_pandas()
    cols = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
    return [{c: float(row[c]) for c in cols if c in row} for _, row in df.iterrows()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--config", default="baseline", help="label for this run (e.g. baseline, hybrid, rerank)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--baseline", help="path to a prior results json to compare against")
    ap.add_argument("--thresholds", default=os.path.join(os.path.dirname(__file__), "thresholds.json"))
    ap.add_argument("--emit-cloudwatch", action="store_true")
    args = ap.parse_args()

    golden = load_golden(args.golden)
    print(f"[eval] {len(golden)} golden items · config={args.config}")

    records = []
    for i, item in enumerate(golden, 1):
        out = run_pipeline_for(item["question"])
        records.append({**out, "question": item["question"], "ground_truth": item.get("ground_truth", "")})
        print(f"  [{i}/{len(golden)}] {item['question'][:60]}...")

    rows = score_with_ragas(records)
    scores = aggregate(rows)
    system = aggregate_system(records)

    with open(args.thresholds, encoding="utf-8") as f:
        thresholds = json.load(f)
    baseline_scores = None
    if args.baseline and os.path.exists(args.baseline):
        with open(args.baseline, encoding="utf-8") as f:
            baseline_scores = json.load(f).get("scores")

    gate = evaluate_gate(scores, thresholds, baseline=baseline_scores, system=system)

    result = {"config": args.config, "ts": int(time.time()), "n": len(golden),
              "scores": scores, "system": system, "gate": gate.as_dict()}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
    if baseline_scores:
        print("\n" + render_markdown(scores, baseline_scores, args.config))

    if args.emit_cloudwatch:
        _emit_cloudwatch(scores, args.config)

    if not gate.passed:
        print("\n[GATE FAILED]\n - " + "\n - ".join(gate.failures), file=sys.stderr)
        return 1
    print("\n[GATE PASSED]")
    return 0


def _emit_cloudwatch(scores: dict, config: str) -> None:
    import boto3

    cw = boto3.client("cloudwatch")
    cw.put_metric_data(
        Namespace="CSHub/Eval",
        MetricData=[{"MetricName": m, "Value": v, "Unit": "None",
                     "Dimensions": [{"Name": "Config", "Value": config}]} for m, v in scores.items()],
    )


if __name__ == "__main__":
    raise SystemExit(main())
