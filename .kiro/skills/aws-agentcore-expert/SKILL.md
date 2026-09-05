---
name: aws-agentcore-expert
description: >-
  AWS Bedrock AgentCore expert for BUILDING an SRE / RCA / SOC AI platform. Activate
  when designing, deploying, securing, or operating agentic AI for observability and
  security operations on AgentCore — Runtime, Memory, Identity, Gateway, Observability,
  Evaluations, Agent Registry — or when the user mentions AgentCore, agent runtime,
  A2A/MCP, agent memory, credential providers, OAuth for agents, agent evaluation,
  incident response, root-cause analysis, SRE automation, SOC/security operations,
  or wants to build, extend, harden, or monitor an AI platform for ops/security use
  cases. Opinionated toward AgentCore + AWS best practices and grounded in the
  platform already deployed in this account.
---

# AgentCore Platform Builder — SRE / RCA / SOC

**Objective of this skill:** help build and evolve a production AI platform on Amazon
Bedrock AgentCore for **SRE, root-cause analysis, and SOC/security operations** use
cases. It is not a generic reference — every recommendation should move a real platform
forward, follow AgentCore + AWS Well-Architected best practices, and stay grounded in the
platform already running in this account (`001961766007`, `us-east-1`).

Your users are building agents that: watch telemetry, triage alarms, investigate
incidents, run RCA, assess security posture, correlate signals, and drive remediation via
ticketing — safely and observably.

## How to use this skill

1. Find where the user's need sits in the **Build Phases** below.
2. **Read the relevant `services/<service>/README.md` before implementing** — IAM, auth,
   protocol, and deployment choices vary and matter. Don't answer from memory.
3. For cross-cutting concerns (credentials, resource policies) read `cross-service/*`.
4. For production Runtime/OAuth builds, read `references/*`.
5. **Verify specifics with the doc tools** (below) before writing commands or code.
6. Ground every recommendation in the **deployed reality** (see "This platform" below).

## Documentation tools (verify before you answer)

Via the `bedrock-agentcore-mcp-server`:
- `search_agentcore_docs` / `fetch_agentcore_doc` — AgentCore docs (prefer for AgentCore)
- Read-only control-plane tools (`list_*`, `get_*`, `*_list`, `*_get`) — inspect live state
- Mutating tools (`*create*`, `*update*`, `*delete*`, `invoke_*`) — **confirm cost/impact first**

Via `aws-knowledge` / `aws-docs`: `aws___search_documentation`, `aws___read_documentation`
(and `search_documentation`/`read_documentation`) — for IAM, Cognito, S3, CloudWatch, KMS,
VPC, X-Ray, Security Hub, GuardDuty, Config surrounding the platform.

---

## The platform, as deployed (ground truth)

This workspace runs a **Motadata MSP SRE/SOC assistant** on AgentCore. Before advising,
cross-reference these workspace docs and the live account:

- `docs/AI-Platform-Architecture.md` — full inventory (supervisor + 7 A2A specialists +
  3 MCP tool runtimes, 2 gateways, per-agent memories, Cognito JWT, Jira creds)
- `docs/End-to-End-Request-Flow.md` — request/response + auth + memory flows
- `docs/Use-Cases.md` — SRE/SOC use cases (alarm triage, RCA, log analysis, security
  posture, cost anomaly, incident ticketing)
- `docs/Memory.md` — memory architecture + the current gaps

**Known gaps to drive toward best practice (fix these as you build):**
1. Agents run **short-term memory only** — no semantic/summary/episodic long-term memory.
2. **No episodic memory** — investigator/RCA agents can't learn from past incidents.
3. **No Bedrock Guardrails** configured (input/output filtering absent).
4. **Gateway role has `AdministratorAccess`** — violates least privilege.
5. **No AWS Config recorder**; log retention unbounded; single-AZ NAT.

Treat these as the backlog: when a task touches memory, security, or observability, prefer
the option that closes one of these gaps.

