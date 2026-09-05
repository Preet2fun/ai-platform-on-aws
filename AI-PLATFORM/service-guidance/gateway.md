# Service Guidance — Gateway & Tools

> How we expose ops/security systems as agent tools. Source: skill `services/gateway/`.

## Standard
- External systems (telemetry, SIEM, ticketing, CMDB, cloud control) exposed as **MCP
  tools via the Gateway** — specialists never hardcode integrations.
- **Auth per target type:** IAM (Lambda), OAuth (MCP servers), API key (via Identity).
- **Least-privilege gateway execution role** (POC gap: was `AdministratorAccess`).
- Gateway lifecycle via CDK custom resource (`scripts/gateway-custom-resource-lambda.py`).
- Validate every target (`services/gateway/validate-deployment.sh`) before use.

## Best practices
- [ ] Target catalog (system → target type → auth → owning agent)
- [ ] Deployment strategy per target (ref: `deployment-strategies.md`)
- [ ] Troubleshooting runbook (ref: `troubleshooting-guide.md`)

## POC gaps addressed
- Scope the gateway role down from admin to per-target least privilege.
