# Phase-2 Online Results (`phase2-final-online`)

Live UI run of the **same 13 questions** used for Phase-1 (`evals/online/ONLINE-QUESTION-SET.md`),
with the Phase-2 all-on configuration (hybrid + rerank k=10 + query-transform + Chain-of-Note +
CRAG + metadata filter). Scored from FI-6 trace spans (`--from-traces`), **13/13 on real
retrieved context**.

## Headline (all 13)
| Metric | Phase-1 (`phase1-final-online`) | Phase-2 (`phase2-final-online`) |
|---|---|---|
| Faithfulness | 0.955 | **0.977** |
| Answer relevancy | 0.873 | 0.727 |
| Deflection rate | 23.1% (3/13, all OOC) | 23.1% (3/13, all OOC) |
| Guardrail-block | 0% | 0% |
| Grounded on real context | 13/13 | 13/13 |

## The honest read — split in-corpus vs out-of-corpus
The all-13 relevancy gap (0.873 → 0.727) is **entirely an OOC refusal-scoring artifact**, not a
quality regression. Both phases correctly refused all 3 out-of-corpus questions (Azure WAF, GCP
encryption, Texas↔NYC distance) with faithfulness 1.00; the LLM-judge just scored those refusals'
"relevance" differently run-to-run (Phase-1 OOC rel 0.60, Phase-2 OOC rel 0.00). Splitting it out:

| | Phase-1 in-corpus (10) | Phase-2 in-corpus (10) |
|---|---|---|
| Faithfulness | 0.942 | **0.970** |
| Answer relevancy | 0.955 | 0.945 |

**On the 10 in-corpus questions, Phase-2 ≈ Phase-1** — marginally higher faithfulness, marginally
lower relevancy, both within judge noise. Online, the two configurations are a quality tie.

## Latency (the real difference)
Phase-2 answers took **~15–20 s** each (all-on: hybrid + 3× query-transform sub-queries + rerank
+ Chain-of-Note + CRAG grade) vs Phase-1's ~5–8 s — roughly **2–3× slower**, consistent with the
offline p95 (7.6 s → 23.5 s).

## Why online didn't show the offline over-refusal
Offline, Phase-2 newly deflected 7 in-corpus golden questions (CRAG over-refusing + metadata-filter
mis-routing). Online, **all 10 in-corpus questions answered** — the broader, multi-service live
questions (WAF, GuardDuty, Security Hub, incident response) retrieve a richer pool that clears
CRAG's 0.30 bar and doesn't mis-route the single-service metadata filter as the narrower golden
pairs do. The offline golden set is the more sensitive probe; it surfaced the regression the
broad online questions masked. Both are recorded.

## Verdict (online)
Phase-2 all-on is a **quality tie online at ~2–3× latency** — no online win to justify the cost.
Combined with the offline **net-negative** (relevancy/recall down, FI-5 regressed, CRAG
over-refuses), the all-on configuration as tuned (CRAG 0.30 + hard metadata filter) is **not
ship-worthy**. Next: a tuning pass (soften CRAG, soften/boost metadata routing, keep
rerank+hybrid) re-measured against the same baseline. See `PHASE-2-CONCLUSION.md`.

> Results file: `../../evals/results/phase2-final-online.json`. Metrics → CloudWatch
> `CSHub/OnlineEval` (dimension `Config=phase2-final-online`).
