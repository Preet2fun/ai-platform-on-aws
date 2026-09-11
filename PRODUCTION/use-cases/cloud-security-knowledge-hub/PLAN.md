# Cloud Security Knowledge Hub — Production RAG Plan

> **Use case:** a customer-facing assistant answering cloud-security questions — how an AWS
> service is configured securely, how a given attack happens on AWS, and how to prevent it —
> grounded in curated AWS security knowledge.
> **Built on:** the `AI-PLATFORM/` component standards (rag, guardrails, memory, runtime).
> This is a PRODUCTION use case: it *uses* the standards, it doesn't redefine them.
> **v1 scope:** AWS security knowledge · single region `us-east-1` · ~20 users · ~$300/mo.

---

## 0. Decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| Architecture | **Custom advanced RAG (Path 2)** | Full control of hybrid search, re-ranking, CRAG; matches `AI-PLATFORM/rag`. |
| Vector store | **Aurora PostgreSQL Serverless v2 + pgvector** | Real hybrid search (pgvector dense + Postgres full-text sparse) that scales down to fit budget. |
| Generation model | **Anthropic Claude Sonnet** (Bedrock) | Already enabled; strong reasoning + citations. |
| Embeddings | **Amazon Titan Text Embeddings v2** (Bedrock) | Native, cheap, 1024-dim. |
| Re-ranker | **Cohere Rerank** (Bedrock) — *Phase 2* | Managed cross-encoder; no infra. |
| IaC | **Raw CloudFormation (YAML)**, nested stacks | Per your choice. |
| Query compute | **AWS Lambda** (see §6 pros/cons) | Cheap, scale-to-zero, fits 20 users. |
| Region / account | `us-east-1`, same account `001961766007` | Reuse account-level services; app resources new. |
| CI/CD | **GitHub → GitHub Actions → CloudFormation** | Per your toolchain. |
| Eval | **RAGAS + Bedrock evaluation + CloudWatch** | Offline gate + online monitoring. |
| **Offline v1** | **Text + PDF only** | Video/Transcribe deferred to a later phase. |
| **Online delivery** | **Two phases (baseline → incremental)** | Measure each advanced stage's individual value. |

---

## 1. What the system does (functional)

Users ask natural-language questions such as:
- "How do I securely configure an S3 bucket?" (configuration)
- "How does an S3 public-exposure / bucket-takeover attack happen on AWS?" (attack)
- "How do I prevent SSRF against EC2 IMDS?" (prevention)

The system retrieves the most relevant, trusted passages from the curated AWS security
corpus, (Phase 2) re-ranks and verifies them, and generates a grounded, **cited** answer —
or says "I don't have enough information" rather than guessing (critical for security).

---

## 2. Offline pipeline (ingestion / indexing) — v1: text + PDF

Batch, asynchronous, not user-facing. Runs when content is added.

```
Source content in S3 (text, PDF)                         [video → later phase]
  → EventBridge (S3 upload) → Step Functions
      → Text extraction:
          • native PDF/text → parser (Lambda)
          • scanned/complex PDF → Amazon Textract
      → Clean & normalize (Lambda)
      → Structure-aware chunking + metadata               (service, topic, source,
        (Lambda or Fargate for large batches)              version, sensitivity)
      → Embed chunks — Titan Text Embeddings v2 (Bedrock)
      → Upsert into Aurora:
          • pgvector column (dense vector)                 [enables dense ANN]
          • tsvector column + GIN index (full-text)        [enables sparse search, Phase 2]
          • chunk text + metadata + doc registry
      → Ingestion eval (chunk count, coverage, embedding sanity) + manifest to S3
```

- **Orchestration:** AWS Step Functions (each stage is a visible, retryable, testable step).
- **Compute:** Lambda for light steps; Fargate task for heavy/large embedding batches.
- **Multi-representation indexing** (LLM summary/propositions per chunk) is added in Phase 2
  when we measure whether it improves retrieval — kept out of the v1 baseline for simplicity.
- **Video ingestion (later):** add an Amazon Transcribe branch (video/audio → transcript →
  same chunk/embed path). Designed for now, built later.

---

## 3. Online pipeline (query / response) — delivered in TWO phases

The goal of phasing is **learning by measurement**: build the simplest thing that works,
measure it, then add one advanced stage at a time and quantify its individual impact against
the golden dataset. This tells you the real need, significance, and impact of decomposition,
RRF, Cohere Rerank, Chain-of-Note, and CRAG — instead of guessing.

### Phase 1 — Baseline (simple, measurable)

```
User question
  → CloudFront → API Gateway (HTTP API) → Lambda query service
  → Input Guardrails (Bedrock Guardrails: prompt-injection / abuse)
  → Embed query (Titan v2)
  → Dense retrieval from Aurora pgvector (top-K ANN)         ← single query, dense only
  → Build prompt (context + question + citation instructions)
  → Generate answer — Claude Sonnet (with citations)
  → Output Guardrails (PII / unsafe / secret-leak)
  → Response + citations to user;  traces + metrics emitted (X-Ray, CloudWatch)
```
Establish the **baseline scores** (faithfulness, answer relevance, context precision/recall,
latency, cost/query) on the golden set. Everything in Phase 2 is measured as a **delta vs this baseline.**

