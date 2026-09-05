# Well-Architected — Agentic AI Lens

Maps the platform to the AWS Well-Architected pillars, with the Generative AI / agentic
lens. Every PRODUCTION use case is reviewed against this.

| Pillar | What it means for this platform | Key practices |
|---|---|---|
| **Operational Excellence** | Run agents like production services | IaC (CDK), versioned runtimes, observability + evaluations closed loop, runbooks |
| **Security** | Protect data, models, and actions | Least-privilege IAM, Guardrails, token vault, encryption, HITL for actions (see `../security/`) |
| **Reliability** | Graceful degradation | Fallback flows, retries, HA egress, stateless runtimes, memory as durable state |
| **Performance Efficiency** | Right model + right memory | Model selection per agent, episodic memory to reduce redundant reasoning, caching |
| **Cost Optimization** | Spend follows value | Model tiering, session lifetime tuning, bounded retention, cost evaluators |
| **Sustainability** | Efficient resource use | ARM64 runtimes, scale-to-zero where possible |

## Review gate
- [ ] Each PRODUCTION use case completes a WAF review against these pillars before go-live.

> This is the acceptance lens. If a design can't answer each pillar, it's not production-ready.
