# Example Cedar Policies (SRE / RCA / SOC)

Ready-to-adapt Cedar policies for the AgentCore Policy Engine. Semantics (verified):
**default-deny**, **forbid-overrides-permit**, each policy evaluated independently.
`context.input.*` = tool parameters; `principal.getTag(...)` = OAuth token claims.

> In ENFORCE mode nothing is allowed unless a `permit` matches. Add scoped permits for the
> tools each agent legitimately needs, plus `forbid` guardrail policies for content safety.

## 1. Permissive baseline (required in ENFORCE mode)
Lets benign requests reach the agent; still subject to `forbid` guardrails.
```cedar
permit (principal, action, resource is AgentCore::Gateway);
```
Prefer scoping it (e.g. to a target or authenticated principal) rather than fully open.

## 2. Input guardrail — block prompt injection & jailbreak
```cedar
forbid (
  principal,
  action == AgentCore::Action::"PromptAttack",
  resource
)
when {
  context.guardrail.promptAttack in ["PROMPT_INJECTION", "JAILBREAK", "PROMPT_LEAKAGE"] &&
  context.guardrail.confidence.greaterThan(decimal("0.6"))
};
```

## 3. Output guardrail — suppress PII (e.g. SSN) leaking in responses
```cedar
suppressOutput (
  principal,
  action,
  resource
)
when {
  context.guardrail.sensitiveInformation == "US_SOCIAL_SECURITY_NUMBER" &&
  context.guardrail.confidence.greaterThan(decimal("0.5"))
};
```

## 4. Tool least-privilege — RCA agent may READ telemetry only
```cedar
// Allow: read CloudWatch metrics/logs via the telemetry MCP target
permit (
  principal,
  action == AgentCore::Action::"TelemetryTool___get_metrics",
  resource == AgentCore::Gateway::"arn:aws:bedrock-agentcore:us-east-1:001961766007:gateway/<gw-id>"
);
permit (
  principal,
  action == AgentCore::Action::"TelemetryTool___query_logs",
  resource == AgentCore::Gateway::"arn:aws:bedrock-agentcore:us-east-1:001961766007:gateway/<gw-id>"
);
```

## 5. Business rule — deny destructive remediation (SRE)
```cedar
// Never allow autonomous destructive actions; require an elevated principal instead.
forbid (
  principal,
  action == AgentCore::Action::"CloudTool___delete_resource",
  resource
);

// Permit a bounded, safe remediation (e.g. restart) only for approved operators.
permit (
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"CloudTool___restart_service",
  resource
)
when {
  principal.hasTag("role") && principal.getTag("role") == "sre-operator"
};
```

## 6. SOC guardrail — block toxic/violent content on the security agent
```cedar
forbid (
  principal,
  action,
  resource
)
when {
  context.guardrail.contentFilter in ["VIOLENCE", "HATE", "MISCONDUCT"] &&
  context.guardrail.confidence.greaterThan(decimal("0.6"))
};
```

## 7. Ticketing — allow create, forbid bulk/delete
```cedar
permit (
  principal,
  action == AgentCore::Action::"TicketTool___create_ticket",
  resource
);
forbid (
  principal,
  action == AgentCore::Action::"TicketTool___delete_ticket",
  resource
);
```

---

### Notes
- Field names in `context.guardrail.*` are illustrative — confirm exact attribute paths
  with the current AgentCore guardrail policy schema before deploying (use the
  `agentcore-expert` agent + `search_agentcore_docs`).
- Prefer generating guardrail policies with `agentcore add policy --form-category ...
  --form-filters ... --form-effect ...` (it emits valid Cedar), then version them here.
- Categories: `contentFilter` (VIOLENCE, HATE, SEXUAL, MISCONDUCT, INSULTS),
  `promptAttack` (JAILBREAK, PROMPT_INJECTION, PROMPT_LEAKAGE),
  `sensitiveInformation` (ADDRESS, EMAIL, PHONE, CREDIT_DEBIT_CARD_NUMBER, SSN, …).
- Effects: `permit`, `forbid`, `suppressOutput` (output phase).
