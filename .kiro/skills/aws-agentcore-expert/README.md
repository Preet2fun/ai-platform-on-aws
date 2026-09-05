# aws-agentcore-expert (Kiro skill)

A **purpose-built AgentCore platform-builder skill** for **SRE / RCA / SOC** use cases.
Curated from the upstream
[`zxkane/aws-skills`](https://github.com/zxkane/aws-skills/tree/main/plugins/aws-agentic-ai/skills/aws-agentic-ai)
`aws-agentic-ai` skill, then trimmed and reframed for one objective: **building an AI
platform on Amazon Bedrock AgentCore for observability and security operations**, following
AgentCore + AWS best practices.

This is not a verbatim reference. `SKILL.md` is an opinionated, phased build playbook, and
content irrelevant to SRE/SOC has been physically removed.

## Scope

**In scope (kept):** Runtime, Memory, Identity, Gateway, Observability, Evaluations, and
Registry (as an optional pointer). Plus the runtime/OAuth references, credential + resource-
policy cross-service guides, and runtime/gateway deployment templates.

**Removed as out-of-scope for SRE/SOC:** Browser automation, Code Interpreter, the Registry
deep sub-guides (governance/sync/mcp-endpoint/getting-started), agent-persistence patterns,
registry-integration, and the AG-UI template. If a genuine need arises, re-crawl those from
upstream.

## What's here

- `SKILL.md` — the entrypoint: an 8-phase platform build playbook (Runtime → Memory →
  Identity → Gateway → Security → Observability → Evaluations → Registry), a service
  quick-reference, a decision guide, and the known gaps to build toward.
- `services/` — runtime, memory, identity, gateway (+deployment-strategies,
  troubleshooting, deploy/validate scripts), observability, evaluations, registry (README).
- `cross-service/` — credential-management, security-resource-policies.
- `references/` — oauth-integration, runtime-core, runtime-deploy, runtime-protocols.
- `scripts/` — Dockerfile, FastAPI (HTTP), MCP, and A2A server templates, plus the gateway
  CDK custom-resource lambda.

Service/cross-service/reference/script files are the upstream content unchanged; only
`SKILL.md` and this README were authored for the SRE/SOC objective.

## How to use it

Consumed by the **`agentcore-expert`** custom agent (`.kiro/agents/agentcore-expert.md`),
which is scoped as an SRE/SOC platform builder.

1. Open the agent picker in the chat pane header and switch to **agentcore-expert**.
2. Ask a platform-building question — "add episodic memory to the RCA agent", "expose our
   SIEM API as an MCP gateway tool", "scope the gateway role to least privilege", "add
   Guardrails to the security agent", "set up online evaluation for triage accuracy".
3. The agent locates the phase in `SKILL.md`, reads the relevant service/reference file,
   verifies with the AgentCore + AWS docs tools, and grounds advice in the deployed platform
   (`docs/`) and its documented gaps.

## Safety model (via the agent)

- Read-only discovery (CLI `list-*`/`get-*`/`describe-*`, CloudWatch/logs reads, MCP
  `list_*`/`get_*`, doc search) runs without prompting.
- Any create/update/delete/invoke (CLI or MCP control-plane) prompts for confirmation.
- Destructive shell (`rm -rf`, `sudo`) is denied.

## Updating from upstream

Re-crawl the raw GitHub files into this folder to refresh in-scope content. Keep the SRE/SOC
curation in mind — don't reintroduce Browser/Code-Interpreter/Registry-deep-dives unless a
use case requires them. Re-check `SKILL.md` front-matter/tool names after any refresh.
