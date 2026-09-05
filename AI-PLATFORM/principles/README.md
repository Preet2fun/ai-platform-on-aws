# Guiding Principles

Non-negotiables for the SRE/RCA/SOC agentic platform. Every PRODUCTION use case is
reviewed against these.

1. **Agents are least-privilege by default.** Each runtime has its own IAM role and
   workload identity, scoped to exactly what it needs. No shared admin roles. (POC gap:
   gateway role had `AdministratorAccess`.)

2. **Guardrails on every model interaction.** Input (prompt-injection, PII) and output
   (secret-leak, unsafe content) filtering via Bedrock Guardrails — mandatory for agents
   that touch security findings or customer telemetry. (POC gap: none configured.)

3. **Memory is intentional.** Choose a memory strategy per agent: SEMANTIC for facts,
   SUMMARIZATION for long sessions, EPISODIC+reflection for agents that must learn from
   past incidents (RCA, triage). Never ship STM-only for a learning agent. (POC gap:
   STM-only everywhere.)

4. **Observability is first-class.** The platform does SRE/SOC, so its own tracing,
   metrics, and log retention must be exemplary (OTel → X-Ray/App Signals, bounded
   retention, per-agent dashboards + alarms).

5. **Quality is measured, not assumed.** Agents are evaluated (LLM-as-judge + custom
   evaluators for RCA correctness / triage accuracy). Low-scoring sessions are reviewed.

6. **Secrets live in the token vault.** All downstream credentials (Jira, SIEM, cloud
   APIs) via AgentCore Identity credential providers — never env vars or code.

7. **Everything is IaC + versioned.** CDK-defined, per-agent versioned runtimes,
   reproducible deploys. No console-only changes in production.

8. **Multi-tenant isolation by design.** Namespaces, tags, and (where needed) resource
   policies isolate tenants/actors from the start.

9. **Human-in-the-loop for consequential actions.** Remediation/ticketing that changes
   real systems requires policy-gated approval, not autonomous execution by default.

10. **Well-Architected alignment.** Every design maps to the WAF pillars (see
    `../well-architected/`).
