# Phase 2 — Advanced RAG (to be run)

Placeholder for the **Phase 2** run: enabling the advanced-RAG stages one at a time
(hybrid + RRF → Cohere rerank → query transformation → Chain-of-Note → CRAG), each measured
against the Phase-1 baseline using the same eval harness.

Not started yet. When it runs, this folder will hold — mirroring Phase 1:
- per-stage eval deltas vs the Phase-1 baseline,
- updated online-testing + observability evidence,
- a `PHASE-2-CONCLUSION.md`.

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
