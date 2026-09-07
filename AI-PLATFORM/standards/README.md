# Standards & Conventions

Platform-wide conventions for consistency across AgentCore components. Use-case-agnostic.

## Naming (generic)
- Runtimes: `{env}-{purpose}` (lowercase, hyphenated).
- Memories: `{runtime}-mem`. Gateways: `{env}-{purpose}-gateway`.
- Credential providers: `{env}-{system}-{type}`.
- Policies: `{effect}-{concern}` (e.g. `block-prompt-attacks`, `allow-baseline`).

## Tagging (all resources)
- `component` (runtime|gateway|memory|identity|observability|evaluations|guardrails)
- `env`, `owner`, `cost-center`, `data-classification`.

## Memory namespaces
Follow `memory/examples/namespace-conventions.md`: an outermost isolation boundary, then
`agent/{agentName}/actor/{actorId}/{recordScope}`; reflections are a sub-path of episodes.

## Infrastructure as code & versioning
- IaC only; no console changes in production.
- Version components immutably; promote across environments (`dev → staging → prod`).
- Policies, guardrails, and memory strategies are versioned as code.

## Documentation convention (this reference)
- One folder per component; component described once, then a **6-pillar analysis**.
- Generic, neutral examples only.
- Cite sources inline; verify against current AWS docs.
- No references to `POC/` or `PRODUCTION/`.

## Component acceptance (generic Definition of Done)
- [ ] Documented with the 6-pillar analysis
- [ ] Least-privilege IAM defined
- [ ] Security controls specified (guardrails/auth/encryption as applicable)
- [ ] Observability + (where relevant) evaluation hooks defined
- [ ] IaC + versioning approach specified
- [ ] Sources cited
