# Use Case — SRE / RCA Agentic System (multi-tenant, on Bedrock AgentCore)

A production-grade **multi-agent SRE assistant** that runs **autonomous, hypothesis-driven
investigations**: given a tenant's alarm, it forms competing root-cause hypotheses, gathers
telemetry to confirm or **reject** each, and converges on one evidence-backed root cause with a
HITL-gated remediation. It **learns across incidents** via episodic memory. The SRE agent is the
RCA engine.

**Stack:** Python · LangGraph (agents) · A2A (agent-to-agent) · MCP (tools) · containers on
AgentCore Runtime · multi-tenant · CloudFormation. Built on `AI-PLATFORM/` standards + the
`.kiro` `aws-agentcore-expert` 8-phase methodology.

See **`PLAN.md`** for the full architecture, decisions, and phase breakdown.

## Build status
- [x] **P0 — Scaffolding + synthetic multi-tenant data + tenant registry**
- [ ] P1 — Runtime foundation (containers on AgentCore Runtime)
- [ ] P2 — Memory (semantic + summarization + episodic+reflection, per-tenant namespaces)
- [ ] P3 — Identity & credentials (token vault, workload identities, tenant JWT)
- [ ] P4 — Gateway & tools (OpenAPI→MCP, per-target auth)
- [ ] P5 — Security & guardrails (least-privilege, Bedrock Guardrails, VPC)
- [ ] P6 — Observability (ADOT→X-Ray/App Signals, per-tenant dashboards)
- [ ] P7 — Evaluation (RCA correctness, hypothesis-rejection quality, triage accuracy)
- [ ] P8 — Full hypothesis-board GUI
- [ ] P9 *(deferred)* — Real-CloudWatch fidelity upgrade (same MCP tool contract)

## What exists after P0

```
sre/
├── PLAN.md                        # full plan + approved decisions
├── synthetic-data/
│   ├── SCENARIO-SCHEMA.md         # fixture + manifest schema
│   └── tenants/
│       ├── registry.yaml          # 2 tenants (acme-retail, globex-fintech)
│       ├── acme-retail/   runbooks.json + scenarios/{rds-connection-exhaustion, cache-stampede, bad-deploy-latency-regression}/
│       └── globex-fintech/ runbooks.json + scenarios/{pod-crashloop-bad-config, noisy-neighbor-latency, dns-resolution-failure}/
└── tools/                         # synthetic observability backends (FastAPI)
    ├── common/{fixtures.py, app.py}
    └── README.md                  # run + endpoints
```

**6 labeled incident scenarios across 2 tenants**, each a self-contained story with a
ground-truth root cause + the hypotheses that should be rejected (the eval label), plus
tenant-scoped metrics / logs / traces / changes / events fixtures.

**6 synthetic observability backends** (metrics / logs / traces / changes / k8s-events /
runbooks) as one FastAPI app — tenant-scoped, time-filterable, with tenant isolation enforced and
the ground-truth manifest **not** exposed. These become MCP tools in P4; the OpenAPI schema is the
tool contract (swappable for real CloudWatch in P9).

Run + examples: `tools/README.md`.

## Design (per AI-PLATFORM)
- **Agents:** supervisor (HTTP) + investigator/hypothesis, telemetry, change-correlation,
  remediation (A2A).
- **Memory:** per-tenant SEMANTIC + SUMMARIZATION + **EPISODIC+reflection** (retrieve-before-act).
- **Tools (MCP via Gateway):** the six backends above (read-heavy); remediation gated by approval.
- **Guardrails:** input + output filtering. **Observability + Evaluations:** RCA-correctness +
  triage-accuracy + hypothesis-rejection-quality evaluators. **HITL:** every change action gated.

## Blueprints used
`supervisor-plus-a2a`, `mcp-tool-target`, `episodic-memory-agent`, `observed-agent`,
`evaluated-agent`, `guardrailed-agent`, `least-privilege-role`.

## Definition of Done
See `../../../AI-PLATFORM/standards/README.md`. Plus: RCA-correctness + triage-accuracy evaluators
live; episodic memory populated; remediation behind approval policy; multi-tenant isolation proven.
