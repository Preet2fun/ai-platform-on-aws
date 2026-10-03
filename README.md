# AI Platform on AWS — Production RAG & Agentic AI

**Building RAG and agentic AI on AWS is engineering, not magic.** This repo is how you ship it
responsibly: a real retrieval-augmented product, a reusable platform standard, and a measured
process where nothing goes live on faith.

🏗️ **A shipped RAG product**, not a toy demo — ingestion, retrieval, generation, guardrails,
evals, observability, and a UI, all wired together on AWS.
📐 **A reusable platform standard** on Amazon Bedrock AgentCore for SRE / RCA / Security-Operations
agentic use cases.
🔬 **Evidence over vibes** — every advanced feature is A/B-measured against a baseline on a
human-reviewed golden set and live traffic, and kept only if it actually helps.

> 💡 The interesting part isn't that the advanced pipeline shipped — it's that **half of it
> didn't**, because the numbers said so. The repo shows the measurement that made that call.

---

## 🎯 Why this repo?

Most RAG write-ups stop at "we added reranking and it got better." This one shows the whole loop:

- **Measure before you ship.** A simple baseline goes live first. Each advanced stage (hybrid
  retrieval, reranking, query transformation, Chain-of-Note, corrective-RAG, metadata filtering)
  is enabled behind a flag and measured against that baseline. Keep it only if the gain justifies
  the latency and cost.
- **Score against *real* retrieved context.** Offline and online evaluation both judge answers
  against the actual passages retrieval returned — captured via OpenTelemetry GenAI traces — not
  the model's self-consistency.
- **Honest findings register.** Every issue is tracked problem → fix → status, *including the
  fixes that failed* (an "obvious" optimization that regressed a target query, and a confidence
  grader that over-refused). You learn from the misses, not just the wins.
- **Well-Architected by default.** Guardrails, least-privilege IAM, PII blocking, cost modeling,
  reliability, and observability are first-class, not afterthoughts.

---

## 🧩 What's built: the Cloud Security Knowledge Hub (production RAG)

`PRODUCTION/use-cases/cloud-security-knowledge-hub/`

A customer-facing RAG assistant for AWS security questions — how to configure a service securely,
how an attack happens, and how to prevent it — grounded in a curated corpus with citations.

**Ingestion (offline):**
```
S3 (raw docs) → EventBridge → Step Functions
   → extract (pypdf / Textract fallback) → clean → structure-aware chunk + per-chunk metadata
   → Titan v2 embeddings → Aurora PostgreSQL (pgvector)
```

**Query (online):**
```
UI (CloudFront + Cognito) → API Gateway (JWT) → Lambda
   → hybrid retrieval + Cohere reranking over pgvector
   → Claude (cited answer) → Bedrock Guardrails → response
```

**Evaluation & observability:**
- A human-reviewed **golden set** + Bedrock **LLM-as-judge** (RAGAS-style faithfulness,
  answer-relevancy, context-precision, context-recall).
- Answers scored against the **real retrieved passages** via OpenTelemetry GenAI traces
  (CloudWatch Transaction Search).
- Custom CloudWatch metrics for ingestion quality, offline gate, and live online eval.

**The headline result:** running the baseline against an "everything on" advanced pipeline, the
all-stages-on variant was a **net negative** (a corrective-RAG grader over-refused and a hard
metadata filter mis-routed queries). The config that actually **beat the baseline on every
quality metric** was the lean one — **hybrid retrieval + reranking** — with the rest measured,
rejected, and documented. Full head-to-head and the reasoning:
[`docs/phase-2/PHASE-2-CONCLUSION.md`](PRODUCTION/use-cases/cloud-security-knowledge-hub/docs/phase-2/PHASE-2-CONCLUSION.md).

### 📋 Next: agentic use cases on the platform standard
`PRODUCTION/use-cases/{rca,sre,security}/` — Root-Cause-Analysis, SRE, and Security-Operations
**agentic** use cases to be built on Bedrock AgentCore (Runtime, Memory, Identity, Gateway,
Observability) following the `AI-PLATFORM/` guidance. Scoped next; the RAG system above is the
first fully-shipped example of the working model.

---

## 🗂️ Repository structure

Three top-level folders — *what exists*, *how it should be built*, *what we ship* — with a strict
one-way dependency: production and POC may reference the standard; the standard never references
them.

```
┌──────────────┐        ┌──────────────────┐        ┌──────────────────────┐
│     POC/     │ lessons│   AI-PLATFORM/   │guidance│     PRODUCTION/      │
│ as-deployed  │   &    │ best practices,  │   &    │ RAG (shipped) +      │
│ + gap        │ ─────► │ reference arch,  │ ─────► │ RCA · SRE · Security │
│ analysis     │  gaps  │ blueprints       │blueprnt│ agentic use cases    │
└──────────────┘        └──────────────────┘        └──────────────────────┘
   "what is"               "how it should be"            "what we ship"
```

| Folder | Role | Start at |
|---|---|---|
| **`PRODUCTION/`** | What we ship — production use cases on the standard, plus shared platform (infra, libs, runbooks). Home of the RAG system. | `PRODUCTION/README.md` |
| **`AI-PLATFORM/`** | How it should be built — a use-case-agnostic standard: principles, reference architecture, RAG patterns, guardrails, memory, per-service guidance across the six Well-Architected pillars. | `AI-PLATFORM/README.md` |
| **`POC/`** | What exists — as-deployed assistants, scaffolding, and gap-analysis that feeds lessons back into the standard. | `POC/OVERVIEW.md` |

---

## 🔁 Working model

1. **Learn** from `POC/` — gaps vs. best practice are documented there.
2. **Codify** the right way in `AI-PLATFORM/` — principles → architecture → blueprints.
3. **Build & measure** real use cases in `PRODUCTION/` — each passing the AI-PLATFORM Definition
   of Done, a Well-Architected review, and an **eval gate** before go-live.

## 🛠️ Tooling
- **`.kiro/agents/agentcore-expert.md`** — a custom agent scoped as an AgentCore platform builder
  for SRE/RCA/SOC; drives work in `AI-PLATFORM/` and `PRODUCTION/`.
- **`.kiro/skills/aws-agentcore-expert/`** — curated AgentCore knowledge (build playbook, service
  guides, references, templates) the agent reads.

---

**Start here:** the shipped RAG system's conclusion —
[`PHASE-2-CONCLUSION.md`](PRODUCTION/use-cases/cloud-security-knowledge-hub/docs/phase-2/PHASE-2-CONCLUSION.md)
— a concrete, measured example of the whole model, from baseline to shipped config.

> ⚠️ Public repo: this README intentionally omits account identifiers, regions, endpoints, cost
> figures, and raw eval numbers. Those live in the internal docs under `PRODUCTION/`.
