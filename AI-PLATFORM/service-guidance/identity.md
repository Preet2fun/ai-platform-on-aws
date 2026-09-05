# Service Guidance — Identity & Credentials

> How we handle auth + secrets. Source: skill `services/identity/` +
> `cross-service/credential-management.md`, `references/agentcore-oauth-integration.md`.

## Standard
- **All downstream secrets** (Jira, SIEM, PagerDuty, ServiceNow, cloud APIs) live in
  **AgentCore Identity credential providers** (token vault) — never env vars/code.
- **Workload identity per runtime**; fetch creds at runtime (`GetResourceApiKey` /
  `GetResourceOauth2Token`).
- **Three-layer OAuth**: inbound JWT (user/service auth), outbound credential provider
  (downstream), gateway OAuth. Cognito for inbound where applicable.
- Rotate credentials on a schedule; monitor usage.

## Best practices
- [ ] Inbound auth pattern per entry point (operators vs. automated systems)
- [ ] Credential provider inventory + rotation policy
- [ ] OAuth setup per external system

## POC gaps addressed
- POC uses token vault for Jira/Cognito — good. Formalize rotation + inventory.