### Phase 2 — Incremental advanced stages (add ONE at a time, measure each)

Add each stage behind a feature flag, run the eval suite, record the delta, keep it only if it
helps. Suggested order (cheapest/highest-leverage first):

| Step | Stage added | What it should improve | How we measure the delta |
|---|---|---|---|
| 2.1 | **Hybrid retrieval** (pgvector + full-text) + **RRF merge** | Recall on exact terms (service names, CVE IDs) | Context Recall, Hit Rate@K |
| 2.2 | **Cohere Rerank** (cross-encoder on top-K) | Precision — right chunk ranked first | Context Precision, MRR/NDCG |
| 2.3 | **Query transformation** (multi-query → decomposition → HyDE) | Recall on ambiguous / multi-hop / vocabulary-mismatch queries | Context Recall on hard-query subset |
| 2.4 | **Chain-of-Note** | Groundedness / fewer hallucinations; "I don't know" when unsupported | Faithfulness, hallucination rate |
| 2.5 | **CRAG grade** (+ optional web fallback) | Robustness when retrieval is weak/stale | Correctness on out-of-corpus / stale queries |

Each toggle is A/B-comparable, so you get an evidence-based answer to "does RRF / rerank /
CoN / CRAG actually help *our* corpus and queries, and is the added latency/cost worth it?"

> This mirrors the `AI-PLATFORM/rag` decision tree (§10): start simple, justify every added
> stage with an eval delta.

---

## 4. AWS services — what / how / why

### Ingestion & data
| Service | How | Why |
|---|---|---|
| **Amazon S3** | Raw content bucket, processed-text bucket, artifacts/manifests | Durable, cheap, event source |
| **Amazon Textract** | Scanned/complex PDF → text | Non-native PDFs |
| **AWS Step Functions** | Orchestrates offline stages | Visible, retryable, testable per step |
| **AWS Lambda** | Light steps: clean, chunk, metadata, upsert | Serverless, scale-to-zero |
| **Amazon ECS / Fargate** | Heavy embedding/parsing batches | Right-sized compute only when running |
| **Amazon EventBridge** | S3 upload → trigger ingestion | Decoupled events |
| *(later)* **Amazon Transcribe** | Video/audio → text | Multi-modal, deferred |

### Knowledge store
| Service | How | Why |
|---|---|---|
| **Aurora PostgreSQL Serverless v2** | pgvector (dense ANN) + tsvector/GIN (full-text) hybrid; chunk text + metadata + doc registry | Scales to budget; hybrid in one engine; SQL metadata filters |

### AI / inference (Amazon Bedrock)
| Model | How | Phase |
|---|---|---|
| **Titan Text Embeddings v2** | Embed chunks (offline) + queries (online) | 1 |
| **Claude Sonnet** | Generation w/ citations; (later) query transforms + CRAG grading | 1 (gen), 2 (transforms/CRAG) |
| **Cohere Rerank** | Cross-encoder re-rank of top-K | 2 |
| **Bedrock Guardrails** | Input + output filtering | 1 |

### Application & edge
| Service | How | Why |
|---|---|---|
| **Amazon API Gateway (HTTP API)** | Public query endpoint | Managed, throttling, JWT auth |
| **AWS Lambda** | Online RAG orchestration (query service) | Cheap, scale-to-zero (see §6) |
| **Amazon Cognito** (new pool) | End-user auth | Public users; JWT to API GW |
| **Amazon CloudFront** | Global edge + TLS for UI/API | "Around the globe" latency, single region |
| **Amazon S3 + CloudFront** | Static chat UI | Cheap static hosting |
| **AWS WAF** | Rate-limit / block abuse | Public endpoint protection |

### Security, ops, eval
| Service | How | Why |
|---|---|---|
| **AWS Secrets Manager** | DB creds / keys | No secrets in code |
| **AWS KMS** | Encrypt S3, Aurora, Secrets | Sensitive content |
| **Amazon CloudWatch** | Metrics, logs, dashboards, alarms | Online observability + eval metrics |
| **AWS X-Ray** | Trace the online pipeline per stage | Latency attribution |
| **Bedrock model invocation logging + evaluation** | Capture prompts/responses; run evals | Quality measurement |

---

## 5. Overall ecosystem (how it fits together)

```
                    ┌────────── OFFLINE (ingestion) ──────────┐
   content ──► S3 ──► EventBridge ──► Step Functions ──► Lambda/Fargate
                                                   │ (Textract, chunk, Titan embed)
                                                   ▼
                                        Aurora Serverless v2
                                        (pgvector + full-text)
                                                   ▲
   user ──► CloudFront ──► WAF ──► API Gateway ──► Lambda query service
             (+ Cognito auth)                      │  Bedrock: Guardrails, Titan,
                                                   │  (Phase 2) Cohere Rerank, Claude
                                                   ▼
                                             cited answer
                    └────────── ONLINE (query) ───────────────┘

   Cross-cutting: CloudWatch + X-Ray (observability) · Secrets Manager + KMS (security)
                  · RAGAS/Bedrock eval (quality) · CloudFormation (IaC) · GitHub Actions (CI/CD)
```

