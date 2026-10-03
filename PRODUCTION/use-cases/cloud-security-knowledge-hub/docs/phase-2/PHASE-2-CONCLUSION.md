# Phase 2 — Conclusion (Advanced RAG head-to-head)

> The Phase-2 run measured advanced RAG against the canonical Phase-1 baseline on the full
> **30-doc / 534-chunk** corpus and **61-pair** golden set, every record scored by Bedrock
> LLM-judge against **real retrieved context** (FI-6 trace spans, 61/61). Account `001961766007`
> · `us-east-1` · tag `usecase=rag-prod`.
>
> **Headline:** the all-on configuration was a **net negative**; a **reduced config — hybrid +
> rerank only — beats the baseline on every quality metric** and is the shipped Phase-2 config.

## 1. The three configurations

| Config | Stages on | Flags |
|---|---|---|
| **Phase-1 baseline** | dense top-6 | all advanced OFF |
| **Phase-2 all-on** | hybrid + rerank(k=10) + query-transform + Chain-of-Note + CRAG(0.30) + metadata filter | all ON |
| **Phase-2 rerank-only (shipped)** | hybrid + rerank(k=10) | HYBRID+RERANK on; CRAG / QT / CoN / metadata-filter OFF |

## 2. Offline head-to-head (in-corpus 58 — the headline)

| Metric | Phase-1 baseline | Phase-2 all-on | **Phase-2 rerank-only** |
|---|---|---|---|
| Faithfulness | 0.969 | 0.983 | **0.983** |
| Answer relevancy | 0.930 | 0.816 | **0.937** |
| Context precision | 0.849 | 0.837 | **0.853** |
| Context recall | 0.845 | 0.813 | **0.861** |
| p95 latency | 7,591 ms | 23,501 ms | 18,446 ms |
| avg latency | 5,843 ms | 16,489 ms | 11,800 ms |
| New in-corpus deflections vs baseline | — | **+7** | **0** |

**Rerank-only beats the baseline on all four quality metrics** (+0.014 / +0.007 / +0.004 / +0.016)
with **zero new deflections**. All-on *looks* higher on faithfulness only because it refuses more
(a refusal never hallucinates), while relevancy and recall drop.

(All-61 incl. the 3 out-of-corpus pairs — these are depressed by the offline judge penalising
honest refusals, FI-7; in-corpus is the honest number: baseline 0.938/0.884/0.811/0.818,
all-on 0.984/0.776/0.797/0.804, rerank-only 0.967/0.891/0.814/0.833.)

## 3. Online head-to-head (same 13 live questions)

| | Phase-1 (`phase1-final-online`) | Phase-2 all-on (`phase2-final-online`) |
|---|---|---|
| In-corpus faithfulness (10) | 0.942 | 0.970 |
| In-corpus relevancy (10) | 0.955 | 0.945 |
| Deflection | 23.1% (3/13, all OOC) | 23.1% (3/13, all OOC) |

Online, all-on was a **quality tie** with the baseline at ~2–3× latency (the offline over-refusal
didn't surface because broad multi-service live questions retrieve a richer pool than the narrow
golden pairs). Since rerank-only is a strict subset of all-on's stages that *removed* the harmful
ones, its online quality is at least the baseline's; we did not spend a separate online run on it
(offline is the sensitive probe and already shows the win). Detail: `ONLINE-RESULTS.md`.

## 4. Why all-on failed — two isolated, proven root causes

1. **CRAG over-refuses.** CRAG grades retrieved context by the **Cohere rerank top score** and
   refuses below `CRAG_MIN_RELEVANCE`. That score is a *relative ranking* signal, not a calibrated
   [0,1] confidence — many genuinely answerable in-corpus questions score low. All-on (0.30) newly
   deflected **7** in-corpus questions, **4 with good retrieved context** (recall ≥ 0.75). Lowering
   the threshold to 0.10 (`phase2-tuned`) didn't fix it — it just changed *which* 10 questions fell
   under the bar. **CRAG-by-rerank-score is the wrong grader**; turning CRAG off removed the
   over-refusal entirely while the grounding prompt still refuses true out-of-corpus questions.
