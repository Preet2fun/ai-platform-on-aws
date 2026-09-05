# Service Guidance — Memory

> How we use AgentCore Memory. Source: skill `services/memory/` + POC `docs/Memory.md`.

## Standard
- **Never STM-only for a learning agent.** Choose a strategy per agent:
  - **SEMANTIC** — durable facts (resources, services, prior findings) — all ops agents
  - **SUMMARIZATION** — long-session context — supervisor
  - **EPISODIC + reflection** — RCA/investigator + triage agents (learn from incidents)
  - **USER_PREFERENCE** — where per-operator/tenant tailoring matters
- **Namespaces** designed for multi-tenant isolation before scaling
  (e.g. `tenant/{tenantId}/agent/{name}/actor/{actorId}/…`).
- **Retrieve-before-act** loop wired in every agent.
- Retention set per data class; CMK encryption for sensitive content.

## Best practices
- [ ] Strategy selection matrix per PRODUCTION use case
- [ ] Episodic memory design for RCA (episode schema + reflection namespaces)
- [ ] Extraction-job monitoring + redrive

## POC gaps addressed
- POC is STM-only with unattached strategies. Fix: attach SEMANTIC+SUMMARIZATION to live
  agents; add EPISODIC to RCA/CloudWatch agents first (highest ROI).
