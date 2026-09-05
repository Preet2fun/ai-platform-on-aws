# Service Guidance — Runtime

> Authoritative "how we use AgentCore Runtime" for this platform. Source: AgentCore docs
> (see `.kiro/skills/aws-agentcore-expert/services/runtime/` and `references/`), refined by
> POC lessons. Use the `agentcore-expert` agent to expand each section (it verifies facts).

## Standard
- **Protocol per role:** HTTP (supervisor/entry), A2A (specialists), MCP (tool servers).
- **Isolation:** one IAM role + workload identity per runtime; least privilege.
- **Runtime:** Python 3.11 container, ARM64, deployed via CDK; versioned per agent.
- **Network:** PUBLIC only for non-sensitive; **VPC mode** for private telemetry/data.
- **Sessions:** set idle/max lifetime deliberately per workload.

## Best practices
- [ ] Container contract & startup (ref: `references/agentcore-runtime-core.md`)
- [ ] Multi-runtime architecture & CDK (ref: `references/agentcore-runtime-deploy.md`)
- [ ] Protocol selection guide (ref: `references/agentcore-runtime-protocols.md`)

## POC gaps addressed
- Per-agent roles already good in POC — keep. Move sensitive agents to VPC mode.
