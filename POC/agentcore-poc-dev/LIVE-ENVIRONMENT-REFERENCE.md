# Live Environment Reference (deployed AgentCore resources)

> Captured from AWS account **`001961766007`**, region **`us-east-1`**, profile `agentcore`.
> Preserved here from the earlier live-discovery scaffold (`agents-repo/`, now removed) so
> the concrete deployed identifiers aren't lost. This developer repo is the authoritative
> **source code**; this file is the authoritative **map of what that code is deployed as**.
>
> For full architecture, see `../docs/AI-Platform-Architecture.md`.

## Account / region
- Account: `001961766007`
- Region: `us-east-1`
- CLI profile: `agentcore`
- Deploy artifact bucket: `bedrock-agentcore-codebuild-sources-001961766007-us-east-1`
  (per-runtime prefix: `<runtime_name>/deployment.zip`)

## Runtimes → protocol → memory ID

| Runtime (deployed name) | Protocol | AgentCore Memory ID |
|---|---|---|
| `dev_msp_supervisor_agent` | HTTP | `dev_msp_supervisor_agent_mem-C2TMffDFAR` |
| `dev_security_a2a_runtime` | A2A | `dev_security_a2a_runtime_mem-hkJu3MA8hs` |
| `dev_cost_a2a_runtime` | A2A | `dev_cost_a2a_runtime_mem-UXpOr667eu` |
| `dev_cloudwatch_a2a_runtime` | A2A | `dev_cloudwatch_a2a_runtime_mem-PYwaSVH1px` |
| `dev_jira_a2a_runtime` | A2A | `dev_jira_a2a_runtime_mem-PVi3gK3BY4` |
| `dev_knowledge_a2a_runtime` | A2A | `dev_knowledge_a2a_runtime_mem-DvPBPY5qbx` |
| `dev_investigator_a2a_runtime` | A2A | `dev_investigator_a2a_runtime_mem-kB61Zn9TLq` |
| `dev_advisor_a2a_runtime` | A2A | `dev_advisor_a2a_runtime_mem-oZJTST9cam` |
| `dev_aws_api_mcp` | MCP | `dev_aws_api_mcp_mem-F4oSyTDTO0` |
| `dev_aws_knowledge_mcp` | MCP | `dev_aws_knowledge_mcp_mem-6xHwJd8YPK` |
| `dev_cloudwatch_mcp` | MCP | `dev_cloudwatch_mcp_mem-cptNOZF8QR` |

> All per-runtime memories are **short-term only** (`strategies: []`, 30-day expiry). See
> `../docs/Memory.md` for the gap analysis. Two standalone memories
> (`dev_msp_assistant_memory`, `msp_assistant_memory`) carry SEMANTIC + SUMMARIZATION but
> are not referenced by any runtime.

## Gateway
- Dev gateway URL:
  `https://dev-msp-assistant-gateway-yamkzgvv48.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp`
- Gateway ID: `dev-msp-assistant-gateway-yamkzgvv48` (also older `msp-assistant-gateway-rfpnvicmgl`)
- Protocol: MCP · Authorizer: `AWS_IAM` · Execution role: `msp-gateway-execution-role`
  (⚠ currently `AdministratorAccess` — least-privilege remediation tracked in
  `../../AI-PLATFORM/guardrails/GAP-CHECKLIST.md`)
- Targets: `dev-aws-api-mcp`, `dev-cloudwatch-mcp`, `dev-aws-knowledge-mcp` (MCP_SERVER),
  `jira-mcp` (OPEN_API_SCHEMA)

## Identity / auth
- Cognito user pool: `us-east-1_vyWBkPHjd` (`dev-msp-assistant-users`)
  - M2M client (MCP JWT auth): `2t0feausc9empnuqq6lgns29bu`, scope `mcp-server/invoke`
  - Web client (SPA login): `494aepiof51n2ujbk71858f2ls`
- Credential providers (token vault): `dev-msp-gateway-cognito` (OAuth2),
  `msp-gateway-cognito` (OAuth2), `dev-jira-api-key` (API key)

## Runtime defaults (observed)
- Runtime: `PYTHON_3_11` · Network mode: `PUBLIC`
- Session: idle timeout `900s`, max lifetime `28800s` (8h)
- Model in use (typical): `us.anthropic.claude-sonnet-4-5-20250929-v1:0` (71 inference
  profiles enabled in the account)

## Environment variables (template)
```
AWS_REGION=us-east-1
AWS_PROFILE=agentcore
AWS_ACCOUNT_ID=001961766007
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0
# per-runtime (example: supervisor)
BEDROCK_AGENTCORE_MEMORY_ID=dev_msp_supervisor_agent_mem-C2TMffDFAR
BEDROCK_AGENTCORE_MEMORY_NAME=dev_msp_supervisor_agent_mem
AGENTCORE_GATEWAY_URL=https://dev-msp-assistant-gateway-yamkzgvv48.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp
COGNITO_USER_POOL_ID=us-east-1_vyWBkPHjd
COGNITO_M2M_CLIENT_ID=2t0feausc9empnuqq6lgns29bu
COGNITO_SCOPE=mcp-server/invoke
JIRA_API_KEY_PROVIDER=dev-jira-api-key
GATEWAY_OAUTH2_PROVIDER=dev-msp-gateway-cognito
```

_These are `dev` identifiers. Do not hardcode them in production code — prefer CDK outputs
/ SSM parameters (as this developer repo already does). This file is a reference map, not a
config source._
