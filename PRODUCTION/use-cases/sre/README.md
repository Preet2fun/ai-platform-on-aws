# Use Case — SRE / Ops Automation

Operational automation: alarm triage, health summaries, log/error analysis, capacity and
cost anomaly checks, and policy-gated remediation.

## Design (per AI-PLATFORM)
- **Agents:** `sre`/ops specialist (A2A) under the supervisor.
- **Memory:** SEMANTIC (service/resource facts) + EPISODIC (recurring alarm patterns) +
  SUMMARIZATION for long triage sessions.
- **Tools (MCP via Gateway):** CloudWatch (alarms/metrics/logs), cloud control APIs
  (read), ticketing/ITSM for incident creation, deployment/change data.
- **Guardrails:** input + output filtering.
- **Observability + Evaluations:** evaluator for **triage accuracy** + time-to-insight.
- **HITL:** any change action gated by approval.

## Blueprints used
`supervisor-plus-a2a`, `mcp-tool-target`, `episodic-memory-agent`, `observed-agent`,
`evaluated-agent`, `guardrailed-agent`, `least-privilege-role`.

## Definition of Done
See `../../../AI-PLATFORM/standards/README.md`. Plus: triage-accuracy evaluator; remediation
actions behind approval policy.

## Status
- [ ] Agent scaffold  - [ ] Tools wired  - [ ] Memory  - [ ] Evaluator  - [ ] IaC + runbook
