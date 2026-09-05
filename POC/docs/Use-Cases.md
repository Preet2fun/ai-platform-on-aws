# Motadata MSP AI Assistant — Use Cases

> Derived from the deployed agent fleet in AWS account `001961766007` (us-east-1):
> a **supervisor** orchestrating 7 specialist agents (security, cost, cloudwatch,
> jira, knowledge, investigator, advisor), 3 MCP tool servers (AWS API, AWS
> Knowledge, CloudWatch), plus legacy RCA and Forecast agents.
>
> Each use case lists the agents involved and the downstream tools/services it
> exercises. Use cases marked _(latent)_ are supported by a deployed agent but
> depend on tool wiring that may still be a stub.

---

## How to read this

| Field | Meaning |
|---|---|
| **Trigger** | What the user asks for |
| **Agents** | Which runtimes handle it (supervisor always routes) |
| **Tools/Services** | Downstream MCP tools / AWS services / external systems |
| **Outcome** | What the user gets back |

---

## A. Cloud Operations & Monitoring

### A1 — Investigate a service health alarm
- **Trigger:** "Why is the payments service unhealthy right now?"
- **Agents:** supervisor → cloudwatch → investigator
- **Tools/Services:** CloudWatch MCP (alarms, metrics, logs), AWS API MCP
- **Outcome:** Current alarm state, correlated metrics/logs, and a likely cause.

### A2 — Summarize operational health
- **Trigger:** "Give me a health summary of my environment."
- **Agents:** supervisor → cloudwatch
- **Tools/Services:** CloudWatch alarms + metrics
- **Outcome:** Roll-up of alarms in ALARM state, noisy metrics, and hot spots.

### A3 — Log analysis for an error spike
- **Trigger:** "We're seeing 5xx errors on the API since 2pm — what's in the logs?"
- **Agents:** supervisor → cloudwatch → investigator
- **Tools/Services:** CloudWatch Logs Insights (via MCP), X-Ray/App Signals
- **Outcome:** Error patterns, affected components, and a first hypothesis.

### A4 — Root-cause analysis (RCA) for an incident
- **Trigger:** "Do an RCA on last night's outage."
- **Agents:** supervisor → investigator (legacy `RCAAgent` for deep RCA)
- **Tools/Services:** CloudWatch, AWS API MCP, knowledge base
- **Outcome:** Timeline, contributing factors, and remediation recommendations.

---

## B. Security & Compliance

### B1 — Security posture review
- **Trigger:** "What are my top security risks?"
- **Agents:** supervisor → security
- **Tools/Services:** AWS API MCP (read security config), knowledge base
- **Outcome:** Prioritized findings with context.

### B2 — Explain a specific finding
- **Trigger:** "Explain this exposed security group and how to fix it."
- **Agents:** supervisor → security → advisor
- **Tools/Services:** AWS API MCP, knowledge base
- **Outcome:** Plain-language explanation + concrete remediation steps.

### B3 — Compliance / config drift check _(latent)_
- **Trigger:** "Are we drifting from our security baseline?"
- **Agents:** supervisor → security
- **Tools/Services:** AWS API MCP; would benefit from AWS Config (not currently recording)
- **Outcome:** Drift report. **Note:** depends on enabling AWS Config.

### B4 — Credential / secret exposure triage
- **Trigger:** "Check whether any secrets are exposed."
- **Agents:** supervisor → security → investigator
- **Tools/Services:** AWS API MCP, CloudTrail (audit)
- **Outcome:** Exposure assessment and recommended rotation actions.

---

## C. Cost & Optimization

### C1 — Cost breakdown
- **Trigger:** "Where is my AWS spend going this month?"
- **Agents:** supervisor → cost
- **Tools/Services:** AWS API MCP (Cost Explorer / billing reads)
- **Outcome:** Spend by service/tag with trends.

### C2 — Optimization recommendations
- **Trigger:** "How can I reduce cost without hurting performance?"
- **Agents:** supervisor → cost → advisor
- **Tools/Services:** AWS API MCP, knowledge base
- **Outcome:** Rightsizing / commitment / cleanup suggestions with est. savings.

### C3 — Cost anomaly explanation
- **Trigger:** "Why did my bill jump yesterday?"
- **Agents:** supervisor → cost → investigator
- **Tools/Services:** AWS API MCP, CloudWatch
- **Outcome:** Attribution of the spike to a resource/change.

### C4 — Cost forecasting
- **Trigger:** "What will next quarter cost at this trajectory?"
- **Agents:** supervisor → cost (legacy `ForecastAgent` for forecasting)
- **Tools/Services:** AWS API MCP, historical usage data (S3/analytics)
- **Outcome:** Projected spend with assumptions.

---

## D. ITSM / Ticketing (Jira)

### D1 — Create a ticket from a conversation
- **Trigger:** "Open a Jira ticket for this disk-space issue."
- **Agents:** supervisor → jira
- **Tools/Services:** Jira (OpenAPI target via Gateway), Jira API key from Token Vault
- **Outcome:** New ticket with summary/description; ticket key returned.

