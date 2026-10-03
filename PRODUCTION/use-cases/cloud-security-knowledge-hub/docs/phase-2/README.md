# Phase 2 — Advanced RAG (head-to-head vs the canonical baseline)

**Phase 2** turns on the advanced-RAG stages and measures them **as one configuration**
(Option A: hybrid + Cohere rerank + query-transform + Chain-of-Note + CRAG + the FI-3 per-chunk
metadata filter, all on together) against the **canonical Phase-1 baseline** — using the same
eval harness, the same 30-doc / 534-chunk corpus, and the same 61-pair golden set.

> **Why all-on, not one-at-a-time?** An earlier stage-by-stage exploration was run on a **small
> corpus** and produced numbers too small to be meaningful; it is archived in
> `_archive-small-corpus/` (kept only for the engineering rationale, not as results). The real
> comparison is a single fair A/B: Phase-1 (all advanced flags OFF, dense top-6) vs Phase-2 (all
> stages ON), offline **and** online, on the enlarged corpus. This is the legitimate measurement.

## The two configurations under test

| | Phase-1 baseline (`phase1-final`) | Phase-2 all-on (`phase2-final`) |
|---|---|---|
| Retrieval | dense top-6 (cosine) | hybrid + **rerank** (Cohere 3.5, candidate **k≈10**) + **query-transform** |
| Generation | Claude Sonnet 4.5 (cited) | + **Chain-of-Note** + **CRAG** grade → honest IDK on weak retrieval |
| Metadata filter | off | **FI-3 per-chunk service filter** on (`ENABLE_METADATA_FILTER=true`) |
| Guardrails / tracing | on | on |

**Design choices (from the archived exploration + user direction):**
- **k ≈ 10, not 60** — the small-corpus run showed k=60 fixed FI-5 but blew latency (~3× p95).
  We accept possibly-smaller quality gains to keep the interactive latency/cost sane.
- **FI-3 metadata filter** is the structural fix for FI-5: with every chunk tagged by its own
  service (proven corpus-wide), a service-named query competes only against same-service chunks,
  so the answer chunk survives in a **small** pool — no need for a huge k.

## Canonical Phase-1 baseline (the number to beat)
`phase1-final`, 61-pair golden, 30-doc/534-chunk corpus, scored against real FI-6 trace context:

| | Faithfulness | Answer rel. | Context prec. | Context recall | p95 latency |
|---|---|---|---|---|---|
| In-corpus 58 (headline) | 0.969 | 0.930 | 0.849 | 0.845 | 7,591 ms |
| All 61 (incl. 3 OOC) | 0.938 | 0.884 | 0.811 | 0.818 | 7,591 ms |

Full report: `../../evals/reports/ITERATION-1-BASELINE.md` · offline detail:
`../phase-1/02-offline-eval.md`.

## What Phase-2 is measured against (the targets)
The baseline's in-corpus retrieval gaps at dense top-6 (context recall) are the concrete surface
Phase-2 must lift — the biggest being **`iam-config-001` (FI-5, cr 0.30)** and the new PDFs
(`rds-tls-*`, `s3-encryption-*`, `eks-pod-attack`, cr 0.15–0.30). Plus:
- **FI-5 recovery** at k≈10 with the metadata filter (the whole point of FI-3).
- **CRAG** behavior on the 3 out-of-corpus questions (should refuse honestly).
- **Latency/cost** the advanced path adds (the other side of the ledger).

## Run plan
1. **Offline:** set all Phase-2 flags on (`ENABLE_HYBRID/RERANK/QUERY_TRANSFORM/CHAIN_OF_NOTE/
   CRAG=true`, `RERANK_CANDIDATE_K=10`, `ENABLE_METADATA_FILTER=true`); re-validate the CRAG
   `0.30` threshold on the new score distribution; run `collect_invoke.py` + `score.py --config
   phase2-final --emit-cloudwatch` on the 61-pair golden.
2. **Online:** operator drives the UI with the **same 13 questions**
   (`../../evals/online/ONLINE-QUESTION-SET.md`) used for Phase-1 (`phase1-final-online`:
   faith 0.955 / rel 0.873 / deflection 23.1%); score `--config phase2-final-online`.
3. **Conclusion:** `PHASE-2-CONCLUSION.md` — offline + online deltas vs baseline, latency/cost,
   FI-5 status at k=10 with FI-3, CRAG on out-of-corpus, and the ship/no-ship verdict.

## Outcome (see `PHASE-2-CONCLUSION.md`)
All-on was a **net negative** (CRAG over-refused; the metadata filter mis-routed and regressed
FI-5). A reduced config — **hybrid + rerank@k=10, everything else OFF** — **beats the Phase-1
baseline on all four quality metrics** (faith 0.983 / rel 0.937 / cp 0.853 / cr 0.861 vs
0.969 / 0.930 / 0.849 / 0.845) with no new deflections, at ~2.4× latency (p95 18.4 s). **That is
the shipped Phase-2 config** and the current live default on `cshub-dev-query`.

## Contents (this folder)
| Doc | What it covers |
|---|---|
| `README.md` | This overview — configs, baseline, run plan. |
| `PHASE-2-CONCLUSION.md` | **The head-to-head result + verdict (start here).** |
| `OFFLINE-RESULTS.md` | Offline per-example detail (all-on net-negative + root causes + wins). |
| `ONLINE-RESULTS.md` | Online run detail (all-on tie + OOC scoring artifact). |
| `_archive-small-corpus/` | Earlier stage-by-stage exploration on the small corpus — rationale only, **not results**. |

## Reference points
- Phase-1 conclusion: [`../phase-1/PHASE-1-CONCLUSION.md`](../phase-1/PHASE-1-CONCLUSION.md)
- Findings that motivate Phase 2: [`../phase-1/FUTURE-IMPROVEMENTS.md`](../phase-1/FUTURE-IMPROVEMENTS.md)
- Chunking & retrieval strategy: [`../phase-1/05-chunking-and-retrieval.md`](../phase-1/05-chunking-and-retrieval.md)
- Frozen online question set (both phases): [`../../evals/online/ONLINE-QUESTION-SET.md`](../../evals/online/ONLINE-QUESTION-SET.md)
- Advanced-RAG flags live in `../../query-service/common/config.py`.

## Per-area phase references
Each code area carries its own "Phase 1 vs Phase 2" block:
- Query service: [`../../query-service/README.md`](../../query-service/README.md)
- Ingestion: [`../../ingestion/README.md`](../../ingestion/README.md)
- Evals: [`../../evals/README.md`](../../evals/README.md)
- Diagrams: [`../../diagrams/README.md`](../../diagrams/README.md)
