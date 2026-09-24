# Phase 1 — Conclusion

> The end-to-end Phase-1 run of the Cloud Security Knowledge Hub: a baseline RAG system
> (dense retrieval → Claude generation with citations → guardrails) taken through **live
> ingestion, offline evaluation, live online testing, and observability**, with every stage
> documented against real AWS evidence. Account `001961766007` · `us-east-1` · tag
> `usecase=rag-prod`. Run date: 2026-09-23.

## 1. What Phase 1 set out to prove
That the baseline is **real, measured, and improvable** — a trustworthy reference point for
Phase 2's advanced-RAG work. Not "is it perfect", but "does the whole loop
(ingest → index → retrieve → generate → evaluate → observe → improve) actually run, and do we
have honest numbers and findings to act on."

## 2. What was accomplished (by stage)

| Stage | Outcome |
|---|---|
| **C0 — Q&A capture** | Added the `CSHUB_QA` structured log line to the query Lambda (zero added latency). This is the prerequisite that makes online eval possible. Deployed + verified live. |
| **A — Offline ingestion** | Ingested the AWS Security Reference Architecture PDF live: **307 chunks, avg 980 chars, 0% null/empty, integrity passed.** Proved the FI-1 throttling fix works (SRA failed before the fix, succeeded after). Corpus ended clean at **19 docs / 337 chunks / 17 services**. |
| **B — Offline eval** | Golden set grown to **42 pairs** (+4 SRA). Re-scored via Bedrock LLM-judge. Corrected baseline (37 comparable Qs): **faithfulness 0.915 · relevancy 0.959 · precision 0.932 · recall 0.938**, p95 7.5s. Surfaced FI-4 (scorer artifact) and FI-5 (genuine IAM regression). |
| **C — Online testing** | Scored **7 live UI questions** through the new online scorer: **faithfulness 0.871 · relevancy 0.921**, deflection 14.3%, guardrail-block 0%, citation coverage 100%, avg latency 5.3s. Metrics emitted to `CSHub/OnlineEval`. |
| **D — Observability** | Full telemetry inventory captured with live sample values across `CSHub/Ingestion` (14), `CSHub/Eval` (4), `CSHub/OnlineEval` (8); 4 alarms all OK; dashboard + budget documented; console navigation written; 5 observability gaps logged. |
| **E — AI-SDLC reconciliation** | `AI-SDLC-AND-EVALS.md` updated with a §9 "as-run reality" that reconciles the plan with what actually ran. |

## 3. Headline results

**Offline (pre-release gate) — `phase1-post-sra`, 37 comparable Qs**
| Metric | Iteration-1 baseline | Phase-1 (post-SRA) | Δ |
|---|---|---|---|
| Faithfulness | 0.984 | 0.915 | −0.069 |
| Answer relevancy | 0.976 | 0.959 | −0.017 |
| Context precision | 0.940 | 0.932 | −0.008 |
| Context recall | 0.947 | 0.938 | −0.009 |
| p95 latency (ms) | 7,046 | 7,506 | +460 |

**Online (live traffic) — `phase1-online`, 7 questions**
| faithfulness | relevancy | deflection | guardrail-block | citation cov. | avg lat | p95 lat |
|---|---|---|---|---|---|---|
| 0.871 | 0.921 | 14.3% | 0% | 100% | 5,292 ms | 6,846 ms |

Both stay **well above the gate floors** (faith 0.80 / rel 0.75 / cp 0.70 / cr 0.70). The
system is grounded (100% citation coverage) and **honest under uncertainty** — an out-of-scope
question ("is SigV4 part of KMS encryption?") correctly returned "I don't have enough
information" rather than hallucinating.

## 4. The single most important finding
**FI-5 — corpus growth degraded IAM retrieval.** Adding 307 IAM-heavy SRA chunks pushed the
specific chunk that used to answer `iam-config-001` out of the top-6 of **dense-only**
retrieval, so a question that scored ~1.0 at baseline now deflects. This is not a bug to patch
— it is the **measured, concrete evidence** that the baseline needs **hybrid retrieval +
re-ranking + larger top-K**. It is the headline motivation for Phase 2, produced by the eval
loop doing exactly its job.

## 5. Findings register (Phase 1)
Full detail in [`FUTURE-IMPROVEMENTS.md`](./FUTURE-IMPROVEMENTS.md).

| ID | Finding | Status |
|---|---|---|
| FI-1 | Embedding throttling on large docs (ingestion loop) | ✅ Done (backoff + pacing) |
| FI-2 | Scale embedding for very large docs (batch / Fargate) | ⏳ Pending |
| FI-3 | Per-chunk service metadata for multi-service docs | ⏳ Pending |
| FI-4 | Offline scorer uses local samples, not real retrieval → false 0.00 | ◑ Partial (online half fixed via FI-6; offline pending) |
| FI-5 | Corpus growth degraded IAM retrieval (genuine regression) | ⏳ Pending (Phase 2) |
| FI-6 | OTel content-carrying traces (query/context/answer) → trace-grounded online eval | ✅ Done (verified 6/6 grounded) |

Plus 5 **observability gaps** (corpus-gauge drift, dashboard hardcoded to `baseline`, no
OnlineEval widget, no eval-drift alarms, chunks not console-browsable) in
[`04-observability.md`](./04-observability.md) §D.6.

## 6. Known limits of this Phase-1 run (honesty box)
- **Offline scores on PDF-sourced content are understated** in raw CloudWatch until FI-4 is
  fixed; the corrected numbers are the ones to trust.
- **Online eval was a manual 7-question sample**, not the automated sampler/feedback/alarm
  infra from `../../evals/ONLINE-EVAL-PLAN.md` (Steps 2/4/5 deferred).
- **Online faithfulness** is judged on answer self-consistency, not the real retrieved passage
  text (same root cause as FI-4).
- **Large multi-hundred-page PDFs** have no ingestion path yet (FI-2 Fargate deferred).
- **Golden set is 42 pairs**, below the ~100–200 v1 target; it grows via the log-mining flywheel.
- **CI eval-gate** is designed and runs locally, but not yet wired into a pipeline.

None of these block the Phase-1 conclusion; each is tracked and has an owner path into Phase 2.

## 7. Is the baseline ready to build on? — Yes.
The full loop runs end-to-end, quality is measured and above floors on both offline and live
traffic, the system refuses rather than hallucinates, and the failure modes are **understood
and written down**. Phase 2 has a clean reference point and a prioritised backlog.

## 8. Handoff to Phase 2
Enable the advanced-RAG stages one at a time (flags in `../../query-service/common/config.py`,
all OFF today), re-running the same eval harness and recording the delta vs this baseline:

1. **Hybrid + RRF** — should recover FI-5 (exact-term/IAM recall).
2. **Cohere rerank** — should lift context precision / put the right chunk first.
3. **Query transformation** — recall on ambiguous/multi-hop questions.
4. **Chain-of-Note** — faithfulness up, better "I don't know".
5. **CRAG** — correctness on out-of-corpus/stale queries.

Alongside the retrieval work, close the highest-value gaps: **FI-4** (score against real
retrieved context) so offline numbers are trustworthy on PDF content, and the **online-eval
infra** (sampler + feedback + drift alarms) so quality is continuously watched.

Continue in [`../phase-2/README.md`](../phase-2/README.md).
