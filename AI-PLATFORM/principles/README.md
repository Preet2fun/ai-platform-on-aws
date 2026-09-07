# Design Principles

Component-agnostic principles for agentic AI on Amazon Bedrock AgentCore. They apply
across every component and are grounded in the 6 Well-Architected pillars. Use-case-neutral
by design.

1. **Least privilege everywhere.** Each runtime, gateway, and tool gets only the access it
   needs — its own scoped IAM role and identity. No shared broad-admin roles. *(Security)*

2. **Guardrails on every model interaction.** Input and output filtering, plus
   policy-based authorization, are default — not optional add-ons. *(Security)*

3. **Memory is intentional.** Choose short-term vs. long-term, and which long-term
   strategy, based on the agent's need — never all-by-default, never STM-only for an agent
   meant to learn. *(Performance, Cost)*

4. **Single controlled entry path.** Callers reach agents through a controlled front door
   (gateway + policy engine); direct runtime invocation is prevented. *(Security)*

5. **Observability is first-class.** Tracing, metrics, and structured logs are built in,
   with bounded retention. *(Operational Excellence)*

6. **Quality is measured.** Agent behavior is evaluated, not assumed; feedback loops drive
   improvement. *(Operational Excellence)*

7. **Secrets in a managed vault.** Outbound credentials come from the Identity token vault,
   never from code or environment variables. *(Security)*

8. **Everything as code, versioned.** IaC-defined, reproducible, promoted through
   environments. No console-only production changes. *(Operational Excellence)*

9. **Isolate boundaries by design.** Namespaces, tags, and resource policies separate
   distinct entities/domains from the start. *(Security, Reliability)*

10. **Human-in-the-loop for consequential actions.** Actions that change real systems are
    policy-gated, not autonomous by default. *(Security, Reliability)*

11. **Design for graceful degradation.** Async processes may lag; agents remain functional
    and fail safe. *(Reliability)*

12. **Efficiency by default.** Minimal, purposeful configuration; reuse over recompute;
    right-sized models and retention. *(Performance, Cost, Sustainability)*

Each principle maps to one or more pillars (see `../well-architected/`). Components apply
these principles concretely in their own analyses.
