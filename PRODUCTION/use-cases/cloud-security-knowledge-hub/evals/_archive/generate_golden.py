"""Bootstrap candidate golden Q&A pairs from the ingested corpus (LLM-generated).

Since we start with no labeled pairs, this reads chunks from Aurora (sampled across services
and topics), asks Claude to write a realistic config/attack/prevention question + a grounded
answer for each, and writes CANDIDATE pairs to a JSONL for HUMAN REVIEW. Nothing enters the
golden set until a human sets `reviewed_by`.

Usage:
  python generate_golden.py --n 60 --out candidates.jsonl
Then review candidates.jsonl, edit/verify, set reviewed_by, and append accepted lines to
golden.jsonl.

Requires Bedrock + Aurora at runtime (imported lazily). Pure helpers below are unit-tested.
"""

from __future__ import annotations

import argparse
import json

PROMPT_TMPL = (
    "You are building an evaluation set for an AWS security knowledge assistant.\n"
    "From the passage below, write ONE realistic user question and a correct, concise answer "
    "GROUNDED ONLY in the passage. Choose the most fitting question_type from: configuration, "
    "attack, prevention.\n\n"
    "Return strict JSON: {{\"question\":\"...\",\"question_type\":\"...\",\"answer\":\"...\"}}\n\n"
    "PASSAGE (service={service}):\n{passage}\n"
)


def build_prompt(service: str, passage: str) -> str:
    return PROMPT_TMPL.format(service=service or "unknown", passage=passage[:2500])


def to_candidate(idx: int, service: str, llm_json: dict) -> dict:
    qtype = llm_json.get("question_type", "configuration")
    if qtype not in {"configuration", "attack", "prevention"}:
        qtype = "configuration"
    return {
        "id": f"{(service or 'gen')}-{qtype}-{idx:03d}",
        "question": llm_json.get("question", "").strip(),
        "question_type": qtype,
        "service": service or "unknown",
        "ground_truth": llm_json.get("answer", "").strip(),
        "expected_source_ids": [],
        "reviewed_by": "",   # MUST be set by a human before use
    }


def _sample_chunks(n: int) -> list[dict]:
    """Sample diverse chunks from Aurora (spread across services)."""
    import os, sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "query-service")))
    from common import retrieval  # reuse the DB connection helper

    conn = retrieval._connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT chunk_id, chunk_text, metadata FROM chunks "
                "ORDER BY random() LIMIT %s", (n,)
            )
            return [{"chunk_id": r[0], "text": r[1], "metadata": r[2] or {}} for r in cur.fetchall()]
    finally:
        conn.close()


def _llm_json(prompt: str) -> dict:
    import os, sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "query-service")))
    from common import bedrock

    raw = bedrock.generate(prompt, max_tokens=600)
    start, end = raw.find("{"), raw.rfind("}")
    return json.loads(raw[start:end + 1]) if start >= 0 else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--out", default="candidates.jsonl")
    args = ap.parse_args()

    chunks = _sample_chunks(args.n)
    with open(args.out, "w", encoding="utf-8") as f:
        for i, ch in enumerate(chunks, 1):
            service = (ch["metadata"] or {}).get("service", "unknown")
            try:
                llm = _llm_json(build_prompt(service, ch["text"]))
                cand = to_candidate(i, service, llm)
                if cand["question"] and cand["ground_truth"]:
                    f.write(json.dumps(cand) + "\n")
            except Exception as e:  # noqa: BLE001
                print(f"  skip chunk {ch['chunk_id']}: {e}")
    print(f"[generate] wrote candidates to {args.out} — HUMAN REVIEW required before use")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
