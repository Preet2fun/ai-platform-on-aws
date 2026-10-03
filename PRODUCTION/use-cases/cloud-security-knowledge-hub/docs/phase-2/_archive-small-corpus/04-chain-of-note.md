# Phase 2 · Stage 4 — Chain-of-Note

> Fourth advanced-RAG stage. Before answering, the model writes a short **relevance note per
> retrieved passage**, then composes the final answer grounded in those notes — targeting
> **faithfulness** and better honest "I don't know". Measured on top of the live rerank
> pipeline (config = CoN **+** rerank). **Verdict: DROP** — no faithfulness gain (already at
> ceiling) and a small relevancy regression, at extra latency. Code kept, flag off.

## What changed
- **Single-call CoN** (not two calls — latency was already high with rerank). One prompt asks
  the model to: (1) write a `NOTES:` line per numbered passage (relevant? what it contributes?),
  (2) emit a `=== FINAL ANSWER ===` marker, (3) give the grounded, cited answer after it — same
  IDK rule as the baseline. `prompt.py`: `build_prompt(..., chain_of_note=True)` +
  `split_final_answer()`. The user sees only the post-marker answer; the **notes are kept in the
  trace** (`cshub.con_notes`) for observability.
- Non-fatal: if the marker is missing, the full text is used. `max_tokens` bumped to 1536 when
  CoN is on. No new IAM (reuses generation).

## Results
Measured as **CoN + rerank** (rerank already live), all 42, real trace context.

### vs rerank-only (the honest comparison — incremental value of Chain-of-Note)
| Metric | Rerank-only | CoN+rerank | Δ | Verdict |
|---|---|---|---|---|
| faithfulness | 0.993 | 0.993 | +0.000 | ⚪ same |
| answer_relevancy | 0.971 | 0.961 | −0.011 | 🔴 worse |
| context_precision | 0.914 | 0.910 | −0.004 | 🔴 worse |
| context_recall | 0.925 | 0.925 | +0.000 | ⚪ same |
| avg latency | 12,392 ms | 15,367 ms | +2,975 ms | 🔴 worse |
| p95 latency | 21,491 ms | 23,377 ms | +1,886 ms | 🔴 worse |

**No faithfulness gain, small relevancy loss, more latency.** (`evals/results/phase2-chainofnote.json`)

### The telling per-question effect — `iam-config-001`
| | answer_relevancy | context_precision | context_recall |
|---|---|---|---|
| Rerank-only | 0.75 | 0.20 | 0.15 |
| CoN+rerank | **0.30** | 0.20 | 0.15 |

With the per-passage notes discipline, the model looked at the weakly-relevant IAM passages,
**noted they only partially matched, and answered more conservatively** — which the relevancy
judge scored lower. CoN did exactly what it's designed to do (be cautious when support is thin);
here that caution *reduced* a borderline-useful answer rather than improving it.

## Why it didn't help (this system)
Chain-of-Note's main lever is **faithfulness / hallucination reduction**. But faithfulness was
**already ~0.99** — the baseline prompt's strict grounding ("answer ONLY from the passages, else
say IDK") plus the reranker feeding clean context had already removed the headroom CoN targets.
With nothing to fix on faithfulness, CoN's added caution only trimmed relevancy on borderline
questions, and its extra output tokens cost ~3s. A classic "the earlier stage already solved the
problem this stage addresses" outcome — the eval loop doing its job.

## Decision — DROP (flag off), keep the code
- **Reverted `ENABLE_CHAIN_OF_NOTE=false`.** Live service remains **dense → rerank (k=60)**.
- **Kept the implementation** (tested: CoN-prompt + marker-split unit tests; flag-gated). It may
  earn its place later if faithfulness drops — e.g. after the corpus grows and retrieval gets
  noisier, or if the grounding prompt is relaxed. The notes are also a useful observability
  artifact (they're in the trace) even when the final answer is unchanged.
- Against `thresholds.json`, the small relevancy dip stays within max-regression, so it wouldn't
  hard-fail the gate — dropped on the keep-only-if-it-helps rule.

## Open items (end-of-Phase-2 comparison)
- Re-check CoN **after the next corpus upload** (its best case is a noisier, larger corpus where
  faithfulness has room to fall).
- If revisited, consider CoN **only as a fallback** on low-confidence retrievals (pair with CRAG,
  Stage 5) rather than on every query, to avoid the blanket latency/relevancy cost.

## Reproduce
```
# live env for this run: ENABLE_CHAIN_OF_NOTE=true, ENABLE_RERANK=true, RERANK_CANDIDATE_K=60
python evals/offline/collect_invoke.py --golden evals/golden/golden.jsonl \
    --function cshub-dev-query --out evals/results/phase2-chainofnote-records.jsonl
python evals/offline/score.py --records evals/results/phase2-chainofnote-records.jsonl \
    --config phase2-chainofnote --out evals/results/phase2-chainofnote.json \
    --minutes 120 --emit-cloudwatch
```
Artifacts: `evals/results/phase2-{baseline,rerank,querytransform,chainofnote}.json`.
