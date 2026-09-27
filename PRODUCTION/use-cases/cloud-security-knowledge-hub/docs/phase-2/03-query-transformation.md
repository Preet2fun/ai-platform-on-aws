# Phase 2 · Stage 3 — Query Transformation (multi-query expansion)

> Third advanced-RAG stage. Reword the user's question into several variants, retrieve for each,
> and merge the candidates so the reranker sees a broader pool — aimed at recall on ambiguous /
> underspecified questions. Measured **on top of the live rerank pipeline** (so the config is
> query-transform **+** rerank). **Verdict: DROP** — no incremental quality gain over
> rerank-alone (slightly negative on retrieval recall) at extra latency. Code kept, flag off.

## What changed
- **Approach:** multi-query expansion (not HyDE). `bedrock.expand_query()` asks Claude for
  `QUERY_TRANSFORM_N=3` reworded variants (synonyms / concrete AWS terms, same meaning).
- **Pipeline (`enable_query_transform`):** embed + retrieve `fetch_k` for the original **and**
  each variant, **merge + dedup by `chunk_id`**, cap at `MERGED_CANDIDATE_CAP=60`, then hand the
  merged pool to the reranker → top-K. Non-fatal: if expansion fails, fall back to the original
  question only.
- **Trace span:** `cshub.retrieval_mode = dense+qt+rerank`, `cshub.query_variants`,
  `cshub.merged_candidates`. Verified live (3 variants, 60 merged candidates → rerank → 6).

## Results
Measured as **query-transform + rerank** (rerank was already live), all 42, real trace context.

### vs Phase-1 baseline (dense-only)
| Metric | Baseline | qt+rerank | Δ |
|---|---|---|---|
| faithfulness | 0.992 | 0.994 | +0.002 |
| answer_relevancy | 0.958 | 0.973 | +0.014 |
| context_precision | 0.908 | 0.912 | +0.003 |
| context_recall | 0.919 | 0.919 | −0.001 |

### vs rerank-only (the honest comparison — incremental value of query-transform)
| Metric | Rerank-only | qt+rerank | Δ | Verdict |
|---|---|---|---|---|
| faithfulness | 0.993 | 0.994 | +0.001 | ⚪ noise |
| answer_relevancy | 0.971 | 0.973 | +0.001 | ⚪ noise |
| context_precision | 0.914 | 0.912 | −0.003 | 🔴 worse |
| context_recall | 0.925 | 0.919 | −0.006 | 🔴 worse |
| avg latency | 12,392 ms | 14,885 ms | +2,493 ms | 🔴 worse |
| p95 latency | 21,491 ms | 21,482 ms | ~flat | ⚪ |

**Almost all of the gain vs baseline comes from rerank, not from query-transform.** On top of
rerank, expansion is flat on quality and **slightly worse on retrieval precision/recall**, while
adding ~2.5s average latency (the expansion LLM call + 3 extra retrievals).

FI-5 (`iam-config-001`) was unchanged by expansion: ar 0.75 / cp 0.20 / cr 0.15 (same as
rerank-only) — deflection stays fixed, retrieval precision unmoved.

## Why it didn't help (this corpus)
The reranker already selects the best chunks from a strong 60-candidate pool. Adding 3 reworded
queries mostly pulls in **more of the same** (for IAM-type questions, more SRA chunks), which:
- **dilutes** the merged pool with near-duplicates, and
- can **push a good single-query chunk out** when the pool is capped at 60.

Multi-query expansion pays off most when the corpus has **diverse phrasings/vocabulary** the
single query misses and when there is **no** strong reranker to recover recall. Here we have a
tightly-scoped security corpus and an already-strong reranker, so expansion is redundant. This
is a genuine "keep only if it helps" result — the eval loop doing its job.

## Decision — DROP (flag off), keep the code
- **Reverted `ENABLE_QUERY_TRANSFORM=false`.** Live service remains **dense → rerank (k=60)**.
- **Kept the implementation** (tested: 3 expand_query unit tests; flag-gated) for two futures:
  1. Re-measure **after the next corpus upload** — a larger, more diverse corpus may make
     expansion pay off (it's exactly the condition where it helps).
  2. Try it with a **smaller candidate cap / dedup by doc** so variants add *diversity* rather
     than duplicate SRA chunks.
- Against `thresholds.json`, the small recall dip is within max-regression, so it wouldn't
  hard-fail the gate — but "no gain + more latency" is a drop on the keep-only-if-it-helps rule.

## Open items (end-of-Phase-2 comparison)
- Re-run query-transform after the corpus grows (its best-case condition).
- If revisited, dedup merged candidates by **doc_id diversity**, not just chunk_id, so expansion
  broadens coverage instead of stacking near-duplicates.

## Reproduce
```
# live env for this run: ENABLE_QUERY_TRANSFORM=true, ENABLE_RERANK=true,
#                        RERANK_CANDIDATE_K=60, QUERY_TRANSFORM_N=3, MERGED_CANDIDATE_CAP=60
python evals/offline/collect_invoke.py --golden evals/golden/golden.jsonl \
    --function cshub-dev-query --out evals/results/phase2-querytransform-records.jsonl
python evals/offline/score.py --records evals/results/phase2-querytransform-records.jsonl \
    --config phase2-querytransform --out evals/results/phase2-querytransform.json \
    --minutes 120 --emit-cloudwatch
```
Artifacts: `evals/results/phase2-{baseline,rerank,querytransform}.json`.
