# Standards & Conventions

Platform-wide conventions every PRODUCTION use case follows. Keeps the platform
consistent, discoverable, and operable as it scales.

## Naming
- Runtimes: `{env}_{domain}_{role}` (e.g. `prod_rca_investigator`, `prod_soc_triage`).
- Memories: `{runtime}_mem`. Gateways: `{env}-{platform}-gateway`.
- Credential providers: `{env}-{system}-{type}` (e.g. `prod-jira-api-key`).

## Tagging (all resources)
- `platform=agentic-sre-soc`, `env`, `domain` (rca|sre|security), `owner`, `cost-center`,
  `data-classification`.

## Memory namespaces
- `tenant/{tenantId}/agent/{name}/actor/{actorId}/facts`
- `tenant/{tenantId}/agent/{name}/actor/{actorId}/episodes/{sessionId}`
- reflections must be a sub-path of the episode namespace.

## Deployment & versioning
- CDK only; no console changes in prod. Per-agent immutable versions; promote via endpoints.
- Environments: `dev` → `staging` → `prod`, separate accounts/namespaces where possible.

## Definition of Done (per PRODUCTION use case)
- [ ] Maps to reference-architecture
- [ ] Satisfies principles + security baseline + WAF review
- [ ] Memory strategy chosen; Guardrails attached; least-privilege IAM
- [ ] Observability (dashboards/alarms) + evaluators in place
- [ ] IaC + runbook committed
