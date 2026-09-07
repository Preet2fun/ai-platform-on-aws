# Repository Structure & AI-PLATFORM Independence

This workspace builds an agentic AI platform on Amazon Bedrock AgentCore, organized into
three **independent-in-one-direction** top-level folders. Always respect this model.

## The three folders

### `AI-PLATFORM/` — the standard (independent reference)
Design, guidance, and architecture **best practices** for AgentCore, built from research
(AWS blogs, webinars, workshops, production examples) and industry standards.

**Hard rules for anything under `AI-PLATFORM/`:**
1. **Independent.** It must NOT reference, depend on, or import context from `POC/` or
   `PRODUCTION/`. No mentions of those folders, their contents, account IDs, resource
   names, or findings.
2. **Use-case-agnostic.** Do NOT mention specific use cases or domains (e.g. SRE, RCA, SOC,
   incident response, or any business/product name). It is a generic standard. Use neutral
   examples ("an agent", "a tool", "an external API") — introduce a specific example ONLY
   when the user explicitly asks for one.
3. **Structure = component × 6 pillars.** Organize by AgentCore component (Runtime,
   Gateway, Memory, Identity, Observability, Evaluations, Guardrails/Policy). Each
   component is described once, then analyzed through the six AWS Well-Architected pillars
   (Security, Reliability, Operational Excellence, Performance Efficiency, Cost
   Optimization, Sustainability). Follow `AI-PLATFORM/_component-template/`.
4. **Cite sources.** Every guidance doc cites its sources (AWS docs/blogs/workshops)
   inline. Verify facts against current AWS documentation before writing. Rephrase source
   content for compliance (no long verbatim quotes).

### `POC/` — ad-hoc learning & experiments
What has been tried/implemented (not necessarily to standard). This is where gap analysis
against `AI-PLATFORM/` happens and where experiments live. `POC/` MAY reference
`AI-PLATFORM/`; `AI-PLATFORM/` must never reference `POC/`.

### `PRODUCTION/` — real use cases
Production-grade use cases built **using** `AI-PLATFORM/` standards and informed by `POC/`
learnings. `PRODUCTION/` MAY reference `AI-PLATFORM/`; `AI-PLATFORM/` must never reference
`PRODUCTION/`.

## Dependency direction (one-way)
```
AI-PLATFORM  (independent standard)
     ▲                 ▲
     │ references      │ references
   POC/            PRODUCTION/
```
`AI-PLATFORM/` depends on nothing internal. `POC/` and `PRODUCTION/` may depend on
`AI-PLATFORM/`. Never the reverse.

## When editing
- Editing `AI-PLATFORM/`? Apply the four hard rules above. If a use case or POC detail
  seems relevant, do NOT add it unless the user explicitly asks.
- Doing gap analysis or experiments? That belongs in `POC/`, referencing `AI-PLATFORM/`.
- Building a use case? That belongs in `PRODUCTION/`, referencing `AI-PLATFORM/`.
- Not sure whether something is generic enough for `AI-PLATFORM/`? Ask the user.

## `.kiro/` (tooling) sits at repo root and is not part of the three folders.
