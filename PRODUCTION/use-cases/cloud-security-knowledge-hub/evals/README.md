# Evaluation (P5) — RAGAS harness + quality gate

Measures the RAG pipeline against a golden set so quality is tracked continuously and each
Phase-2 stage's impact is quantified (see `../AI-SDLC-AND-EVALS.md`).

## What's here
```
evals/
├── run_eval.py        # runner: pipeline over golden set → RAGAS → aggregate → gate → report
├── gate.py            # quality-gate logic (floors, max regression, system ceilings)
├── report.py          # aggregation + baseline-vs-candidate delta report
├── thresholds.json    # gate thresholds (tune once the golden set exists)
├── requirements.txt
├── golden/            # golden dataset (schema, seed, generator)
│   ├── SCHEMA.md
│   ├── seed.jsonl         # 5 hand-written examples to start
│   └── generate_golden.py # LLM-generate CANDIDATE pairs from corpus (human review required)
└── tests/             # offline unit tests (gate, aggregation, delta) — 7, all passing
```

## Metrics (RAGAS)
- **faithfulness** — answer grounded in retrieved context (catches hallucination)
- **answer_relevancy** — answer addresses the question
- **context_precision** — retrieved context is relevant (retrieval noise)
- **context_recall** — the right context was retrieved
Plus system metrics: p95 latency, avg cost/query.

## The quality gate
`gate.py` fails a change if any metric is **below its floor**, **regresses** beyond the
allowed delta vs the recorded baseline, or a **system ceiling** is exceeded. Wired into CI
(`.github/workflows/eval-gate.yml`).

## Two-phase measurement (the point)
Run the baseline, save `results/baseline.json`. For each Phase-2 flag (hybrid, rerank,
query-transform, chain-of-note, crag), run again with that flag on and `--baseline
results/baseline.json` — the delta report shows exactly what the stage contributed.
```bash
python run_eval.py --golden golden/golden.jsonl --config baseline --out results/baseline.json
# enable ENABLE_HYBRID=true in the query env, then:
python run_eval.py --golden golden/golden.jsonl --config hybrid \
  --out results/hybrid.json --baseline results/baseline.json
```

## Golden dataset workflow (no labels yet)
1. `python golden/generate_golden.py --n 60 --out golden/candidates.jsonl`
   (LLM writes candidate Q&A from real corpus chunks).
2. **Human-review** each candidate; fix/verify `ground_truth`, set `reviewed_by`.
3. Append accepted lines to `golden/golden.jsonl`. Target ~100–200 reviewed pairs for v1.
4. Grow the set over time from real user queries (mined from logs).

## Test locally (no AWS)
```bash
python -m pytest tests -q      # gate/report/aggregation logic (7 tests)
```
`run_eval.py` and `generate_golden.py` need Bedrock + Aurora at runtime (RAGAS scoring +
corpus access); the gate/report logic is fully unit-tested offline.

## Notes
- **Not deployed / not run against live yet.** Harness + tests authored; golden set is seed-only.
- Offline eval scores can be pushed to CloudWatch (`--emit-cloudwatch`, namespace `CSHub/Eval`)
  so the observability dashboard tracks eval trends alongside online metrics.
- Tune `thresholds.json` once you have a real baseline; the current values are sensible starts.
