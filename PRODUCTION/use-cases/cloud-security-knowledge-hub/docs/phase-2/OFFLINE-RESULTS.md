# Phase-2 Offline Results (`phase2-final`)

Phase-2 all-on (hybrid + rerank **k=10** + query-transform + Chain-of-Note + CRAG@0.30 +
metadata filter) vs the canonical Phase-1 baseline, on the same 30-doc / 534-chunk corpus and
61-pair golden set. Scored by Bedrock LLM-judge against **real retrieved context** (FI-6 spans,
**61/61** on `trace_context`). Config `phase2-final` → CloudWatch `CSHub/Eval`.

## Head-to-head (in-corpus 58 — the headline)
| Metric | Phase-1 | Phase-2 | Δ |
|---|---|---|---|
| Faithfulness | 0.969 | **0.983** | +0.015 |
| Answer relevancy | 0.930 | 0.816 | **−0.114** |
| Context precision | 0.849 | 0.837 | −0.012 |
| Context recall | 0.845 | 0.813 | −0.032 |
| p95 latency | 7,591 ms | **23,501 ms** | **~3×** |
| avg latency | 5,843 ms | 16,489 ms | ~2.8× |

All 61 (incl. OOC): faith 0.938→0.984 · rel 0.884→0.776 · cp 0.811→0.797 · cr 0.818→0.804.

## Verdict: NET NEGATIVE as configured
Faithfulness rose only because Phase-2 **refuses more** (a refusal never hallucinates).
Relevancy and recall fell, latency ~3×'d, and the FI-5 case **regressed**. Two isolated,
fixable root causes:

### 1. CRAG over-refuses (the main driver)
7 in-corpus golden questions newly deflected (IDK, answer_relevancy 0.00) that Phase-1 answered.
**4 of them had good retrieved context** (context recall ≥ 0.75) — CRAG's `CRAG_MIN_RELEVANCE=0.30`
grader rejected answerable questions:

| Question | Phase-2 ctx-recall | Phase-2 ans-rel | Read |
|---|---|---|---|
| `eks-attack-001` | 1.00 | 0.00 | perfect context, CRAG refused anyway |
| `ebs-prevent-001` | 0.95 | 0.00 | good context, refused |
| `secrets-config-001` | 0.95 | 0.00 | good context, refused |
| `sra-prevent-001` | 0.75 | 0.00 | adequate context, refused |
| `eks-prevent-001` | 0.30 | 0.00 | thin context (filter mis-route) |
| `s3-encryption-attack-001` | 0.00 | 0.00 | filter mis-route |
| `ec2-dataprotect-attack-001` | 0.00 | 0.00 | filter mis-route |

### 2. Metadata filter mis-routes some questions (incl. FI-5)
`infer_query_service` picks the single most-mentioned service and **hard-filters** to it. When it
guesses wrong, retrieval is restricted to the wrong service's chunks. The FI-5 case regressed:

| | Phase-1 | Phase-2 |
|---|---|---|
| `iam-config-001` ctx-precision | 0.65 | 0.30 |
| `iam-config-001` ctx-recall | 0.30 | 0.10 |
| `iam-config-001` ans-rel | 1.00 | 0.30 |

The filter FI-3 built to *fix* FI-5 made it worse here, because the question ("grant an app on
EC2 access to AWS services") infers service `ec2`, not `iam`, and the hard filter then excludes
the `iam-least-privilege` chunk.

## Phase-2 DID win on several (rerank + filter help when routing is right)
| Question | Phase-1 | Phase-2 |
|---|---|---|
| `apigw-config-001` | IDK (f0.80/ar0.70/cp0.65/cr0.75) | **1.00 / 1.00 / 1.00 / 1.00** |
| `s3-encryption-prevent-001` | ar 0.20, cp 0.10, cr 0.20 | **ar 0.95, cp 0.85, cr 0.95** |
| `sra-config-001` | cp 0.30 | **cp 1.00** |
| `rds-tls-prevent-001` | cr 0.30 | **cr 0.75** |
| `eks-pod-attack-001` | cr 0.30 | **cr 0.85** |

So reranking + the metadata filter clearly **help when the service routing is correct and CRAG
doesn't veto** — the gains are real, just outweighed by the two regressions above.

## The tuning pass → the shipped config
Acting on the above, we re-measured two reduced configs on the same 61-pair golden set:

1. **`phase2-tuned`** (CRAG lowered to 0.10, metadata filter + QT + CoN OFF): still deflected
   **10** in-corpus questions. Lowering the CRAG threshold just changed *which* questions fell
   under the bar — confirming **CRAG-by-Cohere-rank-score is the wrong grader** (that score is a
   relative ranking signal, not calibrated confidence), not merely mis-tuned. Rejected.
2. **`phase2-rerank-only`** (hybrid + rerank@k=10; CRAG / QT / CoN / metadata-filter all OFF):
   **the winner.**

| Metric | Phase-1 baseline | Phase-2 all-on | **Phase-2 rerank-only** |
|---|---|---|---|
| Faithfulness | 0.969 | 0.983 | **0.983** |
| Answer relevancy | 0.930 | 0.816 | **0.937** |
| Context precision | 0.849 | 0.837 | **0.853** |
| Context recall | 0.845 | 0.813 | **0.861** |
| p95 latency | 7,591 ms | 23,501 ms | 18,446 ms |
| New in-corpus deflections | — | +7 | **0** |

Rerank-only **beats the baseline on all four metrics**, with no new deflections and **no FI-5
regression** (iam-config returns to baseline cp 0.65 / cr 0.30 / ar 1.00 with the filter off).
The out-of-corpus questions still refuse correctly without CRAG — the grounding prompt already
handles that, so CRAG was redundant for refusal and harmful for borderline in-corpus questions.

**Keepers:** rerank@k=10 + hybrid. **Dropped:** CRAG, metadata filter, query-transform,
Chain-of-Note. Full write-up + verdict: `PHASE-2-CONCLUSION.md`. Shipped config is live on
`cshub-dev-query`.

> Results: `../../evals/results/phase2-final.json`, `../../evals/results/phase2-final-records.jsonl`.
> Full per-example scores in the JSON. Online counterpart: `ONLINE-RESULTS.md`.
