# Reference — "How to Implement Guardrails in Amazon Bedrock AgentCore"

This is the source infographic that inspired the guardrails guidance in this folder.

## Image

Drop the infographic PNG here as `guardrails-agentcore-infographic.png`.
(It was shared in chat; save it into this folder to complete the reference. The guidance
in `../README.md` fully transcribes its content, so the doc is usable without the image.)

## Transcribed content (verbatim intent)

**Title:** How to Implement Guardrails in Amazon Bedrock AgentCore — *Secure every
interaction. Control every action. Protect every response.*

**End-to-End Guardrail Architecture:**

```
User / Application
   → AgentCore Gateway        (single entry point for all requests)
   → Policy Engine (Cedar)    (authorization & policy evaluation)
   → Guardrails (Input)       (prompt injection, jailbreak, PII & secrets, toxic content)
   → AgentCore Runtime        (agent execution & reasoning)
   → Tools / MCP              (APIs, databases, S3, SaaS, systems)
   → Output Guardrails        (PII detection, secrets protection, unsafe content, response control)
   → Safe Response to User

   ⚠ Prevent direct access to Runtime (No Gateway Bypass)
```

**1. Input Protection** — detect prompt injection, detect jailbreak attempts, block
malicious instructions, detect sensitive information. *(Example: Cedar `forbid` on
`AgentCore::Action::"PromptAttack"` when `PROMPT_INJECTION` confidence > 0.6.)*

**2. Authorization with Cedar** — policy-based control of: which tools an agent can
access, which APIs it can invoke, which actions require authorization, which business
operations are denied. *(Example decisions: read customer profile = ALLOW; create refund
<$500 = ALLOW; create refund >$500 = DENY; delete customer = DENY; access payroll = DENY.)*

**3. Protect Tools & MCP** — don't allow unrestricted access to databases, APIs, S3,
financial systems, customer data. Apply least privilege to every tool ("only what is
necessary, nothing more").

**4. Output Guardrails** — before returning: detect PII, prevent secrets leaking, filter
unsafe content, suppress sensitive responses. *(Example: Bedrock Guardrails
`SensitiveInformation` on `US_SOCIAL_SECURITY_NUMBER` in `context.output.text` with
confidence > 0.5.)*

**5. Prevent Gateway Bypass** — block direct access to AgentCore Runtime; all traffic
must go through the Gateway and Policy Engine.

**IAM & Permissions** — least-privilege IAM for the Gateway execution role. Required
permission: `bedrock:InvokeGuardrailChecks`.

**Observability** — monitor and audit every interaction (Amazon CloudWatch, AWS
CloudTrail, Amazon GuardDuty, Dynatrace).

**The Enterprise AI Principle:**
> Guardrails + Authorization + IAM + Observability = Safer Agentic AI.
> Build defense in depth. Build trust. Build responsibly.
> *Because intelligence without guardrails is a risk.*

_Source: AWS / Amazon Bedrock AgentCore community infographic._
