# Reference Architecture — SRE/RCA/SOC Agentic Platform

The target architecture every PRODUCTION use case builds on. This is the "should be",
informed by the POC and AgentCore best practices.

## Logical view

```mermaid
flowchart TB
    subgraph Edge
      U([Operators / Systems]) --> API[API entry<br/>authN via Cognito/OIDC]
    end
    subgraph Orchestration
      API --> SUP[Supervisor Agent<br/>HTTP · routing]
    end
    subgraph Specialists["Specialist Agents (A2A)"]
      RCA[RCA / Investigator]
      SRE[SRE / Ops]
      SEC[Security / SOC]
    end
    SUP --> RCA & SRE & SEC
    subgraph Tools["Tool Layer (MCP via Gateway)"]
      CW[CloudWatch/telemetry]
      SIEM[SIEM / Security data]
      TICKET[Ticketing / ITSM]
      CLOUD[Cloud control APIs]
    end
    RCA & SRE & SEC --> GW[AgentCore Gateway<br/>AWS_IAM / OAuth]
    GW --> CW & SIEM & TICKET & CLOUD
    subgraph Platform["Platform Services"]
      MEM[(Memory<br/>semantic + episodic)]
      ID[Identity / Token Vault]
      GR[Bedrock Guardrails]
      OBS[Observability<br/>X-Ray / App Signals]
      EVAL[Evaluations]
    end
    RCA & SRE & SEC --> MEM
    GW --> ID
    SUP & RCA & SRE & SEC --> GR
    SUP & RCA & SRE & SEC -.-> OBS
    OBS --> EVAL
```

## Design tenets

- **Supervisor + A2A specialists + MCP tools** — the proven decomposition (kept from POC).
- **Per-agent isolation** — role, workload identity, and memory per runtime.
- **Guardrails and Identity are cross-cutting** — every agent inherits them.
- **Observability + Evaluations form a closed quality loop** feeding episodic memory.

## Scalability

- Stateless agent runtimes (AgentCore-managed scaling); state in Memory + external stores.
- Gateway aggregates tools so specialists don't hardcode integrations.
- Namespaced memory for multi-tenant growth.
- New use cases = new specialist(s) + tool targets, not a rebuild.

## To be detailed here

- [ ] Network topology (VPC mode for private telemetry; HA NAT)
- [ ] Data flow + retention/classification per data type
- [ ] Multi-account/landing-zone placement
- [ ] Failure modes & fallback (per the POC error-flow, hardened)
