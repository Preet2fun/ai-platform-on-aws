# Service Guidance — Observability

> How we monitor the platform. Source: skill `services/observability/`.
> Doubly important: this platform *does* SRE/SOC, so its own observability must be exemplary.

## Standard
- **OpenTelemetry (ADOT)** tracing on every runtime → **X-Ray / CloudWatch App Signals**.
- Per-agent **dashboards**; **alarms** on error rate + latency + tool-failure rate.
- **Bounded log retention** (POC gap: unbounded) set per data class.
- Structured logging with correlation IDs across supervisor → specialist → tool.

## Best practices
- [ ] Golden signals per agent (latency, errors, saturation, tool success)
- [ ] Trace propagation across A2A + MCP hops
- [ ] Dashboard + alarm templates (IaC)

## POC gaps addressed
- Set retention on all log groups; add per-agent dashboards/alarms; confirm trace coverage.
