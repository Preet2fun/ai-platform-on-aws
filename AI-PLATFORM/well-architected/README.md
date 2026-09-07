# Well-Architected — The 6-Pillar Lens for Agentic AI on AgentCore

Every component in this reference is analyzed through the six AWS Well-Architected pillars.
This page defines what each pillar means **for agentic AI on Amazon Bedrock AgentCore**, so
component analyses stay consistent. It is the shared vocabulary; component folders apply it.

_Source: [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html) and its Generative AI lens._

## The pillars, applied to AgentCore

### 🔒 Security
Protect data, models, credentials, and actions across the agent execution path.
- Least-privilege IAM per runtime/gateway; no broad admin roles.
- Guardrails on model interactions (input + output); policy-based authorization (Cedar).
- Secrets in a managed vault (Identity), not code/env; encryption (KMS) for sensitive data.
- Prevent bypass of controls; isolate boundaries (namespaces, VPC where warranted).

### 🛡️ Reliability
The platform behaves predictably and degrades gracefully.
- Deterministic policy evaluation; graceful behavior when async processes (e.g. memory
  extraction) haven't completed.
- Retries/fallbacks for tool calls; stateless runtimes with durable state externalized.
- Monitor background jobs; redrive failures.

### ⚙️ Operational Excellence
Run agents like production services.
- Everything as code (IaC); versioned components; reproducible deploys.
- Observability + evaluation feedback loops; runbooks.
- Deliberate rollout (monitor → enforce) for policy/guardrail changes.

### 🚀 Performance Efficiency
Right resource for the job.
- Appropriate model + memory strategy per agent; retrieval to avoid redundant reasoning.
- Precise, minimal policies/tool sets to keep latency low.
- Tune retrieval (`topK`, namespaces) and thresholds.

### 💰 Cost Optimization
Spend follows value.
- Attach only needed strategies/guardrails; model tiering; bounded retention.
- Session/lifecycle tuning; avoid paying to store or process what isn't used.

### 🌱 Sustainability
Efficient resource use.
- Minimal, purposeful configuration; scale-to-zero where possible; reuse over recompute;
  block bad input early to avoid wasted cycles.

## How components use this

Each component `README.md` contains a **"through the 6 pillars"** section applying these
definitions to that component (e.g. what Security means for Memory, what Cost means for
Guardrails). This page is the reference definition; components are the application.

## Acceptance lens
A component design is "well-architected" when it can answer each pillar concretely. If it
can't, the design is incomplete.
