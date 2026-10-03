# Phase 1 — Conclusion

> The end-to-end Phase-1 run of the Cloud Security Knowledge Hub: a baseline RAG system
> (dense retrieval → Claude generation with citations → guardrails) taken through **live
> ingestion, offline evaluation, live online testing, and observability**, with every stage
> documented against real AWS evidence. Account `001961766007` · `us-east-1` · tag
> `usecase=rag-prod`. Canonical baseline run: 2026-09-28 (`phase1-final`, 30 docs / 534 chunks).

## 1. What Phase 1 set out to prove
That the baseline is **real, measured, and improvable** — a trustworthy reference point for
Phase 2's advanced-RAG work. Not "is it perfect", but "does the whole loop
(ingest → index → retrieve → generate → evaluate → observe → improve) actually run, and do we
have honest numbers and findings to act on."

## 2. What was accomplished (by stage)

| Stage | Outcome |
|---|---|
| **C0 — Q&A capture** | Added the `CSHUB_QA` structured log line to the query Lambda (zero added latency). This is the prerequisite that makes online eval possible. Deployed + verified live. |
| **A — Offline ingestion** | Ingested PDFs live end-to-end (native `pypdf`, structure-aware chunking, 0% null/empty, integrity passed) and proved the FI-1 throttling fix. Corpus ended at **30 docs / 534 chunks / 17 services**, with FI-3 per-chunk service tags applied corpus-wide (SRA now spans 19 services, not all-`iam`). |
| **B — Offline eval** | Canonical baseline `phase1-final` on the full **30-doc / 534-chunk** corpus with the **61-pair** golden set, every record scored against **real retrieved context** (FI-6 spans, 61/61). In-corpus (58): **faithfulness 0.969 · relevancy 0.930 · precision 0.849 · recall 0.845**, p95 7.6s. Surfaced FI-5 (IAM/new-PDF recall gap) and FI-7 (judge penalizes honest refusals). |
| **C — Online testing** | 13 questions (10 in-corpus + 3 out-of-corpus) driven through the deployed UI, scored against real trace context (13/13). Config `phase1-final-online`: **faithfulness 0.955 · answer_relevancy 0.873 · deflection 23.1%** (all 3 OOC correctly refused) · guardrail-block 0%. |
| **D — Observability** | Full telemetry inventory captured with live sample values across `CSHub/Ingestion` (14), `CSHub/Eval` (4), `CSHub/OnlineEval` (8); 4 alarms all OK; dashboard + budget documented; console navigation written; 5 observability gaps logged. |
| **E — AI-SDLC reconciliation** | `AI-SDLC-AND-EVALS.md` updated with a §9 "as-run reality" that reconciles the plan with what actually ran. |

## 3. Headline results

**Offline (pre-release gate) — `phase1-final`, 61-pair golden, 30-doc/534-chunk corpus**
| Metric | In-corpus 58 (headline) | All 61 (CloudWatch) | Gate floor |
|---|---|---|---|
| Faithfulness | **0.969** | 0.938 | 0.80 |
| Answer relevancy | **0.930** | 0.884 | 0.75 |
| Context precision | **0.849** | 0.811 | 0.70 |
| Context recall | **0.845** | 0.818 | 0.70 |
| p95 latency (ms) | 7,591 | 7,591 | (ceiling 6,000) |

Every record was scored against the **real retrieved context** (FI-6 trace spans, 61/61). The
in-corpus scores clear all accuracy floors comfortably; p95 latency is over the ceiling (Claude
generation time). The 3 out-of-corpus pairs score low on the offline judge only because it
penalizes honest refusals (**FI-7**) — the answers were correct refusals; see §6.

**Online (live traffic) — `phase1-final-online`, 13 questions (13/13 on real trace context)**
| faithfulness | answer_relevancy | deflection | guardrail-block | grounded-on-real-context |
|---|---|---|---|---|
| 0.955 | 0.873 | 23.1% (3/13, all OOC) | 0% | 13/13 |

Same 13 questions are reused verbatim for Phase-2 (fair A/B). See `03-online-testing.md`.

The system is grounded (citations on in-corpus answers) and **honest under uncertainty** — the
out-of-corpus questions (Azure, GCP, bare-metal kubeadm) correctly returned "I don't have enough
information" rather than hallucinating.

## 4. The single most important finding
**FI-5 — dense top-6 misses the best chunk on a large, multi-service corpus.** On the full
30-doc corpus, `iam-config-001` still *answers* but its **context recall is only 0.30** at dense
top-6 — the specific `iam-least-privilege.md` chunk competes against hundreds of IAM-tagged SRA
chunks. The same recall gap shows on the new PDFs (`rds-tls-*`, `s3-encryption-*`,
`eks-pod-attack`). This is **measured, concrete evidence** that the baseline needs **the FI-3
per-chunk metadata filter + reranking** (at a modest k), and it is the headline motivation for
Phase 2 — produced by the eval loop doing exactly its job. (FI-3 now tags every chunk by its own
service; enabling the query-time filter is what Stage 2 measures.)

## 5. Findings register (Phase 1)
Full detail in [`FUTURE-IMPROVEMENTS.md`](./FUTURE-IMPROVEMENTS.md).

| ID | Finding | Status |
|---|---|---|
| FI-1 | Embedding throttling on large docs (ingestion loop) | ✅ Done (backoff + pacing) |
| FI-2 | Scale embedding for very large docs (batch / Fargate) | ⏳ Pending |
| FI-3 | Per-chunk service metadata for multi-service docs | ◑ Built + proven corpus-wide (filter gated for Phase 2) |
| FI-4 | Offline scorer used local samples, not real retrieval → false 0.00 | ✅ Done (scores against FI-6 trace context, 61/61) |
| FI-5 | Dense top-6 recall gap on large multi-service corpus | ⏳ Pending (Phase 2 — filter + rerank) |
| FI-6 | OTel content-carrying traces (query/context/answer) → trace-grounded eval | ✅ Done (offline + online score on real context) |
| FI-7 | Offline judge penalizes honest refusals (OOC pairs) | ⏳ Pending (report in-corpus; fix judge later) |

Plus 5 **observability gaps** (corpus-gauge drift, dashboard hardcoded to `baseline`, no
OnlineEval widget, no eval-drift alarms, chunks not console-browsable) in
[`04-observability.md`](./04-observability.md) §D.6.

## 6. Known limits of this Phase-1 run (honesty box)
- **Out-of-corpus pairs score low on the offline judge (FI-7):** the 3 OOC answers were correct
  refusals, but the offline judge penalizes refusals, so the **in-corpus (58)** number is the
  honest headline and OOC is tracked as a separate refusal-correctness check.
- **Online eval is a fixed 10-question run** through the UI, not the automated sampler/feedback/
  alarm infra from `../../evals/ONLINE-EVAL-PLAN.md` (Steps 2/4/5 deferred).
- **Large multi-hundred-page PDFs** have no ingestion path yet (FI-2 Fargate deferred).
- **Golden set is 61 pairs**, below the ~100–200 v1 target; it grows via the log-mining flywheel.
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
