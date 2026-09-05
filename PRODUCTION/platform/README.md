# Platform — Shared Foundation

Shared infrastructure and code that all PRODUCTION use cases (RCA, SRE, Security) build on.
Implements the `../../AI-PLATFORM/` reference architecture once, reused everywhere.

## Layout
- `infra/` — CDK stacks for the shared foundation:
  - networking (VPC, HA NAT, endpoints), AgentCore Gateway(s), Identity/credential
    providers, Bedrock Guardrails, observability (dashboards/alarms), Config/CloudTrail.
- `shared-libs/` — common agent runtime code: memory client (semantic/episodic),
  identity/creds, A2A client, observability setup, guardrail hooks. (The POC
  the developer source in `POC/agentcore-poc-dev/agents/` (esp. `shared/` and each
    runtime's `base_runtime.py`, `gateway_client.py`, `sanitize.py`) is the starting
    reference — consolidate and harden it here.)
- `runbooks/` — operational runbooks (deploy, rotate creds, incident response for the
  platform itself, rollback).

## Status
- [ ] infra: VPC + gateway + identity + guardrails + observability baseline
- [ ] shared-libs: memory (with episodic), identity, a2a, observability, guardrails
- [ ] runbooks: deploy, credential rotation, rollback