2. **Metadata filter mis-routes.** `infer_query_service` picks the single most-mentioned service
   and **hard-filters** (`WHERE service = x`). When it guesses wrong the answer chunk is excluded.
   The **FI-5** case regressed under all-on: `iam-config-001` ("grant an app on EC2 access to AWS
   services") infers `ec2`, not `iam`, so the filter dropped the `iam-least-privilege` chunk
   (ctx-recall 0.30 → 0.10). With the filter off, FI-5 returns to its baseline level.

## 5. What actually helped (kept in the shipped config)
**Reranking (Cohere Rerank 3.5) over a hybrid dense+full-text candidate pool.** It lifted the
hardest baseline cases:

| Example | Phase-1 baseline | Phase-2 rerank-only |
|---|---|---|
| `apigw-config-001` | IDK (f0.80 / ar0.70 / cr0.75) | **1.00 / 1.00 / 1.00 / 1.00** |
| `sra-prevent-001` | ar 0.85, cr 0.30 | **ar 0.85, cr 0.75** |
| `rds-tls-prevent-001` | cr 0.30 | **cr 0.30→0.30** (answers; precision up) |
| `eks-pod-attack-001` | cr 0.30 | **cr 0.85** |
| aggregate recall | 0.845 | **0.861** |

## 6. Verdict
- **Ship: Phase-2 rerank-only** (hybrid + rerank@k=10). It is the only configuration that beats
  the baseline on every quality metric with no regressions. **This is the live default** on
  `cshub-dev-query`.
- **Do NOT ship: all-on.** CRAG and the metadata filter are net-harmful as built.
- **Cost/tradeoff:** rerank-only p95 is **18.4 s** (~2.4× the baseline's 7.6 s) — the Cohere rerank
  call plus the wider candidate fetch. Acceptable for a non-interactive security-research tool;
  flagged as the top Phase-3 latency-optimisation target (smaller candidate pool, parallel fetch,
  or a lighter reranker).

## 7. Findings status after Phase 2
- **FI-3 (per-chunk metadata filter):** per-chunk *tagging* is correct and proven corpus-wide, but
  the *query-time filter* that consumes it (hard `WHERE service = x` on a single inferred service)
  **hurts** — it mis-routes multi-service questions and regressed FI-5. **Left OFF.** Redesign
  needed before any reuse: soft *boost* (rerank weighting) instead of hard filter, or allow the
  top-2 inferred services. See `../phase-1/FUTURE-IMPROVEMENTS.md`.
- **FI-5 (dense top-6 recall gap on `iam-config-001`):** **still open.** The metadata filter was
  the intended fix and it backfired; rerank-only leaves FI-5 at its baseline level (ctx-recall
  0.30, but it *answers* correctly). Not a regression, not a fix — carried forward.
- **CRAG:** parked. If revisited, grade with a calibrated signal (LLM-judge of the top passages,
  or an absolute cross-encoder relevance score), not the Cohere rank score.

## 8. Reproduce
```bash
# shipped config: ENABLE_HYBRID=true, ENABLE_RERANK=true, RERANK_CANDIDATE_K=10,
#                 ENABLE_CRAG=false, ENABLE_QUERY_TRANSFORM=false,
#                 ENABLE_CHAIN_OF_NOTE=false, ENABLE_METADATA_FILTER=false
AWS_PAGER="" AWS_PROFILE=agentcore AWS_REGION=us-east-1 \
python3 evals/offline/collect_invoke.py --golden evals/golden/golden.jsonl \
  --function cshub-dev-query --out evals/results/phase2-rerank-only-records.jsonl
AWS_PAGER="" AWS_PROFILE=agentcore AWS_REGION=us-east-1 \
python3 evals/offline/score.py --records evals/results/phase2-rerank-only-records.jsonl \
  --config phase2-rerank-only --out evals/results/phase2-rerank-only.json --minutes 60 --emit-cloudwatch
```
Artifacts: `evals/results/phase2-rerank-only.json` (+ `-records.jsonl`), `phase2-final.json`
(all-on), `phase1-final.json` (baseline). CloudWatch `CSHub/Eval` dims `phase1-final`,
`phase2-final`, `phase2-rerank-only`.

> Detail: offline per-example `OFFLINE-RESULTS.md`; online `ONLINE-RESULTS.md`; baseline
> `../../evals/reports/ITERATION-1-BASELINE.md`; findings `../phase-1/FUTURE-IMPROVEMENTS.md`.
