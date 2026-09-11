# AI-SDLC & Evaluation Plan — Cloud Security Knowledge Hub

Every RAG component is independently **testable** and **measured**, so you can see the value
of each stage as you add it (Phase 1 baseline → Phase 2 incremental). This is the engine that
lets you "continuously measure quality and performance and release improvements over time."

---

## 1. The AI-SDLC loop

```
Data → Ingest → Index → Retrieve → (Re-rank) → (Verify) → Generate → Evaluate → Observe → Improve
                                   └────────────── measured at every stage ──────────────┘
```
Each release goes: **change one stage → run offline eval on the golden set → compare delta →
gate in CI → deploy → observe online → feed findings back.**

---

## 2. Golden dataset (the measurement backbone)

- A labeled set of **question → ideal answer → source chunk(s)** across the three question
  types: **configuration**, **attack**, **prevention** (e.g. "How to secure an S3 bucket?",
  "How does IMDS SSRF work on EC2?", "How to prevent public RDS exposure?").
- **Built later, together:** once the corpus is loaded, I'll help you auto-generate candidate
  Q&A pairs from the documents (LLM-generated, human-reviewed) — a standard bootstrapping
  approach. Target ~100–200 pairs for v1, growing over time.
- Stored in `evals/golden/` and versioned in git so eval runs are comparable across releases.

---

## 3. Per-component tests + eval metrics

### Ingestion (offline)
- **Tests:** parsing succeeds per file type; chunk count within expected range; no empty/oversized
  chunks; every chunk has required metadata; embeddings have correct dimension and are non-null.
- **Metrics:** corpus coverage (docs → chunks), chunk-size distribution, embedding failure rate.
- **Gate:** ingestion manifest must pass before the index is promoted.

### Retrieval
- **Metrics (RAGAS + custom):** Context Precision, Context Recall, Hit Rate@K, MRR, NDCG.
- **What each Phase-2 step should move:**
  - Hybrid + RRF → **Context Recall**, Hit Rate@K (exact-term queries).
  - Cohere Rerank → **Context Precision**, MRR/NDCG (right chunk first).
  - Query transformation → **Context Recall** on the hard-query subset (ambiguous/multi-hop).

### Generation
- **Metrics:** Faithfulness/Groundedness, Answer Relevance, Correctness (vs golden), hallucination rate.
- **What each step should move:**
  - Chain-of-Note → **Faithfulness** up, hallucination down, more correct "I don't know".
  - CRAG → **Correctness** on out-of-corpus/stale queries (via refine/fallback).

### System
- **Metrics:** latency P50/P95 per stage (X-Ray), cost/query, throughput, error rate.
- **Guardrail metrics:** input blocks, output suppressions, false-block rate.

---

## 4. Eval tooling (AWS-ecosystem + industry standard)

| Layer | Tool | Use |
|---|---|---|
| Offline pipeline eval | **RAGAS** | Context precision/recall, faithfulness, answer relevancy on the golden set |
| LLM-as-judge | **Claude via Bedrock** | Qualitative scoring where no ground truth; cheap large-scale scoring |
| Managed eval | **Amazon Bedrock Evaluations** | Model/RAG evaluation jobs, results to CloudWatch/S3 |
| Online metrics | **CloudWatch** dashboards + alarms | Latency, cost, quality signals, guardrail events |
| Tracing | **AWS X-Ray** | Per-stage latency attribution across the online pipeline |
| Invocation capture | **Bedrock model invocation logging** | Store prompts/responses for audit + offline scoring |

> **Implemented (P5):** the eval harness lives in `evals/` — `run_eval.py` (RAGAS runner),
> `gate.py` (quality gate: floors + max-regression + system ceilings), `report.py`
> (baseline-vs-candidate delta), `thresholds.json`, and `golden/` (schema, seed, LLM
> generator). CI gate: `.github/workflows/eval-gate.yml`. Observability (dashboard, alarms,
> budget) is `infra/05-observability.yaml`.

---

## 5. Phase-by-phase measurement plan

### Phase 1 — Baseline
- Ship: input guardrails → dense retrieval (pgvector) → Claude generation + citations → output guardrails.
- Establish baseline scores on the golden set + baseline latency/cost.
- **This is the reference point for everything after.**

### Phase 2 — Add one stage at a time (feature-flagged)
For each of 2.1–2.5 (hybrid+RRF, rerank, query-transform, Chain-of-Note, CRAG):
1. Enable the flag in a test environment.
2. Run the full RAGAS suite on the golden set.
3. Record the **delta** vs the previous configuration (quality) and the **cost/latency delta**.
4. **Keep it only if the quality gain justifies the added latency/cost.** Document the decision.

Output: an evidence table showing exactly what each advanced RAG technique contributed for
*your* corpus and query mix — the "need, significance, and impact" you want to understand.

---

## 6. CI/CD (GitHub Actions)

```
push / PR
  → lint + unit tests (per component)
  → build Lambda/Fargate artifacts
  → deploy to dev (CloudFormation change sets via GitHub OIDC role)
  → run RAGAS eval on golden set  ── quality gate (fail if regression beyond threshold)
  → manual approval → deploy to prod (CloudFormation)
  → post-deploy smoke test + online metric check
```
- **GitHub OIDC** federated role (no long-lived AWS keys in CI).
- **Quality gate:** a PR that drops faithfulness/context-recall below threshold fails the build.
- Infra changes deploy via **CloudFormation change sets** (review before apply).

---

## 7. Milestones

| Phase | Deliverable | Exit criteria |
|---|---|---|
| **P0 Foundation** | VPC, Aurora+pgvector, S3, KMS, Secrets, CFN skeleton, CI/CD OIDC | `cfn deploy` works; pgvector schema bootstrapped |
| **P1 Ingestion (text+PDF)** | Step Functions pipeline; first corpus indexed; ingestion tests | Corpus searchable; manifest passes |
| **P2 Baseline online** | Lambda query service, guardrails, dense retrieval, Claude gen, UI, Cognito, CloudFront/WAF | Baseline eval scores recorded |
| **P3 Advanced RAG** | Hybrid+RRF → rerank → query-transform → Chain-of-Note → CRAG, each measured | Evidence table of per-stage deltas |
| **P4 Golden set + continuous eval** | ~100–200 labeled pairs; RAGAS gate in CI; dashboards | Regression gate live; dashboards green |
| **P5 Hardening + (later) video** | Least-privilege review, cost tuning, Transcribe ingestion branch | Prod-ready; video path added |

---

## 8. Continuous improvement (post-v1)

- Expand the golden set from real user queries (mined from logs, human-labeled).
- Add multi-representation indexing / RAPTOR and measure the delta (per `AI-PLATFORM/rag §4`).
- Add long-term memory for personalization if the product needs it (per `AI-PLATFORM/memory`).
- Extend the corpus beyond AWS to other clouds when ready (the pipeline is cloud-agnostic).
