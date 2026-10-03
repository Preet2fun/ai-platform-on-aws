# Phase 2 · Stage 2 — Reranking

> Second advanced-RAG stage. Retrieve a **wider candidate pool**, then re-order it with a
> cross-encoder **reranker** and keep the top-K for generation. This is the stage that targets
> **FI-5** (the IAM regression hybrid couldn't fix). **Verdict: it fixes the FI-5 deflection and
> improves every quality metric — but at a steep latency cost at the pool size required.**
> Left **enabled** on the live service for now; final tuning deferred to the end of Phase 2
> (and re-evaluation after the next corpus upload).

## What changed
- **Reranker:** Amazon Bedrock **Cohere Rerank 3.5** (`cohere.rerank-v3-5:0`), called via the
  `bedrock-agent-runtime` **Rerank API** (`bedrock.rerank()` in `query-service/common/bedrock.py`).
- **Pipeline (`enable_rerank`):** fetch a wider candidate pool (`RERANK_CANDIDATE_K`), rerank it
  against the question, take the top-K (6) for the prompt. Non-fatal: any rerank error falls
  back to the retrieval order, so reranking can only ever re-order, never break a query.
- **IAM:** added `bedrock:Rerank` to the query Lambda role (inline policy + in the CFN template).
- **Trace span** records `cshub.retrieval_mode = dense+rerank` and `cshub.rerank_candidates`.

## The candidate-pool finding (why k=20 wasn't enough)
Reranking a cross-encoder can only re-order what retrieval **fetches**. The first attempt used
`candidate_k=20` and **did not fix FI-5** — the trace span showed all 20 dense candidates were
SRA-PDF chunks. The answering chunk (`iam-least-privilege.md`, the golden `expected_source_id`
for `iam-config-001`) was **crowded out of the top-20** by the 307 SRA IAM-vectors. The reranker
never saw it, so it could only reshuffle SRA chunks.

Raising the pool to **`candidate_k=60`** pulled enough non-SRA candidates into range that the
reranker could surface relevant IAM content, and **FI-5 stopped deflecting**. This is the key
lesson of Stage 2: with a corpus-growth crowding problem, **rerank quality is gated by candidate
recall** — the pool has to be wide enough to contain the answer before reranking can help.

## Results — delta vs baseline (config `phase2-rerank`, candidate_k=60, all 42, real context)
| Metric | Baseline | Rerank | Δ | Verdict |
|---|---|---|---|---|
| faithfulness | 0.992 | 0.993 | +0.002 | 🟢 |
| answer_relevancy | 0.958 | 0.971 | +0.013 | 🟢 |
| context_precision | 0.908 | 0.914 | +0.006 | 🟢 |
| context_recall | 0.919 | 0.925 | +0.005 | 🟢 |
| **p95 latency** | **7,703 ms** | **21,491 ms** | **+13,788 ms** | 🔴 |
| avg latency | 5,673 ms | 12,392 ms | +6,719 ms | 🔴 |

First stage to move **every quality metric positively** — modest but uniform. (`evals/results/phase2-rerank.json`)

### FI-5 (`iam-config-001`) — deflection fixed, retrieval still imperfect
| | answer_relevancy | context_precision | context_recall | deflected? |
|---|---|---|---|---|
| Baseline (dense) | 0.00 | 0.30 | 0.20 | yes |
| Rerank (k=60) | **0.75** | 0.20 | 0.15 | **no** |

The user-visible symptom is resolved — it now **answers** instead of saying "I don't have enough
information." But context precision/recall stayed low: the reranker produced a usable answer from
**adjacent SRA IAM passages**, not from the ideal `iam-least-privilege.md` chunk. So FI-5's
retrieval quality is **partially** addressed — the deflection is gone, but true retrieval of the
best chunk still wants the FI-3 fix (per-chunk service tags → metadata-filtered retrieval) and/or
better chunk-level competition.

## The tradeoff — quality up, latency ~2.7× up
The quality gains are small; the latency cost is large. p95 went from **7.7s to 21.5s** (avg
5.7s → 12.4s), driven by `candidate_k=60`: the pipeline fetches 60 chunks and reranks all 60
passages, then still generates. Against `thresholds.json` (p95 ceiling 6,000 ms), this **blows
the system ceiling** — it would fail the gate on latency even though quality improves.

**Engineering read:** k=60 is diagnostically valuable (it proves the fix works) but too slow to
ship for an interactive tool. The likely production sweet spot is a **smaller pool** (e.g. k=30)
that still lifts FI-5 out of deflection with far less latency, plus FI-3 metadata filtering so a
small pool already contains the right chunk. That tuning is deliberately **deferred to the
end-of-Phase-2 comparison** (see Decision).

## Decision — KEEP enabled for now, tune at end of Phase 2
- **Kept enabled on the live service** (`ENABLE_RERANK=true`, `RERANK_CANDIDATE_K=60`,
  `ENABLE_HYBRID=false`) so later stages and the upcoming corpus upload are measured against the
  reranked pipeline, not silently reverted.
- **Not yet finalized:** the candidate-pool size / latency tradeoff is an explicit open item for
  the **end-of-Phase-2 in-depth comparison**, to be re-run **after the next batch of docs is
  ingested** (a bigger, more balanced corpus changes both the crowding and the latency picture).
- The **hybrid+rerank** combination (Stage 1 code + Stage 2) was implemented and is available
  behind flags but not separately measured here — it's on the end-of-phase comparison list.

## Hand-off / open items for the end-of-Phase-2 comparison
1. Sweep `RERANK_CANDIDATE_K` (20 / 30 / 40 / 60) for the quality-vs-latency knee.
2. Measure **hybrid + rerank** together vs rerank-alone.
3. Add **FI-3** (per-chunk service tags) so metadata-filtered retrieval keeps the answer chunk in
   a small pool — the structural fix for the SRA crowding behind FI-5.
4. Re-run everything **after the next corpus upload** and compare in depth before locking config.

## Reproduce
```
# live env for this run: ENABLE_RERANK=true, RERANK_CANDIDATE_K=60, ENABLE_HYBRID=false
python evals/offline/collect_invoke.py --golden evals/golden/golden.jsonl \
    --function cshub-dev-query --out evals/results/phase2-rerank-records.jsonl
python evals/offline/score.py --records evals/results/phase2-rerank-records.jsonl \
    --config phase2-rerank --out evals/results/phase2-rerank.json --minutes 120 --emit-cloudwatch
```
Artifacts: `evals/results/phase2-baseline.json`, `evals/results/phase2-hybrid.json`,
`evals/results/phase2-rerank.json`.
