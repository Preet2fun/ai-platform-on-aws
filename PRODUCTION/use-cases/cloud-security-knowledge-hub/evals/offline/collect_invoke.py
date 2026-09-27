"""Collect offline eval records by INVOKING the query Lambda directly (no API/JWT).

Same output shape as collect.py, but calls the Lambda with a synthetic API-Gateway v2 event
instead of curl-through-API-Gateway. Use when you don't have a Cognito token handy — the JWT
authorizer guards the HTTP API route, not direct invoke; the pipeline (and its FI-6 trace span)
runs identically. Captures `request_id` so score.py can join real retrieved context (FI-4 fix).

Usage:
  AWS_PROFILE=agentcore AWS_REGION=us-east-1 \
  python collect_invoke.py --golden ../golden/golden.jsonl \
      --function cshub-dev-query --out ../results/records.jsonl
"""
from __future__ import annotations

import argparse, json, os, time


def load_golden(path):
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def _client():
    import boto3
    return boto3.client("lambda", region_name=os.getenv("AWS_REGION", "us-east-1"))


def invoke(client, function: str, question: str) -> dict:
    event = {
        "version": "2.0", "routeKey": "POST /query", "rawPath": "/query",
        "headers": {"content-type": "application/json"},
        "requestContext": {"http": {"method": "POST", "path": "/query"}},
        "body": json.dumps({"question": question}), "isBase64Encoded": False,
    }
    t0 = time.time()
    resp = client.invoke(FunctionName=function, Payload=json.dumps(event).encode())
    client_ms = int((time.time() - t0) * 1000)
    payload = json.loads(resp["Payload"].read() or b"{}")
    status = payload.get("statusCode", 0)
    body = {}
    try:
        body = json.loads(payload.get("body", "{}"))
    except json.JSONDecodeError:
        body = {"error": str(payload)[:200]}
    return {"status": status, "client_latency_ms": client_ms, **body}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--function", default="cshub-dev-query")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    golden = load_golden(args.golden)
    client = _client()
    print(f"[collect-invoke] {len(golden)} questions -> {args.function}")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    n_ok = n_err = n_idk = 0
    with open(args.out, "w", encoding="utf-8") as out:
        for i, item in enumerate(golden, 1):
            resp = invoke(client, args.function, item["question"])
            answer = resp.get("answer", "")
            contexts = [c.get("source") or c.get("doc_id") for c in resp.get("citations", [])]
            is_idk = "don't have enough information" in answer.lower()
            rec = {
                "id": item["id"], "question": item["question"],
                "question_type": item["question_type"], "service": item["service"],
                "ground_truth": item.get("ground_truth", ""),
                "expected_source_ids": item.get("expected_source_ids", []),
                "answer": answer, "contexts": contexts,
                "request_id": resp.get("request_id", ""),
                "retrieved": resp.get("retrieved", len(contexts)),
                "server_latency_ms": resp.get("latency_ms", 0),
                "client_latency_ms": resp.get("client_latency_ms", 0),
                "blocked": resp.get("blocked"), "status": resp.get("status"),
                "is_idk": is_idk,
            }
            out.write(json.dumps(rec) + "\n")
            if resp.get("status") != 200 or resp.get("error"):
                n_err += 1; tag = "ERR"
            elif is_idk:
                n_idk += 1; tag = "IDK"
            else:
                n_ok += 1; tag = "OK "
            print(f"  [{i}/{len(golden)}] {tag} {item['id']:<22} "
                  f"{rec['server_latency_ms']}ms rid={rec['request_id'][:8]}", flush=True)
    print(f"[collect-invoke] ok={n_ok} idk={n_idk} err={n_err} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
