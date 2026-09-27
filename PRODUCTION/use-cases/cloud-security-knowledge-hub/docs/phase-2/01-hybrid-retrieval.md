# Phase 2 · Stage 1 — Hybrid Retrieval + RRF

> First advanced-RAG stage, run the AI-SDLC way: enable one thing behind a flag, measure the
> delta vs the Phase-1 baseline on the golden set, keep it only if the gain justifies the
> latency/cost. **Verdict: DROP hybrid-alone** — no measurable gain, and it does **not** fix the
> FI-5 IAM regression (which needs reranking, Stage 2). The implementation is kept, tested, and
> flagged off, to be re-measured combined with rerank.

## Stage 0 — measurement readiness first (FI-4 fix)
Before measuring any retrieval change, we fixed the offline scorer so it grades against the
**real retrieved context**, not local sample files (the FI-4 artifact that false-0.00'd
S3-only docs like the SRA PDF). Reusing the FI-6 trace spans:
- `collect.py` / `collect_invoke.py` now capture the API's `request_id`.
- `score.py` joins the real `cshub.retrieved_context` from the `aws/spans` trace by
  `request_id` (falls back to local samples only if a span is missing).

Result: a **clean, honest Phase-2 baseline** scored 42/42 on real context (Phase 1 had to
*exclude* the 4 SRA questions to dodge the artifact):

| Metric | Phase-2 baseline (42, real context) |
|---|---|
| faithfulness | 0.992 |
| answer_relevancy | 0.958 |
| context_precision | 0.908 |
| context_recall | 0.919 |
| p95 latency | 7,703 ms |

This is the number Stage 1 had to beat. (`evals/results/phase2-baseline.json`)

## Stage 1 — what changed
`retrieval.hybrid_search()` (behind `enable_hybrid`): fetch a wider candidate pool (2×top-K)
from **both** dense (pgvector cosine) and sparse (Postgres full-text `tsvector`) retrievers,
merge with **Reciprocal Rank Fusion**, return the top-K. Full-text is non-fatal — if it errors
or returns nothing, hybrid falls back to the dense list (never worse on availability). Wired at
the marked hook in `run_pipeline`; the trace span records `cshub.retrieval_mode = hybrid|dense`.

Deployed to the live Lambda with `ENABLE_HYBRID=true`, ran the same 42-question collect + score
(`config=phase2-hybrid`), then **reverted the flag to `false`** (the baseline service stays
dense-only until a winning config is found).

## Results — delta vs baseline
| Metric | Baseline | Hybrid | Δ | Verdict |
|---|---|---|---|---|
| faithfulness | 0.992 | 0.992 | +0.000 | ⚪ flat |
| answer_relevancy | 0.958 | 0.949 | −0.009 | 🔴 slightly worse |
| context_precision | 0.908 | 0.901 | −0.007 | 🔴 slightly worse |
| context_recall | 0.919 | 0.916 | −0.004 | 🔴 slightly worse |
| p95 latency | 7,703 ms | 7,569 ms | −134 ms | ⚪ flat |
| avg latency | 5,673 ms | 5,756 ms | +83 ms | ⚪ flat |

**No improvement — a slight, within-noise regression.** Latency was unaffected (the second
retriever query is cheap next to generation). (`evals/results/phase2-hybrid.json`)

### FI-5 (the headline target) — NOT recovered
`iam-config-001` ("How should I grant an application on EC2 access to AWS services?"):

| | answer_relevancy | context_precision | context_recall | deflected? |
|---|---|---|---|---|
| Baseline (dense) | 0.00 | 0.30 | 0.20 | yes |
| Hybrid | 0.00 | 0.30 | 0.15 | yes |

Hybrid retrieved the same SRA-crowded top-6 and still deflected.

## Why hybrid alone didn't help (root cause, from trace evidence)
Full-text search **works** — verified behaviourally from the spans. A lexically-distinctive
query (`"IMDSv2 HttpTokens required hop limit metadata"`) produced true **RRF-fused scores**
(~0.033, 0.016, …) and correctly surfaced `ec2-imds-ssrf.md` at the top, mixed with other docs.
So `chunks.tsv` is populated across the corpus (including SRA) and RRF fuses correctly.

But for **iam-config-001**, the span showed all-six retrieved chunks were still the SRA PDF with
dense-like cosine scores — i.e. full-text contributed little and RRF returned the dense list.
The reason: the phrase *"grant an application on EC2 access to AWS services"* has **weak lexical
overlap** with the chunk that actually answers it (`iam-least-privilege.md`, which talks about
IAM roles / instance profiles / least privilege in different words). So:

> **FI-5 is a *semantic crowding* problem, not a lexical one.** The right chunk is semantically
> related but lexically dissimilar, and it is out-competed in dense space by 307 SRA vectors
> that mention IAM. Full-text can only help when the query and answer **share words** — here
> they don't, so hybrid can't rescue it.

The fix has to **re-order by true relevance regardless of vector crowding** — that is
**reranking (Stage 2)**, optionally with a larger candidate top-K and metadata filtering (FI-3,
per-chunk service tags). Hybrid is expected to pull its weight on *exact-term* queries
(service names, API/parameter names, error strings), which this small golden set under-samples.

## Decision — DROP (for now), keep the code
- **Keep hybrid off** in the baseline (flag reverted to `false`; live service is dense-only).
- **Keep the implementation** — it's tested (unit tests for fuse / empty-sparse fallback /
  fulltext-error) and flag-gated, ready to be re-measured **combined with rerank** in Stage 2,
  and on a golden set that includes more exact-term queries.
- Against `thresholds.json`, hybrid's small regression stays within the allowed max-regression
  (ar 0.05, cp/cr 0.05), so it wouldn't *hard-fail* the gate — but "no gain" is not worth
  shipping, so it's dropped on the keep-only-if-it-helps rule.

## Hand-off to Stage 2 (reranking)
1. Enable `enable_rerank` (Cohere Rerank or a cross-encoder) over a **larger candidate pool**
   (e.g. top-20 dense, or top-20 hybrid) → re-order → take top-6.
2. Re-run `phase2-rerank` and, separately, `phase2-hybrid-rerank` to see whether hybrid earns
   its place once a reranker is in front of generation.
3. Primary success check: does **iam-config-001** recover (stop deflecting, cp/cr rise)?
4. Consider FI-3 (per-chunk service tags) to enable metadata-filtered retrieval as a further
   mitigation for corpus-growth crowding.

## Reproduce
```
# baseline (dense) and hybrid, both scored against real trace context (FI-4 fixed):
python evals/offline/collect_invoke.py --golden evals/golden/golden.jsonl \
    --function cshub-dev-query --out evals/results/<cfg>-records.jsonl
python evals/offline/score.py --records evals/results/<cfg>-records.jsonl \
    --config <cfg> --out evals/results/<cfg>.json --minutes 90 --emit-cloudwatch
# hybrid run: set ENABLE_HYBRID=true on cshub-dev-query first, revert to false after.
```
Artifacts: `evals/results/phase2-baseline.json`, `evals/results/phase2-hybrid.json`.
