# Phase-1 Baseline Evaluation Report (Advanced RAG OFF) — canonical

> **System:** Cloud Security Knowledge Hub (production RAG) · account `001961766007` · `us-east-1`
> **Run date:** 2026-09-28 · **Config:** `phase1-final` (all advanced-RAG flags OFF)
> **Purpose:** the single reference point for the Phase-2 (advanced RAG) comparison.
>
> This is an **offline evaluation** — fixed golden set + ground truth, run as a pre-release
> quality gate. It covers **accuracy** (RAGAS-style metrics via Bedrock LLM-as-judge) and
> **system performance** (latency captured during the run). Answers are collected by invoking
> the deployed query Lambda directly (Aurora is in a private VPC, so the pipeline can't run on a
> laptop); it is still offline (fixed golden questions, labeled ground truth), not online eval.
>
> **Scope note:** earlier exploratory runs on a smaller corpus are superseded. All numbers here
> are from the full **30-doc / 534-chunk** corpus with the **61-pair** golden set — the only
> legitimate, comprehensive baseline.

---

## 1. What "baseline" means here

The deployed query pipeline with **no advanced-RAG stages enabled**:

```
question → input guardrail → Titan v2 embed → dense pgvector retrieval (top-6, cosine)
         → Claude Sonnet 4.5 generation (cited) → output guardrail → answer
```

Flags `ENABLE_HYBRID`, `ENABLE_RERANK`, `ENABLE_QUERY_TRANSFORM`, `ENABLE_CHAIN_OF_NOTE`,
`ENABLE_CRAG`, `ENABLE_METADATA_FILTER` are all **false**. Dense-retrieval-only RAG. Tracing
(FI-6 OTel spans) is on.

**Corpus:** 30 AWS-security documents / 534 chunks / 17 services — 18 markdown security notes
plus 12 PDFs (AWS Security Reference Architecture; S3/RDS encryption; data-protection; EKS pod +
best-practices; RDS SSL/TLS; Lambda MicroVMs; IAM-with-a-service).

**Golden set:** 61 human-reviewed Q&A pairs (`evals/golden/golden.jsonl`) — 24 configuration /
19 attack / 18 prevention, 18 distinct services, all `reviewed_by=human`, including 3
out-of-corpus (OOC) pairs.

---

## 2. Methodology

| Aspect | How |
|---|---|
| **Answer collection** | `evals/offline/collect_invoke.py` invokes the deployed `cshub-dev-query` Lambda for all 61 golden questions, capturing answer, citations, `request_id`, and server latency. |
| **Accuracy scoring** | `evals/offline/score.py` — Bedrock **LLM-as-judge** (Claude Sonnet 4.5) scores each answer 0–1 on the four RAG metrics. Used instead of RAGAS because the local runtime is Python 3.8 (RAGAS needs ≥3.9); LLM-as-judge is an approved layer in `AI-SDLC-AND-EVALS.md §4`. |
| **Contexts (FI-4 fixed)** | The scorer joins each record's `request_id` to its **FI-6 trace span** (`aws/spans`, `cshub.retrieved_context`) and judges against the **real retrieved passage text**. This run: **61/61 scored on `trace_context`**, zero local-sample fallback. |
| **Metrics** | faithfulness, answer relevancy, context precision, context recall (accuracy) + p50/p95/avg latency (performance). |
| **Gate** | `evals/thresholds.json` floors, evaluated by `evals/gate.py`. |

---

## 3. Headline results (config `phase1-final`, n=61)

| Metric | All 61 (CloudWatch) | **In-corpus 58 (headline)** | OOC 3 | Gate floor | Status |
|---|---|---|---|---|---|
| Faithfulness | 0.938 | **0.969** | 0.33 | 0.80 | ✅ pass |
| Answer relevancy | 0.884 | **0.930** | 0.00 | 0.75 | ✅ pass |
| Context precision | 0.811 | **0.849** | 0.07 | 0.70 | ✅ pass |
| Context recall | 0.818 | **0.845** | 0.30 | 0.70 | ✅ pass |

**Performance:** p95 **7,591 ms** · avg **5,843 ms** · 0 errors. p95 exceeds the 6,000 ms
ceiling — a Claude generation-time characteristic of the dense baseline, not a quality issue.

**Collection:** 56 answered · 5 IDK · 0 errors.

> **Headline = in-corpus 58** (faith 0.969 / rel 0.930 / cp 0.849 / cr 0.845). The all-61
> aggregate is dragged down by the 3 OOC pairs; see §5.

---

## 4. Breakdown by question type (in-corpus)

| Question type | Faithfulness | Answer rel. | Context prec. | Context recall |
|---|---|---|---|---|
| configuration | high, even | high | mixed (new PDFs lower) | mixed (new PDFs lower) |
| attack | high | high | high | mixed |
| prevention | high | high | mixed | mixed |

Faithfulness is uniformly high (~0.97). The variation is in **context precision/recall**, driven
by the new multi-topic PDFs and the large multi-service SRA doc — exactly the retrieval surface
Phase-2 targets (see §6).

---

