# Blueprints — Reusable Patterns

Reusable, best-practice-compliant building blocks composed from the component standards.
Each blueprint is generic and use-case-agnostic — a proven pattern, not a use-case
implementation.

## Catalog

| Blueprint | What it gives you | Composes |
|---|---|---|
| **controlled-entry** | Gateway + Policy Engine + guardrails as the single entry path | guardrails, gateway |
| **isolated-agent-runtime** | A runtime with its own least-privilege role + identity + memory | runtime, identity, memory |
| **mcp-tool-target** | Expose an external API/tool as an MCP gateway target (auth by type) | gateway, identity |
| **memory-enabled-agent** | An agent with an appropriate long-term memory strategy + retrieve-before-act | memory |
| **guardrailed-model-calls** | Input + output guardrails on model interactions | guardrails |
| **observed-agent** | Tracing + metrics + logging for an agent | observability |
| **evaluated-agent** | Automated quality assessment wired to an agent | evaluations |

Status: catalog defined; individual blueprint docs authored as the corresponding
components are completed.

## How to use
1. Pick the blueprints a design needs.
2. Compose them per `../reference-architecture/`.
3. Validate against `../principles/` and each component's 6-pillar analysis.

> Blueprints are generic composition patterns. They contain no use-case specifics.
