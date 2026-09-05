# Use Case — Root-Cause Analysis (RCA)

Automated RCA for incidents: given an alarm/incident, gather telemetry, correlate signals,
form and test hypotheses, and produce a root cause + remediation with evidence.

## Why AgentCore fits
RCA is the textbook **episodic-memory** use case — the agent should learn from past
incidents and reuse proven investigation playbooks.

## Design (per AI-PLATFORM)
- **Agents:** `investigator` (A2A) led by the supervisor; pulls from telemetry/log/trace tools.
- **Memory:** SEMANTIC (environment facts) + **EPISODIC + reflection** (incident playbooks).
- **Tools (MCP via Gateway):** CloudWatch metrics/logs/alarms, X-Ray/traces, change history,
  CMDB. Read-heavy.
- **Guardrails:** output filtering (no secret leakage in findings).
- **Observability + Evaluations:** custom evaluator for **RCA correctness**.
- **HITL:** remediation proposed, not auto-applied, unless policy-approved.

## Blueprints used
`episodic-memory-agent`, `mcp-tool-target`, `observed-agent`, `evaluated-agent`,
`guardrailed-agent`, `least-privilege-role`.

## Definition of Done
See `../../../AI-PLATFORM/standards/README.md`. Plus: RCA-correctness evaluator live;
episodic memory populated from historical incidents.

## Status
- [ ] Agent scaffold  - [ ] Tools wired  - [ ] Episodic memory  - [ ] Evaluator  - [ ] IaC + runbook