---

## 6. Query compute: Lambda — pros & cons

You chose Lambda. Here's the honest tradeoff so you know when to revisit.

**Pros (why Lambda fits v1)**
- **Scale-to-zero → cheapest** at 20 users / bursty traffic; you pay per request, not idle.
- **No servers to manage**; fast to ship; native API Gateway + Cognito integration.
- Easy per-request tracing (X-Ray) and IAM scoping.

**Cons (watch for these)**
- **Cold starts** add latency (hundreds of ms to ~1–2s) — noticeable on a chat UX after idle.
  Mitigate with a small **provisioned concurrency** (e.g. 1) if it bothers users.
- **15-minute max** execution — fine for online queries, not for heavy ingestion (that's why
  ingestion heavy-steps use Fargate).
- **Package/size limits** — the query service must stay lean; big native deps (some ML libs)
  are awkward. Our design keeps heavy lifting in **Bedrock** (managed), so Lambda stays light.
- **Long streaming responses**: supported via Lambda response streaming, but if you later want
  rich token-streaming to the UI at scale, **Fargate** behind the ALB is smoother.

**Recommendation:** Lambda for Phase 1–2. Revisit **Fargate** only if (a) cold-start latency
hurts UX, or (b) you add token-streaming + higher concurrency later. The API contract stays
the same, so switching compute later is low-friction.

---

## 7. Reuse vs. new (account `001961766007`)

**Reuse (account-level only):** Bedrock model access (Claude/Titan/Cohere enabled),
CloudTrail (org trail), KMS/Config/GuardDuty account settings.

**Create new (all Hub resources):** dedicated small VPC (isolation from the internal POC),
S3 buckets, Aurora Serverless v2, Step Functions, Lambdas, Fargate task, API Gateway,
**new Cognito user pool**, CloudFront, WAF, Secrets, dashboards — one CloudFormation stack set
tagged `project=cloud-security-knowledge-hub`.

**Do NOT reuse:** the MSP POC's AgentCore runtimes/gateway/Cognito — different system, users,
lifecycle. Keeping the customer-facing Hub isolated protects blast radius.

Detailed reasoning + cost in `COST-AND-REUSE.md`.

---

## 8. CloudFormation structure (raw YAML, nested stacks)

```
infra/
├── root.yaml            # orchestrates nested stacks + parameters/outputs
├── 00-network.yaml      # dedicated VPC, subnets, SGs, VPC endpoints (S3, Bedrock, etc.)
├── 01-data-stores.yaml  # S3 buckets, Aurora Serverless v2 (+pgvector bootstrap), Secrets, KMS
├── 02-ingestion.yaml    # Step Functions, Lambdas, Fargate task, EventBridge, Textract role
├── 03-query-service.yaml# API Gateway (HTTP), query Lambda, Cognito pool, WAF
├── 04-edge-ui.yaml      # CloudFront, S3 static site
├── 05-observability.yaml# CloudWatch dashboards/alarms, X-Ray, log groups, Bedrock logging
└── 06-cicd.yaml         # GitHub OIDC deploy role
```
`dev`/`prod` via parameter files. pgvector + schema bootstrapped via a CFN custom resource
(Lambda) after the cluster is up.

---

## 9. Repo layout

```
PRODUCTION/use-cases/cloud-security-knowledge-hub/
├── PLAN.md                 ← this file
├── AI-SDLC-AND-EVALS.md    ← SDLC + per-component evaluation plan + phased milestones
├── COST-AND-REUSE.md       ← detailed cost model + reuse analysis
├── diagrams/               ← rendered architecture diagrams
├── infra/                  ← CloudFormation templates (Phase 1+)
├── ingestion/              ← offline pipeline code
├── query-service/          ← online pipeline code (Phase 1 baseline first)
└── evals/                  ← eval harness + golden dataset (built later)
```

Design guidance is pulled from `AI-PLATFORM/` (rag §, guardrails, memory, runtime).

---

## 10. Summary

Budget-fit, single-region, custom advanced-RAG on AWS. Offline v1 ingests **text + PDF**
(video later) via S3 + Textract + Step Functions into **Aurora Serverless v2 + pgvector**.
Online is delivered in **two phases** — a simple measurable baseline, then advanced stages
(hybrid+RRF, Cohere Rerank, query transformation, Chain-of-Note, CRAG) added one at a time and
A/B-measured so you learn each step's real value. Bedrock provides Titan embeddings, Claude
Sonnet generation, Cohere Rerank, and Guardrails; Lambda + API Gateway + Cognito + CloudFront
+ WAF deliver it; CloudWatch + X-Ray + RAGAS measure it. Reuses only account-level services;
deploys as an isolated CloudFormation stack set. See `AI-SDLC-AND-EVALS.md` and
`COST-AND-REUSE.md`.
