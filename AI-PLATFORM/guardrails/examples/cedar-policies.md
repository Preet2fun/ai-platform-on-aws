# Example Cedar Policies (generic patterns)

Reusable Cedar policy patterns for the AgentCore Policy Engine. Semantics (verified):
**default-deny**, **forbid-overrides-permit**, each policy evaluated independently.
`context.input.*` = tool parameters; `principal.getTag(...)` = identity/token claims.

> In ENFORCE mode nothing is allowed unless a `permit` matches. Add scoped permits for the
> tool actions an agent legitimately needs, plus `forbid` guardrail policies for content
> safety. Placeholders like `<gateway-arn>` and `<ToolName>` are illustrative.

## 1. Permissive baseline (required in ENFORCE mode)
Lets benign requests reach the agent; still subject to `forbid` guardrails.
```cedar
permit (principal, action, resource is AgentCore::Gateway);
```
Prefer scoping it (e.g. to a specific target or authenticated principal) over fully open.

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

## 3. Output guardrail — suppress PII in responses
```cedar
suppressOutput (
  principal,
  action,
  resource
)
when {
  context.guardrail.sensitiveInformation in ["EMAIL", "PHONE", "CREDIT_DEBIT_CARD_NUMBER"] &&
  context.guardrail.confidence.greaterThan(decimal("0.5"))
};
```

## 4. Tool least-privilege — permit a specific read-only tool action
```cedar
permit (
  principal,
  action == AgentCore::Action::"<ToolName>___<read_operation>",
  resource == AgentCore::Gateway::"<gateway-arn>"
);
```

## 5. Business rule — deny a high-impact action, gate a bounded one
```cedar
// Deny a destructive/high-impact action outright.
forbid (
  principal,
  action == AgentCore::Action::"<ToolName>___<destructive_operation>",
  resource
);

// Permit a bounded operation only for an authorized principal.
permit (
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"<ToolName>___<bounded_operation>",
  resource
)
when {
  principal.hasTag("role") && principal.getTag("role") == "<authorized-role>"
};
```

## 6. Parameter-bounded permit (condition on tool input)
```cedar
permit (
  principal,
  action == AgentCore::Action::"<ToolName>___<operation>",
  resource
)
when {
  context.input.amount < 500
};
```

## 7. Content safety — block toxic/violent content
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

---

### Notes
- `context.guardrail.*` attribute paths are illustrative — confirm exact attribute names
  against the current AgentCore guardrail policy schema before deploying.
- Prefer generating guardrail policies with the CLI (`agentcore add policy --form-category
  ... --form-filters ... --form-effect ...`), which emits valid Cedar, then version them here.
- Categories: `contentFilter` (VIOLENCE, HATE, SEXUAL, MISCONDUCT, INSULTS),
  `promptAttack` (JAILBREAK, PROMPT_INJECTION, PROMPT_LEAKAGE),
  `sensitiveInformation` (ADDRESS, EMAIL, PHONE, CREDIT_DEBIT_CARD_NUMBER, …).
- Effects: `permit`, `forbid`, `suppressOutput`.

_Source: [Understanding Cedar policies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-understanding-cedar.html), [Getting started with guardrails](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-guardrails-getting-started.html). Rephrased for compliance._