## 5. The OOC scoring artifact (FI-7) — read before comparing phases

The 3 out-of-corpus questions (Azure, GCP, bare-metal kubeadm) returned **correct honest
refusals** ("I don't have enough information … the knowledge base is about AWS …"). That is the
desired behavior. But the **offline** judge scored them near-zero, because its faithfulness
prompt asks "is every claim supported by the CONTEXT" and its relevancy prompt asks "does the
answer address the QUESTION" — an honest refusal has no context-grounded claims and doesn't
"address" an Azure question. The **online** scorer already rewards honest refusals.

Consequences:
- **Report in-corpus (58) as the true quality number** for both phases.
- Track the 3 OOC pairs separately as a **refusal-correctness** check (did it refuse? yes/no).
- Phase-2's CRAG also refuses on OOC, so scoring OOC with this judge in both phases would cancel
  out — but the honest, apples-to-apples quality number is in-corpus.

Logged as **FI-7**. Fix is a prompt tweak in `score.py`; deferred so Phase-1 and Phase-2 use an
identical (if imperfect) scorer and the delta stays fair.

---

## 6. In-corpus retrieval gaps at dense top-6 (the Phase-2 targets)

| Example | ctx-recall | ctx-prec | ans-rel | Likely Phase-2 lever |
|---|---|---|---|---|
| `rds-tls-attack-001` | 0.15 | 0.10 | 0.65 | rerank + metadata filter (right RDS doc) |
| `s3-encryption-prevent-001` | 0.20 | 0.10 | 0.20 | rerank (was collected as IDK) |
| **`iam-config-001`** (FI-5) | **0.30** | 0.65 | 1.00 | metadata filter (IAM) + rerank@k=10 |
| `sra-prevent-001` | 0.30 | 0.75 | 0.85 | rerank (large multi-service SRA doc) |
| `rds-tls-prevent-001` | 0.30 | 0.75 | 0.95 | rerank + metadata filter |
| `eks-pod-attack-001` | 0.30 | 0.85 | 0.92 | rerank |
| `s3-encryption-config-001` | 0.65 | 0.85 | 0.95 | rerank |
| `apigw-config-001` | 0.75 | 0.65 | 0.70 | rerank (was collected as IDK) |

**`iam-config-001` is the long-standing FI-5 case:** it answers well (ans-rel 1.00) but context
recall is only 0.30 at dense top-6 — the metadata filter (now that FI-3 tags chunks per-service)
+ rerank@k=10 are measured against exactly this in Stage 2.

---

## 7. System / cost notes

- **Latency:** dominated by Claude Sonnet 4.5 generation (~4–6 s) + retrieval (~0.2 s) + cold
  starts. p95 over ceiling is a generation-time issue, not quality.
- **Reliability:** 56/61 answered, 5 correct IDK (incl. 3 OOC + 2 in-corpus recall gaps), 0 errors.
- **Cost:** per-query cost not separately metered this run (Titan embed ~$0; Claude generation is
  the driver).
- **Observability:** aggregate scores emitted to CloudWatch `CSHub/Eval` (Config=`phase1-final`).

---

## 8. Reproduce

```bash
# 1) collect pipeline outputs over the golden set (direct Lambda invoke, all flags OFF)
AWS_PAGER="" AWS_PROFILE=agentcore AWS_REGION=us-east-1 \
python3 evals/offline/collect_invoke.py --golden evals/golden/golden.jsonl \
  --function cshub-dev-query --out evals/results/phase1-final-records.jsonl

# 2) score with the Bedrock LLM-judge, joining real context from FI-6 spans (+ CloudWatch)
AWS_PAGER="" AWS_PROFILE=agentcore AWS_REGION=us-east-1 \
python3 evals/offline/score.py --records evals/results/phase1-final-records.jsonl \
  --config phase1-final --out evals/results/phase1-final.json --minutes 40 --emit-cloudwatch
```

Artifacts: `evals/results/phase1-final-records.jsonl`, `evals/results/phase1-final.json`.

---

## 9. Baseline summary (the number to beat)

| | Faithfulness | Answer rel. | Context prec. | Context recall | p95 latency |
|---|---|---|---|---|---|
| **Phase-1 baseline (dense-only, in-corpus 58)** | 0.969 | 0.930 | 0.849 | 0.845 | 7,591 ms |
| **Phase-1 baseline (all 61 incl. OOC)** | 0.938 | 0.884 | 0.811 | 0.818 | 7,591 ms |

**Phase-2 goal:** enable all advanced stages at once (hybrid + rerank@k=10 + query-transform +
Chain-of-Note + CRAG + FI-3 metadata filter), re-run this exact harness on the same corpus and
golden set, and record the **delta** — especially context precision/recall on the §6 targets and
`iam-config-001` (FI-5), while quantifying the latency/cost the advanced path adds.

> Because faithfulness is already high, the clearest Phase-2 wins should show up in **context
> precision/recall** on the new-PDF + multi-service surfaces in §6, in **FI-5 recovery**, and in
> CRAG behavior on out-of-corpus queries. Latency is the cost side of the ledger.