### D2 — Look up ticket status
- **Trigger:** "What's the status of PROJ-1234?"
- **Agents:** supervisor → jira
- **Tools/Services:** Jira API
- **Outcome:** Current status, assignee, recent activity.

### D3 — Auto-file an incident with context
- **Trigger:** "This alarm is real — raise an incident with the details."
- **Agents:** supervisor → cloudwatch → investigator → jira
- **Tools/Services:** CloudWatch, Jira
- **Outcome:** Incident ticket pre-populated with metrics, logs, and RCA notes.

### D4 — Update / comment on a ticket
- **Trigger:** "Add the remediation plan to PROJ-1234 and mark it in progress."
- **Agents:** supervisor → jira
- **Tools/Services:** Jira API
- **Outcome:** Ticket updated with comment + transitioned state.

---

## E. Knowledge & Guidance

### E1 — Documentation Q&A
- **Trigger:** "How do we configure X per our runbook?"
- **Agents:** supervisor → knowledge
- **Tools/Services:** AWS Knowledge MCP, ITSM/GenAI data (S3)
- **Outcome:** Answer grounded in internal docs / AWS documentation.

### E2 — Best-practice advisory
- **Trigger:** "What's the recommended way to set up multi-AZ for this?"
- **Agents:** supervisor → advisor → knowledge
- **Tools/Services:** AWS Knowledge MCP, knowledge base
- **Outcome:** Recommended approach with rationale and trade-offs.

### E3 — How-to for an AWS task
- **Trigger:** "How do I enable versioning on this bucket?"
- **Agents:** supervisor → knowledge (or aws_api for a suggested command)
- **Tools/Services:** AWS Knowledge MCP, AWS API MCP (`suggest_aws_commands`)
- **Outcome:** Step-by-step guidance / suggested CLI commands.

---

## F. Cross-Domain / Composite

### F1 — "Full triage" of an incident
- **Trigger:** "Something's wrong with the app — investigate end to end and open a ticket."
- **Agents:** supervisor → cloudwatch → investigator → security → jira
- **Tools/Services:** CloudWatch, AWS API, Jira
- **Outcome:** Diagnosis, security check, and a filed incident with full context.

### F2 — Cost + security posture review
- **Trigger:** "Give me a monthly review: cost and security."
- **Agents:** supervisor → cost + security → advisor
- **Tools/Services:** AWS API MCP, knowledge base
- **Outcome:** Combined executive summary with prioritized actions.

### F3 — Change-impact assessment
- **Trigger:** "If I resize these instances, what happens to cost and performance?"
- **Agents:** supervisor → cost + cloudwatch → advisor
- **Tools/Services:** AWS API, CloudWatch
- **Outcome:** Projected cost delta + performance/risk assessment.

---

## Use-Case → Agent Coverage Matrix

| Use Case | supervisor | security | cost | cloudwatch | jira | knowledge | investigator | advisor |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| A1 Alarm investigation | ● | | | ● | | | ● | |
| A2 Health summary | ● | | | ● | | | | |
| A3 Log/error analysis | ● | | | ● | | | ● | |
| A4 RCA | ● | | | | | ○ | ● | |
| B1 Security posture | ● | ● | | | | | | |
| B2 Explain finding | ● | ● | | | | | | ● |
| B3 Compliance drift | ● | ● | | | | | | |
| B4 Secret triage | ● | ● | | | | | ● | |
| C1 Cost breakdown | ● | | ● | | | | | |
| C2 Optimization | ● | | ● | | | | | ● |
| C3 Cost anomaly | ● | | ● | | | | ● | |
| C4 Forecasting | ● | | ● | | | | | |
| D1 Create ticket | ● | | | | ● | | | |
| D2 Ticket status | ● | | | | ● | | | |
| D3 Auto-incident | ● | | | ● | ● | | ● | |
| D4 Update ticket | ● | | | | ● | | | |
| E1 Docs Q&A | ● | | | | | ● | | |
| E2 Best-practice | ● | | | | | ● | | ● |
| E3 AWS how-to | ● | | | | | ● | | |
| F1 Full triage | ● | ● | | ● | ● | | ● | |
| F2 Cost+security | ● | ● | ● | | | | | ● |
| F3 Change-impact | ● | | ● | ● | | | | ● |

● = primary agent · ○ = supporting/legacy agent

---

## Capability Notes & Caveats

- **Tool wiring:** the current repo scaffolding ships tool stubs for specialists;
  several use cases become fully functional once each specialist's `tools.py` is
  connected to the Gateway/MCP targets and boto3 reads.
- **Memory:** all live agents use short-term memory only, so use cases that would
  benefit from "learning from past incidents" (A4, F1) do not yet improve over time.
  Enabling episodic + reflection memory would materially help repetitive workflows.
- **Guardrails:** no Bedrock Guardrails are configured; for any use case that returns
  potentially sensitive output (B4, security/cost reports) add input+output guardrails
  before production use.
- **Dependencies:** B3 (compliance drift) needs AWS Config enabled; C1/C3 need Cost
  Explorer read permissions on the relevant runtime role.
```
