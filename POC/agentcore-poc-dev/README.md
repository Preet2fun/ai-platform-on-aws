# Motadata AI-Powered RCA Agent

Multi-agent Root Cause Analysis system that correlates telemetry data (metrics, logs, traces) across services to identify root causes automatically.

**Flow:** User → CloudFront → API Gateway → ALB → ECS (FastAPI) → AgentCore Supervisor → Specialist Agents → Response  
**Processing time:** 30–50s per query (warm), 60–70s (cold start)

### How it works

The backend returns a `request_id` immediately (under 100ms) and processes the AI request asynchronously. A background task invokes the Supervisor agent on AgentCore, which routes the query to the appropriate specialist via A2A protocol. The frontend polls or streams results via SSE.

### Key Features

- Multi-agent orchestration (1 Supervisor + 7 Specialists + 3 MCP servers)
- Automated Root Cause Analysis with 8-step investigation
- Multi-tenant isolation (STS AssumeRole + Secrets Manager per customer)
- Real-time SSE streaming for chat responses
- 5-step alarm remediation workflow with human approval gates
- AgentCore Memory for cross-session conversational recall
- AWS operation allowlist — blocks writes/deletes; sensitive data-plane reads (object/log contents) gated behind an opt-in flag

---

## Prerequisites

- [AWS CLI v2.33.8+](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) (verify: `aws --version`). Windows: use WSL2.
- [Docker](https://docs.docker.com/get-docker/)
- [Python 3.11+](https://www.python.org/downloads/)
- [Node.js 18+](https://nodejs.org/)

The AgentCore CLI toolkit is installed automatically via `pip install -r requirements.txt`.

**AWS IAM:** the deployer needs standard permissions to create the app's infrastructure
(CloudFormation/CDK, ECS, DynamoDB, S3, Cognito, API Gateway, IAM roles, Bedrock AgentCore).
`deploy.sh` also sets a one-time, account-level API Gateway CloudWatch Logs role, which
additionally needs `apigateway:GET/PATCH` on `/account` and `iam:CreateRole`,
`iam:AttachRolePolicy`, `iam:GetRole`, `iam:PassRole`. If those are unavailable, deploy.sh
skips the step and prints the exact one-time commands for an admin to run.

---

## Setup

This is a cloud-native application — it runs on AWS, not locally.

```bash
# 1. Clone
git clone https://github.com/vynkatesh-sinhasane-comprinno/Motadata-Gen-AI-Poc.git
cd Motadata-Gen-AI-Poc
cd msp-ops-langgraph

# 2. Install dependencies
cd backend
python3.11 -m venv .venv        # Must be 3.11+, not system default
source .venv/bin/activate
pip install -r requirements.txt
pytest -v                        # Verify setup (no AWS creds needed)
cd ../frontend
npm install
cd ..

# 3. Configure
aws sso login --profile <your-aws-profile>
export AWS_PROFILE=<your-aws-profile>    # deploy.sh uses this for AWS credentials
cp backend/.env.example backend/.env
```

Edit `backend/.env` — fill in these 4 values:

| Variable | How to Get |
|----------|-----------|
| `JIRA_DOMAIN` | Your Jira instance URL (e.g. `https://company.atlassian.net`) |
| `JIRA_EMAIL` | Your Atlassian account email |
| `JIRA_API_TOKEN` | [Create API token](https://id.atlassian.com/manage-profile/security/api-tokens) |
| `JIRA_PROJECT_KEY` | From your Jira project URL (e.g. `OPS`) |

All other values are auto-populated by the deploy script.

```bash
# 4. Deploy (~60-90 minutes)
./deploy.sh --email <your-email> --region <AWS_REGION> --env dev
```

`--env` (default `dev`) prefixes all resource names — e.g. `dev-msp-assistant-api`, `dev_msp_supervisor_agent`. Use different values (`dev`, `staging`, `prod`) to run isolated environments in the same account.

After deployment completes, the script outputs:
```
Frontend URL: https://<cloudfront-id>.cloudfront.net
Email: <your-email>
Temporary password: Temp1XXXXXXXXX!
```

Sign in and change your password on first login.

---

## Project Structure

```
├── agents/
│   ├── shared/                      # Canonical shared modules (single source of truth)
│   ├── runtime/                     # Supervisor agent
│   ├── runtime_cloudwatch/          # CloudWatch specialist
│   ├── runtime_security/            # Security specialist
│   ├── runtime_cost/                # Cost specialist
│   ├── runtime_advisor/             # Advisor specialist
│   ├── runtime_jira/                # Jira specialist
│   ├── runtime_knowledge/           # Knowledge specialist
│   ├── runtime_investigator/        # RCA Investigator
│   └── sync_shared.sh              # Copies shared/ to all agents before deploy
├── backend/
│   ├── requirements.txt           # Pinned Python dependencies
│   ├── Dockerfile                 # ECS container build
│   ├── app/core/config.py          # Centralized config (pydantic-settings)
│   ├── app/core/langgraph_client.py # AgentCore Runtime invocation client
│   ├── app/core/task_registry.py   # Background task lifecycle management
│   ├── app/api/routes.py           # FastAPI endpoints
│   └── tests/                      # pytest suite (8 test files)
├── frontend/
│   └── src/                        # React app
├── deploy.sh                       # Full deployment script
└── backend/.env.example            # Environment variable template
```

---

## Configuration

Backend uses `pydantic-settings` (`backend/app/core/config.py`). Agents use `os.environ[]`.

### Backend Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AWS_REGION` | Yes | AWS region for all service calls |
| `COGNITO_USER_POOL_ID` | Yes | Cognito User Pool for JWT validation |
| `COGNITO_CLIENT_ID` | Yes | Cognito App Client ID |
| `SUPERVISOR_RUNTIME_ARN` | Yes | AgentCore Supervisor runtime ARN |
| `GATEWAY_URL` | Yes | AgentCore Gateway MCP endpoint |
| `MEMORY_ID` | Yes | AgentCore Memory resource ID |
| `MODEL` | No | LLM model ID (default: `claude-haiku-4-5`) |
| `FRONTEND_URL` | No | CORS origin (default: `http://localhost:5173`) |
| `CLOUDFRONT_DOMAIN` | No | Production CloudFront domain for CORS |
| `CHAT_REQUESTS_TABLE` | No | DynamoDB table name (default: `msp-assistant-chat-requests`) |
| `CONVERSATIONS_TABLE` | No | DynamoDB table for chat history (auto-set by deploy.sh, e.g. `dev-msp-assistant-conversations`) |
| `OTEL_ENABLED` | No | Enable OpenTelemetry tracing (default: `false`) |

### Specialist ARNs

| Variable | Required | Description |
|----------|----------|-------------|
| `CLOUDWATCH_A2A_ARN` | No | CloudWatch specialist runtime ARN |
| `SECURITY_A2A_ARN` | No | Security specialist runtime ARN |
| `COST_A2A_ARN` | No | Cost specialist runtime ARN |
| `ADVISOR_A2A_ARN` | No | Advisor specialist runtime ARN |
| `JIRA_A2A_ARN` | No | Jira specialist runtime ARN |
| `KNOWLEDGE_A2A_ARN` | No | Knowledge specialist runtime ARN |
| `INVESTIGATOR_A2A_ARN` | No | RCA Investigator runtime ARN |

### Agent Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AWS_REGION` | Yes | Set automatically by AgentCore |
| `GATEWAY_URL` | Yes | AgentCore Gateway MCP endpoint |
| `MODEL_ID` | No | LLM model (default: `claude-haiku-4-5`) |

---

## Secrets & Parameters

| Type | Secret Path | Format | Used By |
|------|-------------|--------|---------|
| Secrets Manager | `msp-credentials/<account-name>` | `{"access_key_id", "secret_access_key", "session_token", "expires_at", "account_id", "role_name", "external_id"}` | Backend (STS credential cache per tenant) |
| Env var | `DATABASE_URL` | `postgresql://<user>:<pass>@<host>:<port>/<db>` | Investigator agent (telemetry DB connection; set via `agentcore deploy --env`) |
| Cognito | User Pool + App Client | JWT tokens | Frontend auth, backend validation |

**No hardcoded credentials anywhere.** All AWS service calls use IAM role-based auth (ECS task role / AgentCore execution role). Tenant credentials are generated via STS AssumeRole and cached in Secrets Manager with auto-refresh.

---
## Testing

```bash
cd backend
pytest -v                    # Run all tests
pytest tests/test_auth_flow.py -v  # Run single file
```

No real AWS credentials needed — tests use mocks (unittest.mock).

### Verify in UI

After deployment, sign in and try these queries to verify each agent:

| Query | Expected Agent |
|-------|---------------|
| "Do I have any active alarms?" | CloudWatch |
| "Show me critical security findings" | Security |
| "What's my AWS spend this month?" | Cost |
| "What are my Trusted Advisor recommendations?" | Advisor |
| "Investigate checkout service latency" | Investigator (RCA) |

Responses should show agent type badges and return real AWS data.

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/chat` | JWT | Submit chat message (async) |
| GET | `/api/v1/chat/{id}` | JWT | Poll chat result |
| GET | `/api/v1/chat/{id}/stream` | JWT | SSE stream for chat |
| GET | `/api/v1/conversations` | JWT | List conversations |
| POST | `/api/v1/conversations` | JWT | Create conversation |
| GET | `/api/v1/accounts` | JWT | List tenant accounts |
| POST | `/api/v1/accounts` | JWT | Register new account |
| POST | `/api/v1/auth/set-refresh` | None | Store refresh token cookie |
| POST | `/api/v1/auth/restore` | Cookie | Restore session from cookie |
| POST | `/api/v1/auth/logout` | None | Clear session cookies |
| GET | `/health` | None | Health check |

---

## Operations Quick Reference

```bash
# Redeploy backend (after code change)
cd backend
docker build --platform linux/amd64 -t <AWS_ACCOUNT_ID>.dkr.ecr.<AWS_REGION>.amazonaws.com/<BACKEND_IMAGE>:latest -f Dockerfile ..
docker push <AWS_ACCOUNT_ID>.dkr.ecr.<AWS_REGION>.amazonaws.com/<BACKEND_IMAGE>:latest
aws ecs update-service --cluster <ECS_CLUSTER> --service <ECS_SERVICE> --force-new-deployment --region <AWS_REGION>

# Redeploy agents (after agent code change)
cd agents && ./sync_shared.sh && cd runtime
agentcore deploy --auto-update-on-conflict

# Redeploy frontend (after UI change)
cd frontend && npm run build
aws s3 sync dist/ s3://<FRONTEND_BUCKET>/ --delete
aws cloudfront create-invalidation --distribution-id <DISTRIBUTION_ID> --paths "/*"

# Tail backend logs
aws logs tail /ecs/<ECS_SERVICE> --follow --region <AWS_REGION>

# Check AgentCore runtime status
aws bedrock-agentcore-control list-agent-runtimes --region <AWS_REGION> --output table

# Test supervisor directly
echo '{"prompt":"What alarms are active?","account_name":"default"}' > /tmp/q.json
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn <SUPERVISOR_RUNTIME_ARN> \
  --payload fileb:///tmp/q.json /tmp/resp.json \
  --cli-read-timeout 180 --region <AWS_REGION>
cat /tmp/resp.json

# Refresh tenant credentials
aws secretsmanager get-secret-value --secret-id msp-credentials/<account-name> --region <AWS_REGION>
```

---

## Security

| Control | Implementation |
|---------|---------------|
| Authentication | Cognito JWT on every request |
| Session isolation | Memory namespaced by `actorId` (Cognito sub) |
| Tenant isolation | STS AssumeRole per customer + contextvars |
| API protection | Rate limiting (slowapi) + input sanitization |
| Agent safety | Operation allowlist: writes/deletes blocked; data-plane reads (S3/log contents, IAM policy docs) opt-in via `ALLOW_SENSITIVE_DATA_READS` |
| Credential storage | Secrets Manager (no hardcoded secrets) |
| Network | HTTPS everywhere, SigV4 for Gateway |
| Monitoring | CloudTrail + Security Hub + GuardDuty |

---

## Clean Up

Ensure your AWS session is active first (`aws sso login --profile <profile>` and
`export AWS_PROFILE=<profile>`), then verify with `aws sts get-caller-identity`.
Without valid credentials the teardown cannot delete resources.

```bash
./destroy.sh --region <AWS_REGION> --force
```

Removes all deployed resources: AgentCore runtimes, ECS, CDK stacks, S3, DynamoDB, Cognito, IAM roles, and Secrets Manager entries.

---

## Further Reading

- [runbooks/](./runbooks/) — AWS operational runbooks (ECS failures, DynamoDB throttling, Lambda, RDS, etc.)

---

Built by **Comprinno Technologies** for Motadata (Mindarray Systems Pvt Ltd).
