# AI-PLATFORM — Best Practices & Reference Architecture

The **guidance layer**. This folder codifies *how an agentic AI platform should be built*
on Amazon Bedrock AgentCore for **SRE / RCA / SOC** use cases — the principles, reference
architecture, per-service best practices, security baseline, and reusable blueprints that
`PRODUCTION/` use cases must follow.

It is derived from three inputs:
1. **AgentCore + AWS best practices** (see the `agentcore-expert` skill in `.kiro/skills/`).
2. **AWS Well-Architected** (with the Generative AI / agentic lens).
3. **Lessons and gaps from `POC/`** — what the current deployment got right and wrong.

> POC shows *what is*. This folder defines *what should be*. PRODUCTION implements it.

## Structure

```
AI-PLATFORM/
├── principles/            # guiding principles & non-negotiables
├── reference-architecture/# the target platform architecture (diagrams + narrative)
├── service-guidance/      # per-AgentCore-service best practices (SRE/SOC framed)
│   ├── runtime.md
│   ├── memory.md
│   ├── identity.md
│   ├── gateway.md
│   ├── observability.md
│   └── evaluations.md
├── security/              # security baseline, IAM least-privilege, guardrails
├── well-architected/      # WAF pillar mapping for agentic AI
├── blueprints/            # reusable patterns (supervisor+A2A, MCP tool, memory, eval)
└── standards/             # naming, tagging, deployment, versioning conventions
```

## How to use it

- Building anything in `PRODUCTION/`? Start here. Every use case must map to the
  reference architecture and satisfy the principles + security baseline.
- Use the **`agentcore-expert`** Kiro agent to author/extend this guidance — it reads the
  AgentCore service docs and verifies facts before writing.
- Treat each `service-guidance/*.md` as the authoritative "how we do X" for that service.

## Relationship to the other folders

```
POC  ──(lessons & gaps)──►  AI-PLATFORM  ──(principles & blueprints)──►  PRODUCTION
```
