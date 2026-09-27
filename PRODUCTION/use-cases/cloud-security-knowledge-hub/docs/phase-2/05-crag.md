# Phase 2 · Stage 5 — CRAG (Corrective RAG)

> Fifth and final advanced-RAG stage. **Grade** the retrieved context; if it's too weak to
> support an answer, take a **corrective action** (here: an honest "I don't have enough
> information" instead of stretching thin context into a shaky answer). Measured on top of the
> live rerank pipeline (config = CRAG **+** rerank). **Verdict: KEEP** — it's a cheap
> production **safety net** for out-of-corpus / weak-retrieval traffic. Note: the golden set
> can't score its value (see below); the decision rests on behaviour, not the aggregate delta.

## What changed
- **Grader = the reranker's top relevance score** (no extra model call). `bedrock.rerank()` now
  writes each returned Hit's `.score` = the Cohere `relevanceScore` (this also fixed a small
  observability wart — reranked spans previously showed stale dense scores).
- **Corrective action:** if `enable_crag` and the top reranked chunk's relevance <
  `CRAG_MIN_RELEVANCE` (0.30), the pipeline **short-circuits to the exact IDK answer and skips
  generation** entirely. Otherwise it answers normally.
- Non-fatal and composable: CRAG needs the reranker on (its grade source); with rerank off it
  no-ops. Trace span records `cshub.crag_grade` and `cshub.crag_action` (answer | idk).

## Why the golden set can't measure CRAG (the key insight)
All 42 golden questions are **answerable, in-corpus** questions. CRAG's corrective path only
fires on **weak/out-of-corpus** retrieval — which the golden set deliberately doesn't contain.
So on the golden set every question grades ≥ 0.30 and answers normally, making CRAG's aggregate
**identical to rerank-only**:

| Metric | Rerank-only | CRAG+rerank | Δ |
|---|---|---|---|
| faithfulness | 0.993 | 0.994 | +0.001 |
| answer_relevancy | 0.971 | 0.973 | +0.001 |
| context_precision | 0.914 | 0.911 | −0.003 |
| context_recall | 0.925 | 0.924 | −0.001 |
| avg latency | 12,392 ms | 11,694 ms | −698 ms |

All deltas are within noise. **Zero false-corrections** — no golden question was wrongly turned
into IDK. FI-5 (`iam-config-001`) preserved: it graded **0.507 ≥ 0.30** so CRAG let it answer
(ar 0.70, unchanged from rerank). (`evals/results/phase2-crag.json`)

## Where CRAG's value actually shows (behavioural sanity checks)
The value is on traffic the golden set lacks — verified live via the trace spans:

| Question | rerank relevance grade | CRAG action | latency | outcome |
|---|---|---|---|---|
| "prevent public S3 exposure" (in-corpus) | high | **answer** | 8.3 s | normal cited answer |
| "How should I grant an EC2 app AWS access?" (FI-5 borderline) | **0.507** | **answer** | 6.7 s | answers (FI-5 preserved) |
| "configure Azure AD conditional access" (out-of-corpus) | **0.165** | **idk** | **0.8 s** | correct honest refusal, generation skipped |

The 0.30 threshold cleanly separated genuine out-of-corpus (0.165) from borderline-but-answerable
(0.507). The out-of-corpus case is the win: instead of the model stretching irrelevant context
into a plausible-but-wrong answer, CRAG refused **correctly and ~10× faster** (0.8 s vs ~8 s,
because generation is skipped).

## Decision — KEEP (as a safety net), re-validate threshold post-corpus-upload
- **Kept enabled** (`ENABLE_CRAG=true`, `CRAG_MIN_RELEVANCE=0.30`, on top of rerank). Rationale:
  neutral on the golden set, **zero false-corrections**, and it correctly + cheaply refuses
  out-of-corpus questions — a real production-safety and cost/latency benefit that doesn't show
  up in golden-set aggregates.
- Unlike the other Phase-2 stages, this isn't a "keep because the numbers went up" decision —
  it's "keep because it's a safe, cheap guardrail for the traffic the eval set doesn't cover."
- **Open item:** the **0.30 threshold must be re-validated after the next corpus upload.** A
  larger, denser corpus changes the relevance-score distribution — the threshold that cleanly
  separates answerable from out-of-corpus today may need tuning. Add a few genuinely
  out-of-corpus questions to the golden set so CRAG's corrective path becomes measurable.

## Live pipeline after Stage 5
```
question → input guardrails → embed → dense retrieve (top-60)
        → rerank (Cohere 3.5) → CRAG grade (top relevance ≥ 0.30?)
             ├─ yes → Claude generate (cited) → output guardrails → answer
             └─ no  → honest IDK (skip generation)
```
All Phase-2 flags: rerank ON, CRAG ON; hybrid / query-transform / Chain-of-Note OFF.

## Reproduce
```
# live env: ENABLE_CRAG=true, ENABLE_RERANK=true, RERANK_CANDIDATE_K=60, CRAG_MIN_RELEVANCE=0.30
python evals/offline/collect_invoke.py --golden evals/golden/golden.jsonl \
    --function cshub-dev-query --out evals/results/phase2-crag-records.jsonl
python evals/offline/score.py --records evals/results/phase2-crag-records.jsonl \
    --config phase2-crag --out evals/results/phase2-crag.json --minutes 120 --emit-cloudwatch
```
Artifacts: `evals/results/phase2-{baseline,hybrid,rerank,querytransform,chainofnote,crag}.json`.
