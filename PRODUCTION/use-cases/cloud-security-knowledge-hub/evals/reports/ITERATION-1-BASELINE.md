# Iteration 1 — Baseline Evaluation Report (Advanced RAG OFF)

> **System:** Cloud Security Knowledge Hub (production RAG) · account `001961766007` · `us-east-1`
> **Run date:** 2026-09-22 · **Config:** `baseline` (all Phase-3 flags OFF)
> **Purpose:** establish the reference point for the later Phase-3 (advanced RAG) comparison.
> This is an **offline evaluation** (fixed golden set + ground truth, pre-release quality gate):
> it covers **accuracy** (RAGAS-style metrics) and **system performance** (latency captured
> during the golden-set run). It is Iteration 1 of two: baseline now, advanced RAG next.
>
> **Note on terminology:** this is *offline* eval even though answers are collected by calling
> the deployed API (Aurora sits in a private VPC, so the pipeline can't run on a laptop). It is
> NOT *online* eval — we do not sample or score real production traffic. See
> `evals/README.md` and `evals/ONLINE-EVAL-PLAN.md`.

---

## 1. What "baseline" means here

The deployed Phase-1/2 query pipeline, with **no advanced-RAG stages enabled**:

```
question → input guardrail → Titan v2 embed → dense pgvector retrieval (top-6, cosine)
         → Claude Sonnet 4.5 generation (cited) → output guardrail → answer
```

Feature flags `ENABLE_HYBRID`, `ENABLE_RERANK`, `ENABLE_QUERY_TRANSFORM`,
`ENABLE_CHAIN_OF_NOTE`, `ENABLE_CRAG` are all **false**. This is dense-retrieval-only RAG.

**Corpus:** 16 AWS-security documents (27 chunks) spanning S3, EC2/IMDS, RDS (public + IAM
auth), IAM, Lambda, VPC/SG, CloudTrail, KMS, Secrets Manager, Cognito, EKS, EBS snapshots,
SNS/SQS, API Gateway, GuardDuty — each covering configuration/attack/prevention.

**Golden set:** 38 human-reviewed Q&A pairs (`evals/golden/golden.jsonl`), balanced across
14 configuration / 13 attack / 11 prevention, one primary AWS service each.

---

## 2. Methodology

| Aspect | How |
|---|---|
| **Answer collection** | `evals/offline/collect.py` calls the deployed `POST /query` (Cognito-authed) for all 38 golden questions, capturing the pipeline answer, citations, and server latency. Sourcing answers from the deployed API is an implementation detail (Aurora is in a private VPC); the eval is still offline (fixed golden questions, labeled ground truth). |
| **Accuracy scoring** | `evals/offline/score.py` — Bedrock **LLM-as-judge** (Claude Sonnet 4.5) scores each answer 0–1 on the four RAG metrics against the golden ground truth. Used instead of the RAGAS library because the local runtime is Python 3.8 (RAGAS needs ≥3.9); LLM-as-judge is an approved scoring layer in `AI-SDLC-AND-EVALS.md §4`. |
| **Contexts** | The `/query` API returns citation **source ids**, not passage text, so the scorer reconstructs retrieved-context text from the local corpus (`ingestion/samples`) by `doc_id`. |
| **Metrics** | faithfulness, answer relevancy, context precision, context recall (accuracy) + p50/p95/avg latency (performance). |
| **Gate** | `evals/thresholds.json` floors + system ceilings, evaluated by `evals/gate.py`. |

> **Fidelity note:** LLM-as-judge scores are directionally accurate and internally
> consistent (same judge, same prompts across iterations), which is what matters for a
> baseline-vs-Phase-3 **delta**. Absolute values may differ slightly from the RAGAS library.

---

## 3. Headline results

### 3.1 Accuracy (offline, golden set, n=38)

| Metric | Baseline | Gate floor | Status |
|---|---|---|---|
| Faithfulness (groundedness) | **0.984** | 0.80 | ✅ pass |
| Answer relevancy | **0.976** | 0.75 | ✅ pass |
| Context precision | **0.940** | 0.70 | ✅ pass |
| Context recall | **0.947** | 0.70 | ✅ pass |

### 3.2 Performance (latency measured during the golden-set run, n=38)

| Metric | Baseline | Ceiling | Status |
|---|---|---|---|
| Latency p50 | 5,752 ms | — | — |
| Latency p95 | **7,046 ms** | 6,000 ms | 🔴 **fail** |
| Latency avg | 5,611 ms | — | — |
| Errors / 5xx | 0 / 38 | — | ✅ |
| Guardrail false-blocks | 0 / 38 | — | ✅ (after fix — see §5) |

### 3.3 Gate verdict

**FAIL — on performance only.** All four accuracy metrics clear their floors comfortably;
the single failure is **p95 latency (7,046 ms) over the 6,000 ms ceiling**. Root cause is
Claude Sonnet 4.5 generation time plus occasional Lambda cold starts — not a quality problem.
This is a known, expected baseline characteristic and a target for later optimization
(streaming, provisioned concurrency, or a faster generation model).

---

## 4. Breakdown by question type

| Question type | n | Faithfulness | Answer rel. | Context prec. | Context recall |
|---|---|---|---|---|---|
| configuration | 14 | 0.989 | 0.982 | 0.943 | 0.926 |
| attack | 13 | 0.973 | 0.969 | 0.931 | 0.977 |
| prevention | 11 | 0.991 | 0.977 | 0.945 | 0.937 |

**Reading it:** quality is high and even across all three types. Attack questions show
slightly lower faithfulness/precision (they require the model to describe a mechanism, which
is harder to keep perfectly grounded) but the **highest context recall** (attack docs are
distinctive, so dense retrieval finds them reliably). Configuration/prevention have marginally
lower recall — expected, since prevention guidance often spans two chunks of the same doc.

---

## 5. The most important baseline finding (and fix)

**Guardrail false-positive on security-education questions.** The first eval run scored
**0.00 on all 12 attack-type questions**. Investigation (not guesswork — verified with
`apply_guardrail`) showed the Bedrock Guardrail's **MISCONDUCT filter (HIGH)** was **blocking
legitimate questions** like *"How does an SSRF attack against EC2 IMDS work?"* at the input
stage. For a security-education assistant, describing how an attack works **is the core use
case**, so this was a critical false-positive.

**Fix (guardrail v2):** set MISCONDUCT and VIOLENCE input strength to `NONE`, while keeping:
- **PROMPT_ATTACK = HIGH** on input (prompt-injection still blocked — verified),
- HATE / SEXUAL filters,
- output-side PII block for AWS access keys / secret keys / passwords.

Post-fix: **0 / 38 false-blocks**, prompt-injection still blocked. This is the exact
"measure → find the real issue → fix → re-measure" loop the eval process exists for, and it
is baked into the baseline used for the Phase-3 comparison.

---

## 6. Lowest-scoring examples (where Phase-3 could help)

| Example | Avg score | Likely Phase-3 lever |
|---|---|---|
| `iam-attack-001` (privilege escalation) | 0.887 | Chain-of-Note (tighten grounding of the mechanism) |
| `rds-config-001` (IAM DB auth) | 0.913 | Hybrid+RRF / rerank (exact-term recall: "rds-db:connect") |
| `lambda-prevent-001` | 0.917 | Rerank (rank the most on-point chunk first) |
| `ec2-config-001` (IMDSv2 vs v1) | 0.925 | Rerank / query-transform |
| `iam-prevent-001` | 0.925 | Hybrid retrieval (multi-aspect prevention guidance) |

These are the concrete cases to watch when advanced RAG is enabled — they hint that
**hybrid retrieval + reranking** (exact-term precision) and **Chain-of-Note** (grounding on
attack mechanisms) are the highest-leverage Phase-3 stages for this corpus.

---

## 7. System / cost notes

- **Latency:** dominated by Claude Sonnet 4.5 generation (~4–6 s) + retrieval (~0.2 s) +
  cold starts on idle Lambdas (adds ~1–2 s). p95 over ceiling is a generation-time issue.
- **Reliability:** 38/38 answered, 0 API errors, 0 unexpected "I don't know".
- **Cost:** per-query cost was not separately metered in this run (Titan embed is ~$0; Claude
  Sonnet generation is the driver). To be added via Bedrock invocation logging in a later pass;
  the gate's `avg_cost_usd_per_query` ceiling is not yet populated.
- **Observability:** aggregate scores emitted to CloudWatch namespace `CSHub/Eval`
  (Config=`baseline`); dashboard `cshub-dev-hub`.

---

## 8. Reproduce

```bash
# 1) collect pipeline outputs over the golden set (needs a Cognito id_token)
python evals/offline/collect.py --golden evals/golden/golden.jsonl \
  --api <ApiEndpoint> --token <id_token> --out evals/results/records.jsonl

# 2) score accuracy with the Bedrock LLM-judge (+ push to CloudWatch)
AWS_PROFILE=agentcore AWS_REGION=us-east-1 \
python evals/offline/score.py --records evals/results/records.jsonl \
  --config baseline --out evals/results/baseline.json --emit-cloudwatch
```

Artifacts: `evals/results/records.jsonl` (raw pipeline outputs),
`evals/results/baseline.json` (scores + per-example + system).

---

## 9. Baseline summary (the number to beat)

| | Faithfulness | Answer rel. | Context prec. | Context recall | p95 latency |
|---|---|---|---|---|---|
| **Iteration 1 (baseline, dense-only)** | 0.984 | 0.976 | 0.940 | 0.947 | 7,046 ms |

**Phase-3 goal:** enable advanced stages one at a time (hybrid+RRF → rerank → query-transform
→ Chain-of-Note → CRAG), re-run this exact harness, and record the **delta per stage**. Keep a
stage only if its accuracy gain justifies its latency/cost. Iteration 2 will report those
deltas against this table.

> Because accuracy is already very high on this small, clean corpus, the clearest Phase-3
> wins will likely show up on (a) the lowest-scoring examples in §6, (b) context precision/
> recall as the corpus grows, and (c) latency if a lighter path is chosen. A realistic
> expectation: advanced RAG's value becomes visible as corpus size and query difficulty
> increase — this baseline is the honest starting line to measure that from.
