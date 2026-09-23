"""Collect real baseline pipeline outputs by calling the deployed /query API.

Runs every golden question against the live query service (P3 flags OFF), capturing the
answer, retrieved contexts (from citations), and server-reported latency. Writes a records
JSONL that the RAGAS scorer (score_offline.py) consumes — this lets us score accuracy
offline while the pipeline itself runs in-VPC (Aurora is private, unreachable from here).

Usage:
  python collect_online.py --golden golden/golden.jsonl --api <ApiEndpoint> \
      --token <id_token> --out results/records.jsonl
"""
from __future__ import annotations

import argparse, json, subprocess, time


def load_golden(path):
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def call_api(api: str, token: str, question: str) -> dict:
    """Use curl (system cert store) to avoid Python.org macOS SSL cert issues."""
    body = json.dumps({"question": question})
    t0 = time.time()
    proc = subprocess.run(
        ["curl", "-s", "-w", "\n%{http_code}", "-X", "POST", api,
         "-H", "content-type: application/json",
         "-H", f"authorization: {token}",
         "-d", body],
        capture_output=True, text=True, timeout=120,
    )
    client_ms = int((time.time() - t0) * 1000)
    out = proc.stdout.rsplit("\n", 1)
    status = int(out[-1]) if out[-1].strip().isdigit() else 0
    try:
        data = json.loads(out[0]) if out[0].strip() else {}
    except json.JSONDecodeError:
        data = {"error": out[0][:200]}
    return {"status": status, "client_latency_ms": client_ms, **data}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--api", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    golden = load_golden(args.golden)
    print(f"[collect] {len(golden)} questions against {args.api}")

    import os
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    n_ok = n_err = n_idk = 0
    with open(args.out, "w", encoding="utf-8") as out:
        for i, item in enumerate(golden, 1):
            resp = call_api(args.api, args.token, item["question"])
            answer = resp.get("answer", "")
            contexts = [c.get("source") or c.get("doc_id") for c in resp.get("citations", [])]
            is_idk = "don't have enough information" in answer.lower()
            rec = {
                "id": item["id"], "question": item["question"],
                "question_type": item["question_type"], "service": item["service"],
                "ground_truth": item.get("ground_truth", ""),
                "expected_source_ids": item.get("expected_source_ids", []),
                "answer": answer, "contexts": contexts,
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
            print(f"  [{i}/{len(golden)}] {tag} {item['id']:<22} {rec['server_latency_ms']}ms")
    print(f"[collect] ok={n_ok} idk={n_idk} err={n_err} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
