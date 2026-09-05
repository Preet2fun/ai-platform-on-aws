# Blueprints — Reusable Patterns

Copy-paste-ready patterns that PRODUCTION use cases assemble from. Each blueprint = a
proven, best-practice-compliant building block. Runnable templates live in the skill at
`.kiro/skills/aws-agentcore-expert/scripts/`.

## Catalog

| Blueprint | What it gives you | Status |
|---|---|---|
| **supervisor-plus-a2a** | Supervisor router + A2A specialist decomposition | [ ] to author |
| **mcp-tool-target** | Expose an external system as an MCP gateway tool (auth by type) | [ ] to author |
| **episodic-memory-agent** | Agent wired with SEMANTIC + EPISODIC memory + retrieve-before-act | [ ] to author |
| **guardrailed-agent** | Agent with Bedrock Guardrails (input+output) attached | [ ] to author |
| **observed-agent** | OTel tracing + dashboard + alarms for an agent | [ ] to author |
| **evaluated-agent** | Online evaluation + custom evaluator wiring | [ ] to author |
| **least-privilege-role** | IAM role template scoped per agent/gateway | [ ] to author |

## How to use
1. Pick the blueprints your use case needs.
2. Compose them following `../reference-architecture/`.
3. Validate against `../principles/`, `../security/`, and `../well-architected/`.

> Build these blueprints once, reuse across RCA / SRE / Security use cases.
