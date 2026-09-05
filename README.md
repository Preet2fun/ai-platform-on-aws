# Agentic AI Platform on AWS Bedrock AgentCore — SRE / RCA / SOC

This repository builds a **production-grade agentic AI platform** on Amazon Bedrock
AgentCore for **SRE, Root-Cause Analysis, and Security Operations** use cases.

It is organized into three top-level folders that represent a deliberate progression from
*what exists*, to *how it should be built*, to *what we ship*.

```
┌──────────────┐        ┌──────────────────┐        ┌──────────────────┐
│     POC/     │        │   AI-PLATFORM/   │        │   PRODUCTION/    │
│              │ lessons│                  │guidance│                  │
│ as-deployed  │  &     │ best practices,  │  &     │ RCA · SRE ·      │
│ + gap        │ ─────► │ reference arch,  │ ─────► │ Security agentic │
│ analysis     │  gaps  │ blueprints       │blueprnt│ use cases        │
└──────────────┘        └──────────────────┘        └──────────────────┘
   "what is"               "how it should be"           "what we ship"
```

## Folders

### `POC/` — Proof of Concept (as-deployed)
Everything currently deployed and explored in AWS account `001961766007` (us-east-1): the
existing Motadata MSP SRE/SOC assistant, its source scaffolding, and full discovery docs.
**Purpose:** learn from it and find the gaps vs. best practice. See `POC/OVERVIEW.md`.

### `AI-PLATFORM/` — Best Practices & Guidance
The authoritative "how it should be built": guiding principles, target reference
architecture, per-AgentCore-service guidance, security baseline, Well-Architected mapping,
reusable blueprints, and standards. Derived from AgentCore + AWS best practices and POC
lessons. See `AI-PLATFORM/README.md`.

### `PRODUCTION/` — Agentic AI Use Cases
Production-grade RCA, SRE, and Security use cases built strictly on the `AI-PLATFORM/`
guidance, plus the shared platform foundation (infra, shared libs, runbooks). See
`PRODUCTION/README.md`.

## Tooling

- **`.kiro/agents/agentcore-expert.md`** — a custom Kiro agent scoped as an AgentCore
  platform builder for SRE/RCA/SOC. Use it to drive work in `AI-PLATFORM/` and `PRODUCTION/`.
- **`.kiro/skills/aws-agentcore-expert/`** — the curated AgentCore knowledge (8-phase build
  playbook + service guides + references + templates) that the agent reads.

## Working model

1. **Learn** from `POC/` (gaps are documented there).
2. **Codify** the right way in `AI-PLATFORM/` (principles → architecture → blueprints).
3. **Build** real use cases in `PRODUCTION/`, each passing the AI-PLATFORM Definition of
   Done + Well-Architected review before go-live.

Drive each step with the **`agentcore-expert`** agent — it enforces the guidance and
verifies against AgentCore/AWS docs and the live account.
