# Evaluation

Measures the RAG system's quality so each change is quantified and gated (see
`../AI-SDLC-AND-EVALS.md`).

## Terminology (industry definitions — used consistently here)

| | **Offline eval** | **Online eval** |
|---|---|---|
| **When** | Before release, in the AI-SDLC / CI — a quality gate | After release, continuously, on live traffic |
| **Data** | A fixed **golden set** (curated questions + known-good answers) | **Real production queries**, sampled from logs/traces |
| **Ground truth** | Yes (labeled expected answers) | Usually none — quality is inferred (LLM-judge on live answers, user feedback, deflection/guardrail rates) |
| **Answers "..."** | "Is this version good enough to ship?" | "Is the shipped system still good on real, changing traffic?" |

> **Not the same as operational monitoring.** CloudWatch dashboards, X-Ray, and latency/error
> alarms tell you the system is **up and fast** — that is *observability*, not answer-quality
> *online eval*. Online eval scores the **quality of live answers**.

## What is built vs. not

| Capability | Status | Where |
|---|---|---|
| **Offline eval** — query pipeline (golden set → 4 accuracy metrics → gate) | ✅ **Built** | `offline/` + `golden/` + `lib/gate.py` |
| **Offline system perf** — latency captured during the golden run | ✅ Built | `offline/score.py` → `results/baseline.json` |
| Operational monitoring — latency, errors, alarms | ✅ Built | `infra/05-observability.yaml` (ops, not quality) |
| **Online eval** — score real production traffic | ❌ **Not built** | design in `ONLINE-EVAL-PLAN.md` |
| **Ingestion quality eval** — chunk/embedding quality + continuous monitoring | ❌ **Not built** | placeholder in `ingestion/` |

> **Important:** everything under `offline/` is **offline eval**, even though `collect.py`
> sources answers by calling the *deployed* API. That is only an implementation detail —
> Aurora sits in a private VPC, so the pipeline can't run on a laptop. It is still offline
> eval: **fixed questions, labeled ground truth, a pre-release gate.**

## Folder structure

```
evals/
├── thresholds.json         # gate config: metric floors, max-regression, system ceilings
├── requirements.txt
│
├── lib/                    # shared, pure, unit-tested logic
│   ├── gate.py             # pass/fail: floors + regression-vs-baseline + system ceilings
│   └── report.py           # aggregate metrics + baseline-vs-candidate delta report
│
├── offline/                # OFFLINE eval (golden set → gate) — the working path
│   ├── collect.py          # run golden Qs through the pipeline → results/records.jsonl
│   └── score.py            # Bedrock LLM-as-judge → 4 metrics → results/baseline.json (+CloudWatch)
│
├── ingestion/              # INGESTION quality eval  [TODO — currently empty]
│
├── golden/
│   ├── SCHEMA.md           # golden-set field schema
│   └── golden.jsonl        # 38 human-reviewed Q&A pairs (config/attack/prevention · 16 services)
│
├── tests/
│   └── test_gate_and_report.py   # 7 offline unit tests for lib/
│
├── results/                # run artifacts (records.jsonl gitignored; baseline.json kept)
│   └── baseline.json       # Iteration-1 baseline scores — the number Phase-3 must beat
│
├── reports/
│   └── ITERATION-1-BASELINE.md   # the human-readable baseline report
│
└── _archive/               # superseded, NOT run (kept for reference)
    ├── run_eval.py         # original RAGAS-library runner (needs py3.9+ and in-VPC Aurora)
    ├── generate_golden.py  # original Aurora-based golden generator
    └── seed.jsonl          # original 5 starter examples
```

*(An `ONLINE-EVAL-PLAN.md` design doc describes the not-yet-built online eval.)*

## Metrics (offline)

**Accuracy (per golden question, 0–1):**
- **faithfulness** — every claim in the answer is grounded in retrieved context (catches hallucination)
- **answer_relevancy** — the answer addresses the question
- **context_precision** — retrieved context is relevant (low noise)
- **context_recall** — retrieved context covers the ground-truth answer

**System:** p50 / p95 / avg latency (and cost/query once metered).

## The quality gate (`lib/gate.py` + `thresholds.json`)

Fails a change if any metric is **below its floor**, **regresses** beyond the allowed delta vs
the recorded baseline, or a **system ceiling** is exceeded. Wired into CI (`.github/workflows/eval-gate.yml`).

## How to run the offline eval

```bash
# 1) collect pipeline outputs over the golden set (needs a Cognito id_token)
python offline/collect.py --golden golden/golden.jsonl \
  --api <ApiEndpoint> --token <id_token> --out results/records.jsonl

# 2) score accuracy with the Bedrock LLM-judge (+ push aggregate to CloudWatch CSHub/Eval)
AWS_PROFILE=agentcore AWS_REGION=us-east-1 \
python offline/score.py --records results/records.jsonl \
  --config baseline --out results/baseline.json --emit-cloudwatch
```

Why LLM-as-judge and not the RAGAS library: the local runtime is Python 3.8 (RAGAS needs
≥3.9). The judge computes the same four metrics on the same 0–1 scale and uses the **same judge
across iterations**, so the baseline-vs-Phase-3 **delta** is valid. The RAGAS-library path is
preserved in `_archive/run_eval.py` for when we run inside the VPC on py3.9+.

## Two-iteration measurement (the point of offline eval)

1. **Iteration 1 (baseline, Phase-3 OFF):** `results/baseline.json` + `reports/ITERATION-1-BASELINE.md`.
2. **Iteration 2 (Phase-3 advanced RAG):** enable one stage at a time, re-run the same two
   scripts with `--config <stage>`, and use `lib/report.py` to show the per-stage delta vs the
   baseline. Keep a stage only if its gain justifies its latency/cost.

## Golden dataset

`golden/golden.jsonl` — 38 human-reviewed pairs across the three question types
(configuration / attack / prevention) and all 16 corpus services. Schema in `golden/SCHEMA.md`.

## Not yet built (roadmap)

- **Ingestion quality eval + continuous monitoring** (`ingestion/`): chunk-size distribution,
  empty/duplicate-chunk rate, embedding sanity (dim/norm/non-null), corpus coverage; emit a
  `CSHub/Ingestion` CloudWatch namespace with a dashboard widget + alarms. Today the only
  ingestion signal is the per-doc **integrity** check in `../ingestion/handlers/manifest.py`
  (chunks produced · all embedded · DB count matches) — not a quality eval, no metrics emitted.
- **Online eval** (`ONLINE-EVAL-PLAN.md`): sample live Q&A from logs, async LLM-judge on live
  answers (no ground truth), user feedback (thumbs up/down), deflection + guardrail-block rates,
  and quality-drift alarms → `CSHub/OnlineEval` namespace.

## Test locally (no AWS)

```bash
python -m pytest tests -q      # 7 tests for lib/gate.py + lib/report.py
```
