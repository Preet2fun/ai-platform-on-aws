# Use Case — Security / SOC Operations

Security operations: posture assessment, findings triage and prioritization, alert
correlation, exposure/secret checks, and guided response — with strong guardrails.

## Design (per AI-PLATFORM)
- **Agents:** `security`/SOC specialist (A2A) under the supervisor.
- **Memory:** SEMANTIC (prior findings, asset context) + EPISODIC (how similar findings
  were remediated). Namespaced per tenant.
- **Tools (MCP via Gateway):** Security Hub / GuardDuty / SIEM, CloudTrail (audit), config
  posture, ticketing. Read-heavy; sensitive.
- **Guardrails:** MANDATORY — input (prompt-injection) + output (no secret/PII leakage in
  findings). Consider VPC network mode.
- **IAM:** strict least privilege; sensitive-data classification.
- **Observability + Evaluations:** evaluator for **finding accuracy / false-positive rate**.
- **HITL:** response actions require approval.

## Blueprints used
`supervisor-plus-a2a`, `mcp-tool-target`, `episodic-memory-agent`, `guardrailed-agent`
(mandatory), `observed-agent`, `evaluated-agent`, `least-privilege-role`.

## Definition of Done
See `../../../AI-PLATFORM/standards/README.md`. Plus: Guardrails verified; false-positive
evaluator; sensitive-data controls (CMK, VPC) reviewed.

## Status
- [ ] Agent scaffold  - [ ] Tools wired  - [ ] Memory  - [ ] Guardrails  - [ ] Evaluator  - [ ] IaC + runbook
