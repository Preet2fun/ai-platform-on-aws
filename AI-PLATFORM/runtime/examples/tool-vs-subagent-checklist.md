# Example — Tool vs Sub-Agent Decision Checklist

The most consequential runtime decision: should a capability be a **tool** (fast, cheap) or
a **sub-agent** (a full reasoning loop)? Getting this wrong is a common, high-risk
anti-pattern. Grounded in AGENTPERF05-BP02 (see `../reference/SOURCES.md`).

## Quick rule
> **Default to a tool. Promote to a sub-agent only when re-invocation patterns show it
> needs its own reasoning loop.**

## Choose a TOOL when ALL are true
- [ ] Deterministic (same input → same output)
- [ ] Stateless
- [ ] Single-step
- [ ] Fast (under ~2–3 seconds)
- [ ] Examples: API call, database lookup, format conversion, calculation

## Choose a SUB-AGENT when ANY is true
- [ ] Needs its own reasoning (LLM inference for ambiguous inputs / judgment calls)
- [ ] Needs its own context or memory scope
- [ ] Multi-step tool orchestration where sequencing itself requires reasoning
- [ ] Needs a different model or prompt than the parent
- [ ] Needs independent failure isolation

## Why it matters
- A tool call completes in **milliseconds**; a sub-agent delegation is a **full LLM
  reasoning loop** (time + tokens).
- Delegating deterministic single-step work to a sub-agent pays reasoning-loop cost for
  work a tool would handle instantly — **High** risk per the lens.

## Borderline cases
Start as a tool. Watch invocation patterns. If the capability is frequently re-invoked with
contextual variation that needs judgment, promote it to a sub-agent.

_Source: AGENTPERF05-BP02 [2] in `../reference/SOURCES.md`. Rephrased for compliance._
