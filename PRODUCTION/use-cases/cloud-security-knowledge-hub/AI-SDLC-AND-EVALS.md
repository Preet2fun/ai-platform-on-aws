# AI-SDLC & Evaluation Plan — Cloud Security Knowledge Hub

Every RAG component is independently **testable** and **measured**, so you can see the value
of each stage as you add it (Phase 1 baseline → Phase 2 incremental). This is the engine that
lets you "continuously measure quality and performance and release improvements over time."

> **This document is the plan (design intent). For what actually happened in the Phase-1 run —
> real numbers, deviations, and findings — see [§9 As-run reality](#9-as-run-reality-phase-1)
> and `docs/phase-1/`.** Sections 1–8 remain the forward-looking design; §9 reconciles them
> against the executed run and is the source of truth where they differ.

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

> **Implemented (as-run):** the eval harness lives in `evals/` — but the runner is split into
> `offline/collect.py` (query the live API for the golden set) + `offline/score.py`
> (**LLM-as-judge via Bedrock**, not the RAGAS library — see §9 for why), plus
> `online/score_online.py` (online eval on live traffic). Shared logic is `lib/gate.py`
> (quality gate) and `lib/report.py` (aggregate + baseline-vs-candidate delta), with
> `thresholds.json` and `golden/`. Observability (dashboard, alarms, budget) is
> `infra/05-observability.yaml`. **The CI eval-gate workflow is designed but not yet wired**
> (§9).

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

---

## 9. As-run reality (Phase 1)

This section reconciles the plan above with what the Phase-1 run actually did. Where they
differ, **this section wins.** Full detail with real numbers is in `docs/phase-1/`.

### 9.1 What ran vs what was planned

| Area | Plan (§1–8) | As-run (Phase 1) | Why the difference |
|---|---|---|---|
| Offline scorer | RAGAS library | **LLM-as-judge via Claude on Bedrock**, computing the same 4 metrics on 0–1 | RAGAS 0.2+ needs Python ≥3.9 + a heavy dep tree; the runtime here is py3.8. LLM-judge was already a listed layer (§4) and gives comparable, gate-feedable numbers. |
| Runner shape | single `run_eval.py` | split `offline/collect.py` + `offline/score.py` + `online/score_online.py` | collect (query the live API) and score (judge) have different runtimes/creds; splitting lets us re-score without re-querying. |
| Scoring concurrency | (unspecified) | **sequential**, with backoff | macOS py3.8 threads segfault on the boto3 path + Bedrock throttles under parallel judge calls. |
| Golden set size | ~100–200 pairs (v1 target) | **42 pairs** (17 config / 13 attack / 12 prevention) | Phase-1 baseline set; grows via the flywheel (§8). Enough to gate, not yet the v1 target. |
| Online eval | continuous EventBridge sampler + feedback UI + drift alarms | **manual 7-question run** through the online scorer; metrics emitted to `CSHub/OnlineEval` | the sampler/feedback/alarm infra (Steps 2/4/5 of `evals/ONLINE-EVAL-PLAN.md`) is deferred; the scoring logic and metric path are proven. |
| Q&A capture | Bedrock invocation logging | **structured `CSHUB_QA` log line** in the query Lambda | simpler, zero-latency, already in the request path; the online-eval prerequisite. |
| Trace/content capture | (not planned in Phase 1) | **OpenTelemetry GenAI spans (FI-6)** — `rag.query` spans with question + retrieved chunk text + answer, exported to CloudWatch Transaction Search | added mid-run so online eval can score against **real retrieved context** (closes the online half of FI-4); the trace-eval foundation Phase 2 builds on. |
| Large-PDF ingestion | Fargate branch for big docs | **not built** — large PDF (KMS, 2,213 chunks) exceeded the 900s Lambda path | Fargate deferred (FI-2); SRA PDF (307 chunks) ingested fine on Lambda. |
| CI eval-gate | GitHub Actions gate live | **not wired yet** | gate logic (`lib/gate.py` + `thresholds.json`) exists and runs locally; CI hookup pending. |

### 9.2 Phase-1 baseline numbers (the reference point §5 asks for)

**Offline (golden-set gate, `phase1-post-sra`, 37 non-SRA comparable):**
faithfulness **0.915** · answer_relevancy **0.959** · context_precision **0.932** ·
context_recall **0.938** · p95 latency **7,506 ms**.
(Raw all-42 numbers in CloudWatch are lower — depressed by the FI-4 scorer artifact; see
`docs/phase-1/02-offline-eval.md`.)

**Online (live traffic, `phase1-online`, 7 questions):**
faithfulness **0.871** · answer_relevancy **0.921** · deflection **14.3%** ·
guardrail-block **0%** · citation coverage **100%** · avg latency **5,292 ms** ·
p95 **6,846 ms**. See `docs/phase-1/03-online-testing.md`.

These are the **reference points** every Phase-2 change is measured against.

### 9.3 Findings the run surfaced (drive Phase 2)

Pipeline findings are tracked in `docs/phase-1/FUTURE-IMPROVEMENTS.md` (FI-1…FI-5); the
headline for the eval story:

- **FI-4 (scorer):** the offline scorer reconstructs context from **local sample files**, so
  documents that live only in S3 (the SRA PDF) score a **false 0.00**. **Online half now fixed
  via FI-6** — online faithfulness is judged against the real retrieved passage text carried on
  the trace span. **Offline half still pending** (the golden-set batch scorer must capture
  retrieved passages the same way).
- **FI-6 (trace-eval, DONE):** the query Lambda now emits **OpenTelemetry GenAI spans**
  (question + retrieved chunk text + answer) to CloudWatch Transaction Search;
  `evals/online/score_online.py --from-traces` scores faithfulness against real retrieved
  context (verified 6/6 grounded). Prerequisite: Transaction Search enabled + a logs resource
  policy (one-time, account level). This is the per-conversation, retrieved-context-grounded
  measurement foundation Phase 2's advanced-RAG A/B tests rely on.
- **FI-5 (genuine regression):** `iam-config-001` passed ~1.0 at baseline and now deflects,
  because 307 SRA IAM-heavy chunks crowd the top-6 of **dense-only** retrieval. This is the
  concrete, measured motivation for **Phase 2 hybrid + rerank + larger top-K** — exactly the
  "measure what each stage contributes" loop this plan is built around.

Observability gaps (visibility, not correctness) are in `docs/phase-1/04-observability.md` §D.6.

### 9.4 Milestone status (as-run)

| Phase | Plan status | As-run |
|---|---|---|
| P0 Foundation | — | ✅ deployed (8 `cshub-dev-*` stacks) |
| P1 Ingestion | text+PDF | ✅ text + native-text PDF on Lambda; ⏳ large-PDF Fargate branch (FI-2) |
| P2 Baseline online | dense + guardrails + gen + UI | ✅ live (UI, Cognito, API, dense retrieval, Claude, guardrails) |
| P3 Advanced RAG | hybrid→rerank→transform→CoN→CRAG | ⏳ Phase 2 (flags exist, all off) — FI-5 is the trigger |
| P4 Golden set + continuous eval | 100–200 pairs, CI gate | ⏳ 42 pairs, local gate; CI + online sampler pending |
| P5 Hardening | least-priv, cost, video | ⏳ ongoing; video path not started |
