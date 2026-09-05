# POC — Proof of Concept (as-deployed)

This folder holds **everything currently deployed and explored in AWS account
`001961766007` (us-east-1)** — the Motadata MSP SRE/SOC assistant as it exists today.

Its purpose is to **learn from the current implementation and identify what is missing**
versus AgentCore + AWS best practices. It is the *baseline*, not the target.

## Contents

- `agentcore-poc-dev/` — **the authoritative developer source code** from the dev team:
  real agent runtimes (supervisor + 7 A2A specialists), MCP servers, MCP tool Lambdas,
  backend, React frontend, CDK infrastructure, runbooks, and deploy/destroy scripts. This
  is the single source of truth for the POC implementation.
  - `LIVE-ENVIRONMENT-REFERENCE.md` — the concrete deployed identifiers (runtime→memory
    IDs, gateway URL, Cognito, credential providers) captured from the live account, mapped
    to this code. (Merged in from the earlier live-discovery scaffold, which has been
    removed to avoid duplication.)
- `docs/` — discovery output and analysis of the live platform:
  - `AI-Platform-Architecture.md` — full component inventory + findings
  - `End-to-End-Request-Flow.md` — request/response, auth, and memory flows (Mermaid)
  - `Use-Cases.md` — the SRE/SOC use cases the platform supports today
  - `Memory.md` — memory architecture deep-dive + gap analysis
  - plus guardrail/memory gap diagrams
- `README.md` — original repo readme.

## How this folder feeds the vision

```
POC (this folder)                AI-PLATFORM                      PRODUCTION
─────────────────                ───────────                      ──────────
what's deployed today   ──►   best practices + guidance   ──►   production-grade
+ documented gaps             + scalable architecture           RCA / SRE / Security
(learn & critique)            (the "how it should be")          agentic use cases
```

## Known gaps found here (the backlog for AI-PLATFORM / PRODUCTION)

1. Agents run **short-term memory only** — no semantic/summary/episodic long-term memory.
2. **No episodic memory** — investigator/RCA agents can't learn from past incidents.
3. **No Bedrock Guardrails** configured.
4. **Gateway role has `AdministratorAccess`** — not least privilege.
5. **No AWS Config recorder**; unbounded log retention; single-AZ NAT.

> Do not build production on top of the POC. Extract lessons here, codify them in
> `AI-PLATFORM/`, then build clean in `PRODUCTION/`.