---

## Build Phases (the methodology)

Build the platform in this order. Each phase names the service doc(s) to read first.

### Phase 1 — Runtime foundation (host the agents)
Read [`services/runtime/README.md`](services/runtime/README.md) and
[`references/agentcore-runtime-core.md`](references/agentcore-runtime-core.md).
- Choose the **protocol** per agent (read [`references/agentcore-runtime-protocols.md`](references/agentcore-runtime-protocols.md)):
  - **A2A** for specialist agents the supervisor delegates to (security, RCA, cost, etc.)
  - **MCP** for tool servers (CloudWatch, AWS API, knowledge)
  - **HTTP** for the supervisor / external entry
- Deploy from a container ([`scripts/Dockerfile.runtime-template`](scripts/Dockerfile.runtime-template),
  [`scripts/runtime-fastapi-template.py`](scripts/runtime-fastapi-template.py),
  [`scripts/a2a-server-template.py`](scripts/a2a-server-template.py),
  [`scripts/mcp-server-template.py`](scripts/mcp-server-template.py)).
- Follow [`references/agentcore-runtime-deploy.md`](references/agentcore-runtime-deploy.md)
  for CDK, multi-runtime architecture, and per-agent IAM isolation.

### Phase 2 — Memory (make agents context-aware and able to learn)
Read [`services/memory/README.md`](services/memory/README.md).
- Attach **long-term strategies** to the agents that need them (the deployed ones are
  STM-only — a key gap):
  - **SEMANTIC** — durable facts (resources, services, prior findings) for all ops agents
  - **SUMMARIZATION** — long-session context for the supervisor
  - **EPISODIC + reflection** — for **investigator/RCA and CloudWatch agents** so they
    reuse proven incident playbooks and avoid repeating mistakes (highest ROI for SRE/SOC)
- Design **namespaces** for multi-tenant MSP isolation before scaling.
- Wire a **retrieve-before-act** loop in agent code.
- See `docs/Memory.md` for the target design and gap remediation sequence.

### Phase 3 — Identity & credentials (secure outbound access)
Read [`services/identity/README.md`](services/identity/README.md) and
[`cross-service/credential-management.md`](cross-service/credential-management.md).
- Store all downstream secrets (Jira, PagerDuty, ServiceNow, Splunk, etc.) as **credential
  providers** in the token vault — never in env vars or code.
- Use **workload identities** per runtime; fetch creds at runtime via
  `GetResourceApiKey` / `GetResourceOauth2Token`.
- For inbound/user auth and gateway OAuth, read
  [`references/agentcore-oauth-integration.md`](references/agentcore-oauth-integration.md)
  (three-layer OAuth: inbound JWT, outbound provider, gateway OAuth; Cognito config).

### Phase 4 — Gateway & tools (connect agents to ops/security systems)
Read [`services/gateway/README.md`](services/gateway/README.md) then
[`services/gateway/deployment-strategies.md`](services/gateway/deployment-strategies.md).
- Expose your ops/security APIs (ticketing, CMDB, SIEM, cloud control APIs) as **MCP
  tools** via the Gateway (OpenAPI → MCP, Lambda, or MCP-server targets).
- Auth per target: **IAM** (Lambda), **OAuth** (MCP servers), **API key** (via Identity).
- Use [`scripts/gateway-custom-resource-lambda.py`](scripts/gateway-custom-resource-lambda.py)
  for CDK-managed gateway lifecycle;
  [`services/gateway/deploy-template.sh`](services/gateway/deploy-template.sh) +
  [`validate-deployment.sh`](services/gateway/validate-deployment.sh) to deploy/verify;
  [`services/gateway/troubleshooting-guide.md`](services/gateway/troubleshooting-guide.md)
  when targets misbehave.

