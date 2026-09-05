# PRODUCTION — Agentic AI Use Cases

The **implementation layer**. Production-grade agentic AI use cases for **RCA, SRE, and
Security operations**, built strictly on the guidance in `../AI-PLATFORM/`.

Nothing here is greenfield guesswork: every use case composes `AI-PLATFORM/blueprints`,
maps to `AI-PLATFORM/reference-architecture`, and passes the `AI-PLATFORM/principles`,
`security`, and `well-architected` gates before go-live.

## Structure

```
PRODUCTION/
├── platform/              # shared foundation used by all use cases
│   ├── infra/             # CDK: VPC, gateways, identity, guardrails, observability
│   ├── shared-libs/       # common agent runtime code (memory, identity, a2a, obs)
│   └── runbooks/          # operational runbooks
├── use-cases/
│   ├── rca/               # Root-Cause Analysis agent(s)
│   ├── sre/               # SRE / ops automation agent(s)
│   └── security/          # SOC / security operations agent(s)
└── README.md
```

## Use cases

| Use case | Goal | Lead agents | Status |
|---|---|---|---|
| **RCA** | Automated root-cause analysis for incidents | investigator + telemetry/log tools + EPISODIC memory | [ ] scaffold |
| **SRE** | Ops automation: alarm triage, health, remediation | sre/ops + CloudWatch/cloud tools | [ ] scaffold |
| **Security** | SOC: posture, findings triage, correlation | security + SIEM/security tools + Guardrails | [ ] scaffold |

## Build workflow (per use case)
1. Read `../AI-PLATFORM/` (principles → reference-architecture → relevant service-guidance).
2. Compose the needed `blueprints/`.
3. Implement agent(s) + tools + memory + guardrails + observability + evaluators.
4. Pass the `standards/README.md` Definition of Done + WAF review.
5. Deploy via `platform/infra` (CDK), promote dev → staging → prod.

## Relationship to the other folders
```
POC (lessons)  →  AI-PLATFORM (how-to)  →  PRODUCTION (this: real use cases)
```

> Use the `agentcore-expert` Kiro agent to drive each build — it enforces the AI-PLATFORM
> guidance and verifies against AgentCore/AWS docs and the live account.
