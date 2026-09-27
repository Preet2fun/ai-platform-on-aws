# Phase 2 — Advanced RAG (in progress)

The **Phase 2** run: enabling the advanced-RAG stages one at a time
(hybrid + RRF → Cohere rerank → query transformation → Chain-of-Note → CRAG), each measured
against the Phase-1 baseline using the same eval harness. One stage at a time; keep a stage only
if the gain justifies the latency/cost.

## Stage log (in run order)
| Doc | Stage | Outcome |
|---|---|---|
| `01-hybrid-retrieval.md` | Stage 0 (measurement readiness) + Stage 1 (hybrid + RRF) | Stage 0 ✅ fixed offline FI-4 (scorer now grades real trace context, 42/42) → clean baseline. Stage 1 ❌ **DROP** — hybrid alone gave no gain and didn't fix FI-5 (semantic crowding needs rerank). Code kept, flag off. |
| `02-reranking.md` | Stage 2 (reranking) | ◑ **KEEP (for now)** — Cohere Rerank 3.5 at `candidate_k=60` **fixes the FI-5 deflection** (iam-config-001 IDK→answering, ar 0.00→0.75) and nudges every metric up (0.993/0.971/0.914/0.925). **But p95 latency 7.7s→21.5s** (blows the 6s ceiling). Kept enabled; candidate-pool/latency tuning + FI-3 deferred to end-of-Phase-2. |
| `03-query-transformation.md` | Stage 3 (multi-query expansion) | ❌ **DROP** — on top of rerank, expansion is flat on quality and **slightly worse on recall** (cr 0.925→0.919) at +2.5s avg latency. Reranker already extracts the best chunks; variants just add near-duplicate SRA chunks. Code kept, flag off; revisit after corpus grows. |
| `04-chain-of-note.md` | Stage 4 (Chain-of-Note) | ❌ **DROP** — faithfulness was already ~0.99 (no headroom), so CoN gave **no faithfulness gain** and a small **relevancy loss** (0.971→0.961) at +3s latency. Its caution even trimmed a borderline answer (iam-config-001 ar 0.75→0.30). Code kept, flag off; revisit if faithfulness drops (bigger/noisier corpus) or paired with CRAG as a low-confidence fallback. |
| `05-crag.md` | Stage 5 (Corrective RAG) | ✅ **KEEP (safety net)** — grades retrieved context via the reranker score; if < 0.30, refuses honestly (skips generation). Neutral on the golden set (can't measure it — all goldens answerable) with **zero false-corrections**; real value shown live: out-of-corpus Azure Q → correct IDK in **0.8 s** vs a shaky answer. Kept enabled; threshold to re-validate post-corpus-upload. |

**Phase-2 baseline (clean, all 42, real context):** faithfulness 0.992 · answer_relevancy 0.958
· context_precision 0.908 · context_recall 0.919 · p95 7,703 ms
(`../../evals/results/phase2-baseline.json`).

**Live service now runs:** dense retrieval → **rerank (Cohere 3.5, k=60)** → Claude, tracing on.

## Stage scoreboard (all 42, real trace context)
| Config | faith | rel | cp | cr | p95 latency | Decision |
|---|---|---|---|---|---|---|
| baseline (dense) | 0.992 | 0.958 | 0.908 | 0.919 | 7.7s | reference |
| hybrid+RRF | 0.992 | 0.949 | 0.901 | 0.916 | 7.6s | ❌ drop |
| **rerank (k=60)** | 0.993 | 0.971 | 0.914 | 0.925 | 21.5s | ◑ **keep (live)** |
| qt+rerank | 0.994 | 0.973 | 0.912 | 0.919 | 21.5s | ❌ drop (qt) |
| CoN+rerank | 0.993 | 0.961 | 0.910 | 0.925 | 23.4s | ❌ drop (CoN) |
| CRAG+rerank | 0.994 | 0.973 | 0.911 | 0.924 | 21.4s | ✅ keep (safety net) |

**Reading:** on this small, clean corpus **rerank is the one stage that moved every metric up**
(it fixed the FI-5 deflection). Hybrid, query-transform and Chain-of-Note added no incremental
value because rerank already solved what they target. CRAG is neutral on the golden set by
design (it only acts on out-of-corpus/weak retrieval, which the golden set doesn't contain) but
is kept as a cheap, zero-false-correction safety net. Expect this picture to shift after the
corpus grows — that's the deferred end-of-phase re-run.

## Phase-2 stages: COMPLETE (5/5)
Live pipeline: **dense retrieve (top-60) → rerank (Cohere 3.5) → CRAG grade → generate (or honest
IDK)**, with OTel content tracing on. Flags: rerank ON, CRAG ON; hybrid / query-transform /
Chain-of-Note OFF (code kept, flag-gated).

## Deferred to the end-of-Phase-2 comparison (after the next corpus upload)
Per plan, the in-depth comparison + `PHASE-2-CONCLUSION.md` run **on the larger corpus**, not
this small one, because the small clean corpus under-exercises most stages. Open items:
- Re-run all six configs on the bigger corpus; re-check hybrid / query-transform / Chain-of-Note
  (they may pay off with more diverse content).
- Sweep `RERANK_CANDIDATE_K` (20/30/40/60) for the quality-vs-latency knee (rerank p95 is ~21s).
- Re-validate the CRAG `0.30` threshold on the new relevance-score distribution; add out-of-corpus
  golden questions so CRAG becomes measurable.
- FI-3 (per-chunk service tags → metadata-filtered retrieval) as the structural fix behind FI-5.
- Then write `PHASE-2-CONCLUSION.md`.

When Phase 2 completes, this folder will also hold updated online-testing + observability
evidence and a `PHASE-2-CONCLUSION.md`.

Reference points from Phase 1:
- Phase-1 conclusion: [`../phase-1/PHASE-1-CONCLUSION.md`](../phase-1/PHASE-1-CONCLUSION.md)
- Findings that motivate Phase 2: [`../phase-1/FUTURE-IMPROVEMENTS.md`](../phase-1/FUTURE-IMPROVEMENTS.md)
- Chunking & retrieval strategy (baseline + hooks): [`../phase-1/05-chunking-and-retrieval.md`](../phase-1/05-chunking-and-retrieval.md)
- Baseline scores: `../../evals/reports/ITERATION-1-BASELINE.md`
- Advanced-RAG flags live in `../../query-service/common/config.py` (all OFF in Phase 1).

## Per-area phase references
Each code area carries its own "Phase 1 vs Phase 2" block (what shipped, what was missing, what
Phase 2 adds and why) — start there when working in that area:
- Query service (retrieval/generation/tracing): [`../../query-service/README.md`](../../query-service/README.md)
- Ingestion (chunking/large-docs/embedding): [`../../ingestion/README.md`](../../ingestion/README.md)
- Evals (offline/online/ingestion-quality): [`../../evals/README.md`](../../evals/README.md)
- Diagrams (architecture/flows): [`../../diagrams/README.md`](../../diagrams/README.md)

## What Phase 2 adds, by area (why it's needed)
| Area | Phase-2 work | Missing in Phase 1 (finding) |
|---|---|---|
| Retrieval | Hybrid + RRF → Cohere rerank → query-transform | Dense-only regressed as corpus grew (**FI-5**) |
| Generation | Chain-of-Note, CRAG | Faithfulness / out-of-corpus fallback headroom |
| Ingestion | Per-chunk service tagging; Fargate large-PDF path | **FI-3** (mono-service tags), **FI-2** (900s Lambda limit) |
| Evals | Automated online sampler + feedback + drift alarms; offline real-context scoring | Manual online run; offline **FI-4** half still open |