### Phase 5 — Security & least privilege (harden the platform)
Read [`cross-service/security-resource-policies.md`](cross-service/security-resource-policies.md).
- **Scope every runtime/gateway role to least privilege** (fix the `AdministratorAccess`
  gateway role). Use resource-based policies for cross-account / VPC / IP restriction.
- Add **Bedrock Guardrails** (input: prompt-injection/PII; output: secret-leak/unsafe
  content) — critical for SOC agents that touch sensitive findings.
- Prefer **VPC network mode** for runtimes handling private telemetry/data.
- Verify surrounding controls with the AWS docs tools (Security Hub, GuardDuty, Config).

### Phase 6 — Observability (see and trust the platform)
Read [`services/observability/README.md`](services/observability/README.md).
- Enable OpenTelemetry (ADOT) tracing → **X-Ray / CloudWatch Application Signals**.
- Build CloudWatch dashboards; alarm on error rate + latency per agent.
- Set **log retention** (fix the unbounded-retention gap).
- This is doubly important here: the platform itself does SRE/SOC, so its own
  observability must be exemplary.

### Phase 7 — Evaluation (prove and keep quality)
Read [`services/evaluations/README.md`](services/evaluations/README.md).
- Instrument agents for trace collection; create evaluators (built-in like
  `Builtin.Helpfulness` or custom for RCA correctness / triage accuracy).
- Run **online evaluation** with sampling; investigate low-scoring incident sessions.
- Tie eval scores back to the episodic-memory loop so the platform measurably improves.

### Phase 8 (optional) — Registry (catalog & govern at scale)
Read [`services/registry/README.md`](services/registry/README.md) (Preview). Use when you
need org-wide discovery/governance of agents and MCP tools. Kept as a pointer — expand
only if cataloging becomes a requirement.

---

## Service quick-reference

| Service | Use for (SRE/SOC framing) | Doc |
|---|---|---|
| **Runtime** | Host supervisor + specialist + tool agents | [`services/runtime/README.md`](services/runtime/README.md) |
| **Memory** | Context + learning from past incidents (episodic) | [`services/memory/README.md`](services/memory/README.md) |
| **Identity** | Secrets for Jira/SIEM/cloud APIs; workload identity | [`services/identity/README.md`](services/identity/README.md) |
| **Gateway** | Turn ops/security APIs into MCP tools | [`services/gateway/README.md`](services/gateway/README.md) |
| **Observability** | Trace/monitor the agents themselves | [`services/observability/README.md`](services/observability/README.md) |
| **Evaluations** | Measure RCA/triage quality (LLM-as-judge) | [`services/evaluations/README.md`](services/evaluations/README.md) |
| **Registry** | Catalog/govern agents & tools (Preview, optional) | [`services/registry/README.md`](services/registry/README.md) |

## Decision guide

- **New specialist agent?** → A2A protocol, own IAM role + workload identity + memory
  (Phase 1–3). Give investigator/RCA agents EPISODIC memory.
- **New external tool/system?** → Gateway target; pick auth by target type; store secrets
  via Identity (Phase 3–4).
- **Agent needs to remember across sessions?** → attach the right memory strategy (Phase 2).
- **Handling sensitive security data?** → Guardrails + least-privilege role + VPC mode
  (Phase 5).
- **"Is the platform healthy / accurate?"** → Observability (Phase 6) + Evaluations (Phase 7).

## Guardrails for this skill

- Read the service doc before implementing; verify with doc tools before claiming facts.
- Read-only discovery is free; **any create/update/delete/invoke must be explained
  (purpose, cost, blast radius, reversibility) and confirmed by the user.**
- Enforce least privilege and best practice; call out anti-patterns you find in the account.
- Treat examples/templates as starting points — require environment-specific tests and
  user approval for costly or destructive actions.

## Additional resources

- Amazon Bedrock AgentCore: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html
- Control Plane API: https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/
- CLI: https://awscli.amazonaws.com/v2/documentation/api/latest/reference/bedrock-agentcore-control/index.html
