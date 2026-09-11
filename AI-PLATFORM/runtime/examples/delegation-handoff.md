# Example — Delegation & Handoff Best Practices

How agents pass work and context to each other efficiently. Grounded in AGENTPERF05 (see
`../reference/SOURCES.md`). Generic and use-case-agnostic.

## Principles
1. **Transfer only what the receiver needs.** Don't send the full conversation history on
   every handoff — receiving agents shouldn't re-derive context the parent already had.
2. **Pass large results by reference.** Store big intermediate outputs in a shared store
   (object store / DynamoDB) and pass a reference, not the payload inline. Keeps the
   orchestrator's context window small and state size bounded.
3. **Use shared context stores.** A shared store (e.g. AgentCore Memory) carries delegation
   context across agents instead of inline transfers.
4. **Use standardized interfaces.** Delegate through a standardized interface (e.g. a
   gateway) rather than bespoke per-agent wiring.
5. **Measure handoff latency.** Treat handoff latency as a first-class metric — overhead
   grows silently if unmeasured.

## Async delegation
When the parent has parallel work to do, use **asynchronous delegation** (e.g. event-driven
callbacks) instead of blocking. Pre-warm predictable receivers (provisioned concurrency or
warm session pools) to cut cold-start latency.

## Handoff checklist
- [ ] Minimal context transferred (not full history)
- [ ] Large payloads passed by reference
- [ ] Shared context store used for cross-agent state
- [ ] Standardized delegation interface (not ad-hoc calls)
- [ ] Handoff latency measured and on a dashboard
- [ ] Async delegation where the parent can proceed in parallel

## Common anti-patterns
- Full conversation history transferred on every handoff.
- Inline transfer of large intermediate results.
- Delegation latency never measured.

_Source: AGENTPERF05 [1] in `../reference/SOURCES.md`. Rephrased for compliance._
