# Production-Grade Multi-Tenant SRE Agentic System on Bedrock AgentCore — Plan

> **Location:** `PRODUCTION/use-cases/sre/`
> **Stack:** Python everywhere · LangGraph (agent framework) · A2A (agent-to-agent) · MCP (tools) ·
> containers on AgentCore Runtime · multi-tenant.
> **Built on:** `AI-PLATFORM/` standards + the `.kiro` `aws-agentcore-expert` skill's 8-phase methodology.

## Approved decisions (v1)
1. **Data sourcing:** Option A now (synthetic tenant-scoped MCP backends) → Option B later
   (real CloudWatch, P9, same tool contract). Option C (dummy rows in RDS) rejected as a
   telemetry source.
2. **Scenarios:** ~6 labeled incidents across 2 tenants.
3. **IaC:** CloudFormation.
4. **GUI:** full hypothesis board.
5. **Model:** Claude Sonnet for all agents to start.
6. **v1 scope:** P0–P8 shippable; P9 (real CloudWatch) deferred.

---

## 0. What we're building

A multi-agent **SRE assistant** that, given an alarm/incident for a specific **tenant**, runs an
**autonomous, hypothesis-driven investigation** — forming competing root-cause hypotheses,
gathering telemetry (metrics/logs/traces/changes) to confirm or **reject** each one, and
converging on a single evidence-backed root cause with a remediation proposal (HITL-gated). It
**learns across incidents** via episodic memory, so recurring signatures resolve faster. The SRE
agent *is* the RCA engine. The GUI shows the live hypothesis board
(candidates → evidence → accepted/rejected → conclusion), mirroring the AWS DevOps-Agent
"investigation in action" pattern.

---

## 1. Data sourcing (the key design decision)

### Option A — Synthetic "mock observability" backends behind MCP tools *(CHOSEN for v1)*
Small **FastAPI stub services** (`metrics-api`, `logs-api`, `traces-api`, `changes-api`,
`k8s-events-api`, `runbooks-api`) serve **realistic, tenant-scoped, scenario-driven synthetic
data** from fixtures. Exposed as **MCP tools via the AgentCore Gateway** (OpenAPI → MCP). Each tool
call carries a `tenant_id`; the stub returns that tenant's data for the requested window.

- Mirrors the **official AWS multi-agent SRE sample** (synthetic data from demo backends, exposed
  as OpenAPI tools; "in production these stub servers would be replaced with real infrastructure").
- Scenarios carry a **ground-truth root cause** → doubles as the **eval label**.
- Multi-tenant is clean: `tenants/<tenant_id>/scenarios/<scenario_id>/{metrics,logs,...}.json`.
- Cheap, deterministic, reproducible — ideal for building the agent loop + eval harness.

### Option B — Real telemetry via a sample app → CloudWatch *(DEFERRED to P9)*
A tiny instrumented sample app emits real metrics/logs/traces to CloudWatch/X-Ray; a
`cloudwatch-tools` MCP server implements the **same tool contract** so agents swap backend by
config, not rewrite. Highest fidelity; slower/costly/non-deterministic → fidelity upgrade.

### Option C — Dummy rows in RDS *(REJECTED as telemetry source)*
Lowest fidelity (real SRE tools are CloudWatch/X-Ray, not a SQL table). DB kept only for the
agent's own state/memory, not as the telemetry source.

---

## 2. Architecture

LangGraph **supervisor** (HTTP runtime) delegates over **A2A** to specialist agents
(**investigator/hypothesis**, **telemetry**, **change-correlation**, **remediation-HITL**), which
call **MCP tools** (via Gateway) that front the synthetic backends. **AgentCore Memory** provides
per-tenant SEMANTIC + SUMMARIZATION + EPISODIC(+reflection). Cross-cutting: Identity (token vault),
Bedrock Guardrails (in/out), Observability (ADOT→X-Ray/App Signals), Evaluations.

| Agent | Role | Protocol | Memory |
|---|---|---|---|
| Supervisor | Plan, delegate, aggregate hypotheses → verdict | HTTP | SUMMARIZATION |
| Investigator / Hypothesis | Generate competing hypotheses; decide confirm/reject evidence; render verdict (critic) | A2A | SEMANTIC + EPISODIC+reflection |
| Telemetry | Craft precise iterative metric/log/trace queries | A2A | SEMANTIC |
| Change-correlation | Correlate deploys/config/infra changes to timeline | A2A | SEMANTIC |
| Remediation (HITL) | Propose fix + ticket; never auto-apply without approval | A2A | EPISODIC |

---

## 3. Hypothesis-driven diagnosis flow

Agent loop (LangGraph state machine): **Intake** (alarm+tenant+symptom; pull semantic facts +
matching past episodes) → **Hypothesis generation** (N competing hypotheses, each with the evidence
that would confirm/reject it) → **Evidence gathering (parallel)** → **Hypothesis evaluation**
(confirmed/rejected/needs-more, with a critic challenging weak causality) → **Converge or branch**
(bounded iterations) → **Conclusion** (root cause + causal timeline + impact + HITL remediation +
citations; write episode to EPISODIC memory).

GUI (hypothesis board): left = live thought-stream; right = hypothesis cards moving across lanes
*Candidate → Investigating → Rejected(reason) → Confirmed*, each with evidence + citations; final
Root-Cause panel (timeline + remediation + accept/▶ run HITL); tenant + scenario picker on top.

