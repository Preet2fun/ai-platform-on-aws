# Sources — Runtime & Multi-Agent Patterns

The runtime guidance in this folder is grounded in the following AWS sources. Content was
rephrased for compliance; verify against current AWS documentation before building.

## Primary sources

**[1] Well-Architected Agentic AI Lens — AGENTPERF05: Workflow orchestration and multi-agent collaboration**
https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentperf05.html
- Orchestration coordinates distribution, agent selection/invocation, result passing, and
  parallelism; performance depends on these.
- Orchestration types: dynamic graphs (reasoning-driven), deterministic skeletons (Step
  Functions), hybrid.
- Collaboration models matched to task shape: supervisor-worker, pipeline, peer-to-peer,
  swarm; default to tools over sub-agents.
- Delegation transfers only needed context via shared stores + standardized interfaces;
  handoff latency is a first-class metric; large results passed by reference.
- Guardrails for dynamic graphs: cycle detection, max depth, bounded fan-out.
- Timeouts (per-step/branch/workflow) from task SLO; slow branches return best partial
  result; end-to-end tracing (AgentCore Observability / X-Ray).
- Maturity levels 1–5 (Initial → Optimized).
- Common issues: sub-agent overuse, serial execution, unbounded delegation, inline
  payloads, uniform pipeline compute, full-history handoffs.

**[2] AGENTPERF05-BP02: Implement optimized multi-agent collaboration models**
https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentperf05-bp02.html
- Tool vs sub-agent decision (tool: deterministic/stateless/single-step/<2–3s; sub-agent:
  own reasoning/context/multi-step/different model/failure isolation); borderline → start
  as tool, promote on re-invocation.
- Pattern selection: supervisor-worker (decomposition + central QA), pipeline (sequential),
  peer-to-peer/blackboard (async partial solutions), swarm (parallel exploration; needs
  convergence + budgets).
- Deploy on AgentCore Runtime (managed scaling/observability) or EKS/ECS; monitor
  coordination latency, redundant-work rate, throughput.
- Anti-patterns: sub-agent for tool work; supervisor-worker for everything; swarm without
  convergence/budgets. Risk if not established: High.

## Supporting
- [Multi-agent architectures — AWS AI agent learning series](https://aws.amazon.com/marketplace/build-learn/ai-agent-learning-series/multi-agent-architectures)
- [Scaling agentic AI: Enterprise patterns without vendor lock-in](https://aws.amazon.com/blogs/machine-learning/scaling-agentic-ai-enterprise-patterns-without-vendor-lock-in/)
- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html)

## Note on the originally requested URL
The user-provided blog
(`builder.aws.com/content/3DCax04M9o7gBpAMttstsLjmPUD/multi-agent-architecture-patterns-with-amazon-bedrock-agentcore-runtime`)
could not be extracted programmatically. This guidance is instead grounded in the canonical
AWS Well-Architected Agentic AI Lens, which covers the same multi-agent-on-AgentCore-Runtime
material and is pillar-aligned with this reference. Re-verify against that blog if desired.
