# Guardrails — Gap-to-Remediation Checklist

Maps the **POC current state** (from account `001961766007`) to the **target** guardrail
architecture, in the order to implement. Use with the `agentcore-expert` agent.

## Current state (from POC discovery)
- ❌ **0 Bedrock Guardrails** configured (runtimes hold `bedrock:ApplyGuardrail` but nothing to apply).
- ❌ **No Policy Engine / Cedar policies** — no per-tool authorization layer.
- ❌ **Gateway execution role = `AdministratorAccess`** (`msp-gateway-execution-role`).
- ◐ Gateway auth present (AWS_IAM); MCP runtimes use Cognito JWT.
- ◐ CloudWatch + CloudTrail present; no policy-decision logging or denial alarms; no GuardDuty noted.
- ◐ Runtimes in PUBLIC network mode.

## Remediation sequence

### Phase A — Authorization foundation
- [ ] Create a **Policy Engine** per gateway (`create-policy-engine`).
- [ ] Associate it with the gateway; start in **monitor/log mode**.
- [ ] Add the **permissive baseline** permit so traffic isn't fully denied.
- [ ] Baseline real traffic; capture decision logs.

### Phase B — Least privilege (highest-risk fix)
- [ ] Replace `AdministratorAccess` on `msp-gateway-execution-role` with a scoped policy
      (only its targets + `bedrock:InvokeGuardrailChecks`).
- [ ] Add **per-tool Cedar `permit`** policies for exactly the tools each agent needs
      (RCA = read telemetry; SRE = read + gated remediation; SOC = read security data).
- [ ] Add **`forbid`** policies for destructive/business-denied actions.

### Phase C — Input guardrails
- [ ] `promptAttack` (PROMPT_INJECTION, JAILBREAK, PROMPT_LEAKAGE) → `forbid`.
- [ ] `sensitiveInformation` on input where relevant.
- [ ] `contentFilter` for SOC agents ingesting attacker-controlled text.

### Phase D — Output guardrails
- [ ] `sensitiveInformation` (SSN, card, email, phone, …) → `suppressOutput`.
- [ ] `contentFilter` → `suppressOutput` for unsafe content.

### Phase E — Bypass prevention
- [ ] Restrict `bedrock-agentcore:InvokeAgentRuntime` via runtime **resource policy** to
      the supervisor/gateway principals only.
- [ ] Evaluate **VPC network mode** for runtimes handling private telemetry/security data.

### Phase F — Turn on enforcement
- [ ] Switch policy engine to **ENFORCE** once permits cover legitimate flows.
- [ ] Set policies to **ACTIVE**.

### Phase G — Observability of guardrails
- [ ] Log every allow/deny + guardrail block.
- [ ] Alarm on denial/block spikes (attack or misconfig).
- [ ] Enable **GuardDuty**; review in the platform observability dashboards.
- [ ] Bounded log retention (ties to the observability component).

## Acceptance (per gateway / use case)
Meets the **Definition of Done** in `README.md §6`. No agent reaches a tool or returns a
response without passing the policy engine + guardrails, and the gateway role is
least-privilege.