---

## 4. Memory architecture (past RCAs help future ones)

Per `AI-PLATFORM/memory` + skill Phase 2. **Isolation boundary outermost = `tenant_id`.**
- SEMANTIC — durable tenant environment facts (services, dependencies, prior findings).
- SUMMARIZATION — supervisor long-session context.
- EPISODIC + reflection — each resolved incident as a reusable playbook (symptom signature →
  hypotheses → rejected-and-why → confirmed root cause → remediation → outcome). **Retrieve-
  before-act**: at intake semantic-search past episodes; if signature matches, seed hypotheses and
  shortcut. Reflection namespace is a sub-path of the episode namespace.
- Feedback loop — eval scores + human corrections update the episodic store.

Namespace shape (per the standard): `/<tenant_id>/<agent>/{actorId}/facts/`,
`/<tenant_id>/<agent>/{actorId}/episodes/{sessionId}/`,
`/<tenant_id>/<agent>/{actorId}/reflections/`.

---

## 5. Multi-tenancy model

- **Tenant identity:** inbound Cognito JWT carries `tenant_id`; supervisor propagates it through
  every A2A hop and MCP tool call.
- **Data isolation:** synthetic backends serve only the requested tenant's fixtures; memory
  namespaces per-tenant; (P9) CloudWatch scoped by tag/account per tenant.
- **Compute isolation:** per-agent least-privilege IAM roles + per-tenant workload identities.
- **Config:** `synthetic-data/tenants/registry.yaml` (name, services, data source, memory ns).
- **Eval/observability:** every trace + eval tagged with `tenant_id`.

---

## 6. Build phases (each = reviewable increment)

| Phase | What | Exit criteria |
|---|---|---|
| **P0** | Scaffolding + synthetic multi-tenant data + tenant registry | Backends serve tenant-scoped scenario data locally |
| **P1** | Runtime foundation: containerize supervisor(HTTP)+specialists(A2A)+tools(MCP); AgentCore Runtime; per-agent IAM | Supervisor reachable; A2A delegation end-to-end on one scenario |
| **P2** | Memory: per-tenant SEMANTIC+SUMMARIZATION+EPISODIC(+reflection); retrieve-before-act; seed episodic | Recurring signature resolves faster via a past episode |
| **P3** | Identity & creds: token vault; workload identities; inbound JWT w/ tenant claim | No secret in env/code; tenant claim enforced |
| **P4** | Gateway & tools: synthetic backends → MCP via Gateway (OpenAPI→MCP), per-target auth | Agents call tools only through the Gateway |
| **P5** | Security & guardrails: least-privilege roles; Bedrock Guardrails (in/out); VPC mode | Guardrails verified; roles scoped |
| **P6** | Observability: ADOT→X-Ray/App Signals; per-agent + per-tenant dashboards; log retention | Full investigation visible as one trace tree |
| **P7** | Evaluation: RCA-correctness + triage-accuracy + hypothesis-rejection-quality; online eval; tie to episodic loop | Eval gate green on labeled scenarios |
| **P8** | Full hypothesis-board GUI (thought-stream + lanes + root-cause panel + tenant/scenario picker + HITL) | Operator drives a full investigation visually, per tenant |
| **P9** *(deferred)* | Fidelity upgrade: `cloudwatch-tools` MCP (same contract) + instrumented sample app + chaos trigger | Same agent logic runs on real CloudWatch |

---

## 7. Evaluation strategy

Labeled scenarios *are* the golden set (ground-truth root cause + hypotheses-to-reject).
Evaluators (Bedrock LLM-as-judge + rule checks): **RCA correctness**, **hypothesis-rejection
quality**, **triage accuracy**, **steps/time-to-insight**, **evidence grounding**. Online eval
with sampling; low scorers feed back into episodic memory. Measure-before-you-ship: baseline the
single-agent loop, then add specialists/memory/parallelism and keep each only if evals improve.

---

## 8. Folder layout (`PRODUCTION/use-cases/sre/`)

```
sre/
├── README.md                      # this architecture + status
├── PLAN.md                        # this plan
├── agents/{supervisor,investigator,telemetry,change_correlation,remediation}/
├── tools/{metrics_api,logs_api,traces_api,changes_api,k8s_events_api,runbooks_api}/
│   └── (P9) cloudwatch_tools/     # same contract, real CloudWatch
├── synthetic-data/
│   ├── tenants/registry.yaml
│   └── tenants/<tenant_id>/scenarios/<scenario_id>/{metrics,logs,traces,changes,events}.json
├── memory/                        # namespace design + seeding scripts
├── gui/                           # hypothesis-board UI
├── evals/                         # golden scenarios + evaluators + harness
├── infra/                         # CloudFormation (runtime, gateway, memory, identity, guardrails, obs)
└── docs/                          # architecture, request-flow, memory, use-cases, runbook
```

## 9. References
- AWS DevOps Agent — autonomous incident response ("investigation in action", hypothesis-based).
- AWS ML blog — build multi-agent SRE assistants with Bedrock AgentCore (LangGraph + MCP; synthetic
  demo backends swapped for real infra in production).
- `aws-samples/sample-multi-agent-on-agentcore`.
- Resolve-AI architecture talk (narrowest-point start; parallel hypotheses; reject wrong theories;
  learn-like-an-engineer memory).
- `.kiro/skills/aws-agentcore-expert/` (8-phase methodology + service docs).
