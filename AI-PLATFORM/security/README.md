# Security Baseline

Mandatory security controls for every PRODUCTION use case. Source: skill
`cross-service/security-resource-policies.md`, `credential-management.md`, AWS docs.

## Baseline controls
- **Least-privilege IAM** per runtime + gateway (no admin roles). Resource-based policies
  for cross-account / VPC / IP restriction where needed.
- **Bedrock Guardrails** on all model calls: input (prompt-injection, PII) + output
  (secret-leak, unsafe content). Mandatory for security/SOC agents.
- **Secrets** only via AgentCore Identity token vault; rotation policy enforced.
- **Encryption:** CMK (KMS) for sensitive memory/data; TLS everywhere.
- **Network:** VPC mode for runtimes touching private telemetry; HA egress.
- **Governance:** AWS Config recorder enabled (POC gap); CloudTrail multi-region (present);
  GuardDuty / Security Hub reviewed.
- **Human-in-the-loop** approval for consequential remediation actions.

## Checklists
- [ ] Per-agent IAM policy review template
- [ ] Guardrail policy definitions (input + output)
- [ ] Data classification → control mapping
- [ ] Pre-prod security review gate

## POC gaps to close
1. Gateway role `AdministratorAccess` → least privilege.
2. No Guardrails → define + attach.
3. No AWS Config recorder → enable.
