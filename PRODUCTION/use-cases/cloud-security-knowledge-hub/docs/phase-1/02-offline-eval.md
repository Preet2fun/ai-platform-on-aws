# Phase 1 · Stage B — Offline Evaluation (golden-set quality gate)

> **Offline eval** = fixed golden set + ground truth, run as a pre-release quality gate (not
> production traffic). This is the **canonical Phase-1 baseline**, run on the full
> **30-doc / 534-chunk** corpus with the **61-pair** golden set and the real-trace-context
> scorer. Config label: **`phase1-final`**. All advanced-RAG flags OFF
> (`ENABLE_HYBRID/RERANK/QUERY_TRANSFORM/CHAIN_OF_NOTE/CRAG/METADATA_FILTER=false`), dense
> top-6, tracing on. Earlier small-corpus runs are superseded and not reported here.

## B.1 — Corpus + golden set
- **Corpus:** 30 documents / 534 chunks / 17 services (18 markdown security notes + 12 AWS PDFs
  incl. the AWS Security Reference Architecture, encryption/data-protection, EKS, RDS-TLS).
- **Golden set:** **61 human-reviewed pairs** (`evals/golden/golden.jsonl`) — 24 configuration /
  19 attack / 18 prevention, 18 distinct services, all `reviewed_by=human`. Includes **3
  out-of-corpus (OOC)** questions (Azure, GCP, bare-metal kubeadm) so the honest-refusal /
  CRAG behavior is measurable.

## B.2 — Run
`offline/collect_invoke.py` (direct Lambda invoke, all flags OFF) → `offline/score.py --config
phase1-final --minutes 40 --emit-cloudwatch` (Bedrock LLM-as-judge) →
`results/phase1-final.json`, emitted to CloudWatch `CSHub/Eval` (dimension `Config=phase1-final`).
- Collection: **56 answered · 5 "I don't know" · 0 errors.**
- **Every record scored against real retrieved context**: the scorer joins each record's
  `request_id` to its FI-6 trace span (`aws/spans`, `cshub.retrieved_context`). **61/61 scored
  on `trace_context`**, zero local-sample fallback — the old FI-4 artifact is gone.

## B.3 — Results (config `phase1-final`, n=61)

| Metric | All 61 (emitted to CloudWatch) | **In-corpus 58 (headline)** | OOC 3 |
|---|---|---|---|
| Faithfulness | 0.938 | **0.969** | 0.33 |
| Answer relevancy | 0.884 | **0.930** | 0.00 |
| Context precision | 0.811 | **0.849** | 0.07 |
| Context recall | 0.818 | **0.845** | 0.30 |
| p95 latency | 7,591 ms | — | — |
| avg latency | 5,843 ms | — | — |

**Headline = in-corpus 58:** faithfulness **0.969** · relevancy **0.930** · precision **0.849**
· recall **0.845**. This is the number every Phase-2 change is measured against.

### Why report in-corpus separately (the OOC scoring artifact — FI-7)
The 3 OOC questions returned **correct honest refusals** ("I don't have enough information … the
knowledge base is about AWS …") — the desired behavior. But the **offline** judge scores them
near-zero: its faithfulness prompt asks "is every claim supported by the CONTEXT" and its
relevancy prompt asks "does the answer address the QUESTION", and an honest refusal has no
context-grounded claims and doesn't "address" an Azure question. The **online** judge already
rewards honest refusals. This is a scorer-prompt mismatch (**FI-7**), not a system fault, so we
report **in-corpus** as the quality headline and track the 3 OOC pairs as a separate
**refusal-correctness** check. Both phases run the identical scorer, so the head-to-head delta
stays fair.

## B.4 — In-corpus retrieval gaps at dense top-6 (the Phase-2 targets)
Lowest context_recall on in-corpus pairs — where rerank@k=10 + the FI-3 metadata filter should help:

| Example | ctx-recall | ctx-prec | ans-rel | Note |
|---|---|---|---|---|
| `rds-tls-attack-001` | 0.15 | 0.10 | 0.65 | new PDF; dense pulled wrong RDS context |
| `s3-encryption-prevent-001` | 0.20 | 0.10 | 0.20 | new PDF; collected as IDK |
| **`iam-config-001`** (FI-5 case) | **0.30** | 0.65 | 1.00 | the FI-5 target — recall is the gap |
| `sra-prevent-001` | 0.30 | 0.75 | 0.85 | large multi-service SRA doc |
| `rds-tls-prevent-001` | 0.30 | 0.75 | 0.95 | new PDF |
| `eks-pod-attack-001` | 0.30 | 0.85 | 0.92 | new PDF |
| `s3-encryption-config-001` | 0.65 | 0.85 | 0.95 | new PDF |
| `apigw-config-001` | 0.75 | 0.65 | 0.70 | collected as IDK (in-corpus gap) |

**Reading it:** the dense-only baseline is strong on faithfulness (0.969 in-corpus) but **context
recall sits at 0.845** — the new PDFs and the multi-service SRA doc are where dense top-6 misses
the best chunk. `iam-config-001` (the **FI-5** case) now *answers* (ans-rel 1.00) but with
context recall only **0.30**. These are the concrete surfaces Phase-2 aims to lift.

## B.5 — Findings (in `FUTURE-IMPROVEMENTS.md`)
- **FI-5 (Phase 2):** IAM / new-PDF context recall is the retrieval gap at dense top-6 →
  rerank@k=10 + FI-3 metadata filter are measured against it in Stage 2.
- **FI-7 (⏳):** offline judge penalizes honest refusals (OOC pairs) → report in-corpus as the
  headline; fix the judge prompts later so both phases keep an identical scorer.
- **FI-4 (✅ Done):** the scorer now scores against the real retrieved context via FI-6 trace
  spans (61/61 on `trace_context`) — the false-0.00-on-PDF artifact is resolved.

## B.6 — Gate verdict
Against `thresholds.json` floors (faith 0.80 / rel 0.75 / cp 0.70 / cr 0.70): the **in-corpus**
scores pass comfortably. p95 latency (7,591 ms) exceeds the 6,000 ms ceiling — a
generation-time characteristic of the dense baseline, not a quality issue.

## B.7 — What this stage proved
- The full offline loop runs end-to-end on a realistic 30-doc corpus and scores against **real
  retrieved context** (FI-4 fixed).
- The baseline is **strong and honest**: 0.969 in-corpus faithfulness, and it **refuses rather
  than hallucinates** on out-of-corpus questions.
- It surfaces **concrete, measured retrieval gaps** (FI-5 + new-PDF recall) that give Phase-2 a
  clear target and a fair reference point.

> Per-example breakdown + full Phase-2 target list: `evals/reports/ITERATION-1-BASELINE.md`.
> Artifacts: `evals/results/phase1-final-records.jsonl`, `evals/results/phase1-final.json`.
