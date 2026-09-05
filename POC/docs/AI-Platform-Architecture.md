# Motadata MSP AI Assistant — Architecture Notes

> **Source of truth:** Live discovery of AWS account `001961766007`, region `us-east-1`, captured 2026-08-31 via the `agentcore` CLI profile. Everything below reflects deployed resources, not intended design. Where a design intent is inferred, it is marked _(inferred)_.

---

## 1. Executive Summary

The platform is a **supervisor-orchestrated, multi-agent Agentic AI system** for MSP (Managed Service Provider) / ITSM operations, built on **Amazon Bedrock AgentCore**. A conversational web app fronts a containerized backend that dispatches user requests to a **supervisor agent**, which routes work to a fleet of **specialist agents** (security, cost, CloudWatch, Jira, knowledge, investigator, advisor). Specialists call tools exposed through an **AgentCore Gateway** (MCP) and directly via **MCP tool runtimes**, reaching Amazon Bedrock models plus external systems (Jira, AWS APIs, CloudWatch).

**Key characteristics**
- **Agent framework:** Amazon Bedrock AgentCore (Runtime, Gateway, Memory, Identity)
- **Orchestration pattern:** Supervisor → A2A (agent-to-agent) specialists → MCP tools
- **Compute:** ECS Fargate backend + AgentCore-managed serverless agent runtimes
- **Edge/UI:** CloudFront + S3 (SPA) + ALB
- **IaC:** AWS CDK (bootstrap `hnb659fds`)
- **Environment:** `dev` (an earlier POC exists in `ap-south-1`)

---

## 2. High-Level Architecture

```
                              ┌──────────────────────────────────────────────┐
                              │                   End User                    │
                              └───────────────────────┬──────────────────────┘
                                                      │ HTTPS
                                          ┌───────────▼───────────┐
                                          │   Amazon CloudFront    │  E2VJ4TEA44SIHK
                                          │  d2ci0urb01znvf.cf.net │
                                          └─────┬─────────────┬────┘
                            static SPA          │             │  /api/*
                       ┌────────────────────────▼──┐      ┌───▼──────────────────────┐
                       │  S3: frontend SPA bucket   │      │  ALB: dev-alb (public)   │
                       │  (React/SPA assets)        │      └───┬──────────────────────┘
                       └────────────────────────────┘          │  :8000
                                                     ┌──────────▼───────────────────────┐
                                                     │  ECS Fargate: dev-ecs-cluster     │
                                                     │  BackendService (2 tasks)         │
                                                     │  container :8000                  │
                                                     │  + EFS mount (shared state)       │
                                                     └──────────┬────────────────────────┘
                                    Cognito (auth)   │          │  invoke
                       DynamoDB (chat-requests) ◄────┤          │
                                                     │  ┌───────▼──────────────────────────┐
                                                     │  │ AgentCore Runtime: SUPERVISOR     │
                                                     │  │ dev_msp_supervisor_agent (HTTP)   │
                                                     │  └───────┬──────────────────────────┘
                                                     │          │ bedrock-agentcore:InvokeAgentRuntime
                       ┌─────────────────────────────┴──────────┼─────────────────────────────────────┐
                       │                A2A specialist runtimes (protocol = A2A)                        │
                       │  security · cost · cloudwatch · jira · knowledge · investigator · advisor      │
                       └───────┬───────────────────────────────────────────────────┬──────────────────┘
                               │ invoke tools (MCP)                                  │ InvokeModel
                   ┌───────────▼─────────────────────────┐              ┌───────────▼──────────────┐
                   │  AgentCore Gateway (MCP, AWS_IAM)    │              │   Amazon Bedrock          │
                   │  dev-msp-assistant-gateway          │              │   (Claude / Nova / etc.)  │
                   │  targets:                            │              └──────────────────────────┘
                   │   • dev-aws-api-mcp    (MCP_SERVER)  │
                   │   • dev-cloudwatch-mcp (MCP_SERVER)  │      ┌───────────────────────────────────┐
                   │   • dev-aws-knowledge  (MCP_SERVER)  │──────▶ External: Jira (API key),         │
                   │   • jira-mcp           (OPEN_API)    │      │ AWS Control-plane APIs, CloudWatch │
                   └──────────────────────────────────────┘      └───────────────────────────────────┘
                     MCP tool runtimes (protocol = MCP, Cognito JWT auth):
                       aws_api_mcp · aws_knowledge_mcp · cloudwatch_mcp
```

---

## 3. AgentCore Layer (the core of the platform)

### 3.1 Agent Runtimes (15 total)

All runtimes: **Python 3.11**, code pulled from S3 `bedrock-agentcore-codebuild-sources-001961766007-us-east-1`, built via **CodeBuild**, network mode **PUBLIC**, session limits **idle 900s / max lifetime 28800s (8h)**, IMDSv2 required. Each runtime has its **own IAM role, workload identity, and Memory resource**.

| Runtime | Protocol | Role | Purpose _(inferred)_ |
|---|---|---|---|
| `dev_msp_supervisor_agent` | **HTTP** | supervisor | Orchestrator; routes requests to specialists |
| `dev_security_a2a_runtime` | A2A | specialist | Security posture / findings analysis |
| `dev_cost_a2a_runtime` | A2A | specialist | Cost analysis / optimization |
| `dev_cloudwatch_a2a_runtime` | A2A | specialist | Metrics / logs / alarms reasoning |
| `dev_jira_a2a_runtime` | A2A | specialist | Ticket management |
| `dev_knowledge_a2a_runtime` | A2A | specialist | Knowledge base / doc Q&A |
| `dev_investigator_a2a_runtime` | A2A | specialist | Incident investigation / RCA |
| `dev_advisor_a2a_runtime` | A2A | specialist | Recommendations / advisory |
| `dev_aws_api_mcp` | **MCP** | tool server | `call_aws` / `suggest_aws_commands` (awslabs) |
| `dev_cloudwatch_mcp` | **MCP** | tool server | CloudWatch MCP (awslabs) |
| `dev_aws_knowledge_mcp` | **MCP** | tool server | AWS Knowledge search |
| `MotadataAgents_RCAAgent` | — | legacy | Earlier standalone RCA agent (v10) |
| `MotadataAgents_ForecastAgent` | — | legacy | Earlier forecasting agent (v10) |
| `MotadataAgents_MotadataAgents` | — | legacy | Earlier monolithic agent (v19) |

> The three `MotadataAgents_*` runtimes predate the current `dev_*` A2A design (last updated June 2026 vs. Aug 2026). They appear to be **legacy / superseded** by the specialist-agent architecture. _(inferred)_

### 3.2 Protocols

- **HTTP** — supervisor entry point (called by the backend)
- **A2A** — agent-to-agent protocol for supervisor→specialist calls
- **MCP** — Model Context Protocol for tool servers

### 3.3 Gateways (2)

| Gateway | Auth | Protocol | Role | URL |
|---|---|---|---|---|
| `dev-msp-assistant-gateway` | AWS_IAM | MCP | `msp-gateway-execution-role` | `https://dev-msp-assistant-gateway-yamkzgvv48.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp` |
| `msp-assistant-gateway` | AWS_IAM | MCP | — | (older/prod-candidate) |

**Gateway targets (dev):**

| Target | Type | Purpose |
|---|---|---|
| `dev-aws-api-mcp` | MCP_SERVER | AWS API MCP (call_aws, suggest_aws_commands) |
| `dev-cloudwatch-mcp` | MCP_SERVER | CloudWatch MCP |
| `dev-aws-knowledge-mcp` | MCP_SERVER | AWS Knowledge search |
| `jira-mcp` | OPEN_API_SCHEMA | Jira ticket management (OpenAPI-defined) |

### 3.4 Memory (14 resources)

One AgentCore **Memory** resource per agent (short-term events + long-term records), all `ACTIVE`. Runtimes reference their memory via env vars `BEDROCK_AGENTCORE_MEMORY_ID` / `_NAME`. Examples: `dev_msp_supervisor_agent_mem`, `dev_security_a2a_runtime_mem`, etc. Older non-`dev` memories (`msp_assistant_memory`, `msp_supervisor_agent_mem`) remain from the prior deployment.

### 3.5 Identity & Credential Providers

- **Workload identities:** one per runtime + one per gateway (AgentCore Identity directory `default`).
- **OAuth2 credential providers (CustomOauth2):** `dev-msp-gateway-cognito`, `msp-gateway-cognito` — Cognito-backed gateway auth.
- **API-key credential provider:** `dev-jira-api-key` — Jira access.
- All three are stored in **Secrets Manager** under the AgentCore Identity token vault; agents fetch them at runtime via `GetResourceApiKey` / `GetResourceOauth2Token`.
- **Not deployed:** Code Interpreter, Browser (IAM permits code-interpreter use, but none provisioned).

---

## 4. Application Layer (front-to-back request path)

### 4.1 Edge / Frontend
- **CloudFront** `E2VJ4TEA44SIHK` (`d2ci0urb01znvf.cloudfront.net`) with two origins:
  1. **S3** SPA bucket (`dev-msp-assistant-fronten-frontends3bucket…`) — static web app.
  2. **ALB** `dev-alb` — API traffic.
- CloudFront + LB access logging enabled (dedicated S3 logging buckets).

### 4.2 Backend
- **ALB** `dev-alb` (internet-facing) → target group → **ECS Fargate** service on cluster `dev-ecs-cluster`.
- **Service:** `desiredCount=2` (2 running tasks), container `BackendService-container` on **port 8000**, task definition `dev-msp-assistant-task-definition:16`.
- **Image:** ECR repo `dev-msp-assistant-backend`.
- **Shared state:** encrypted **EFS** (`fs-0b3bfb52a50510440`) mounted to tasks.
- The backend authenticates users via **Cognito**, persists chat requests to **DynamoDB**, and invokes the **AgentCore supervisor** over HTTP. _(inferred from IAM + resources)_

### 4.3 API Gateway
- **REST API** `dev-msp-assistant-api` (`z9a1xpios1`) present alongside the ALB path _(role in the request flow to be confirmed against the CDK stack — possibly async/callback or an alternate entry)_.

### 4.4 Lambda
- Only **2 functions**, both **CDK custom-resource helpers** (S3 auto-delete, bucket deployment). **No application logic runs in Lambda** — the app is container-based.

---

## 5. Data & Storage

| Store | Resource | Notes |
|---|---|---|
| **DynamoDB** | `dev-msp-assistant-chat-requests` | PK `request_id`, PAY_PER_REQUEST, no GSI/stream/TTL. Chat request correlation store. |
| **S3 (data)** | `motadata-itsm-genai-data` | `raw/` + `notebooks/` — ITSM data + prep notebooks |
| **S3 (eval)** | `motadata-llm-judge` | `llm-judge/`, `project/`, `sample-data/` — LLM-as-judge evaluation harness |
| **S3 (analytics)** | `lakeformation-workshop-*` (+ athena-results) | Lake Formation / Athena analytics |
| **S3 (deploy)** | `bedrock-agentcore-codebuild-sources-…` | 14 runtime `deployment.zip` artifacts (one prefix per agent) |
| **S3 (app)** | frontend SPA + CloudFront/ALB logging buckets | |
| **S3 (governance)** | CloudTrail logs, Config bucket | |
| **Secrets Manager** | 3 secrets | All AgentCore Identity token-vault backed (2 OAuth2 + 1 API key) |

**Not present in-region:** RDS/Aurora, OpenSearch (managed or serverless). No vector database was found — retrieval/knowledge is served via the AWS Knowledge MCP + S3 data, not a self-managed vector store. _(inferred)_

---

## 6. Networking

**VPC `dev-vpc`** (`10.0.0.0/16`, non-default), 3-tier across AZs `us-east-1a/b/c`:

| Tier | Subnets | Hosts |
|---|---|---|
| Public | `dev-public-subnet-0/1/2` | ALB, NAT Gateway |
| Private (app) | `dev-private-app-subnet-0/1/2` | ECS Fargate tasks |
| Private (db) | `dev-private-db-subnet-0/1/2` | Reserved (currently unused — no RDS) |

- **NAT Gateway:** 1 (single-AZ egress).
- **VPC Endpoints:** S3 (Gateway) + Interface endpoints for `monitoring`, `logs`, `ecr.api`, `ecr.dkr` — Fargate pulls images and ships logs/metrics privately.
- **Security groups:** ALB SG, backend service SG, VPC-endpoints SG, EFS inbound/outbound NFS SGs.
- A **default VPC** (`172.31.0.0/16`) also exists but is unused by the platform.

> **Note:** AgentCore runtimes run in **PUBLIC** network mode (AgentCore-managed network), not inside `dev-vpc`. Only the ECS backend and its data/mount resources live in the VPC.

---

## 7. Identity, Authentication & Authorization

- **End-user auth:** Cognito user pool `dev-msp-assistant-users` (`us-east-1_vyWBkPHjd`).
  - `UserPoolWebClient` (`494aepiof51n2ujbk71858f2ls`) — SPA login.
  - `UserPoolM2MClient` (`2t0feausc9empnuqq6lgns29bu`) — machine-to-machine client credentials; issues JWTs for MCP runtime authorization (scope `mcp-server/invoke`).
- **MCP runtime authorization:** custom JWT authorizer validating Cognito tokens (discovery URL on pool `us-east-1_vyWBkPHjd`).
- **Gateway authorization:** AWS_IAM (SigV4).
- **Runtime IAM model:** each runtime has a dedicated `AmazonBedrockAgentCoreSDKRuntime-*` role. The **supervisor** additionally holds `InvokeA2ASpecialists` (`bedrock-agentcore:InvokeAgentRuntime` on `runtime/*`) — the IAM expression of the orchestration pattern.
- **Runtime execution permissions include:** `bedrock:InvokeModel` / `InvokeModelWithResponseStream` / `ApplyGuardrail`; full Memory ops; CloudWatch Logs + X-Ray + metrics; `GetResourceApiKey` / `GetResourceOauth2Token` / `secretsmanager:GetSecretValue`; `sts:GetWebIdentityToken` (workload identity token exchange).

---

## 8. AI / Model Layer

- **Amazon Bedrock**, accessed via cross-region **inference profiles** (71 enabled), spanning:
  - **Anthropic Claude** — 3 Sonnet/Haiku through **Sonnet 4.5/4.6** and **Opus 4.1/4.5/4.7**
  - **Meta Llama** 3.1–3.3, **Amazon Nova** (incl. Nova 2 Lite / Premier), **DeepSeek-R1**, **Mistral Pixtral**
  - Embeddings: **Cohere Embed v4**, **TwelveLabs Marengo**; image: **Stability** family
- Agents invoke models through `bedrock:InvokeModel` (streaming supported). Specific per-agent model selection lives in the deployment code (not exposed via control-plane APIs).
- **LLM evaluation:** `motadata-llm-judge` S3 bucket indicates an LLM-as-judge quality harness.

---

## 9. Observability & Governance

- **CloudWatch Logs:** per-runtime log groups `/aws/bedrock-agentcore/runtimes/<runtime>-DEFAULT` (multiple versions retained), per-runtime CodeBuild builder logs, Glue log groups (pre-provisioned), plus `/aws/application-signals/data`.
- **Application Signals (APM):** enabled.
- **X-Ray:** tracing wired via IAM on every runtime (`PutTraceSegments`, sampling). Service graph was empty at capture (no live traffic).
- **CloudTrail:** 2 multi-region trails — org `management-events` → central account `960324207840`, plus local `poc-cloudtrail` → `aws-cloudtrail-logs-001961766007`. Indicates an **organization / landing-zone** setup.
- **AWS Config:** no configuration recorder in this region.

---

## 10. Deployment & IaC

- **AWS CDK** throughout (bootstrap `cdk-hnb659fds-*`, `CustomCDKBucketDeployment` / `CustomS3AutoDeleteObjects` custom resources).
- CDK stacks _(inferred from resource naming):_ `dev-msp-assistant-frontend*`, `dev-msp-assistant-backend-stack`, plus AgentCore resources deployed via the AgentCore SDK/CodeBuild pipeline.
- Agent code is packaged to S3 and built per-runtime by CodeBuild (`bedrock-agentcore-<runtime>-builder` projects).
- Prior **POC** deployment in `ap-south-1` (`pocassistantfrontendstack`, `poc-alb`, `poc-agentcore-assets-*`) — candidate for cleanup.

---

## 11. End-to-End Request Flow

1. User loads the SPA from **CloudFront → S3**, authenticates via **Cognito** (web client).
2. SPA calls the API via **CloudFront → ALB → ECS Fargate** backend (port 8000).
3. Backend records the request in **DynamoDB** (`chat-requests`) and invokes the **supervisor** AgentCore runtime (HTTP).
4. **Supervisor** reasons over the request (Bedrock model + its Memory) and routes to one or more **specialist agents** via **A2A** (`InvokeAgentRuntime`).
5. Specialists call tools through the **AgentCore Gateway** (MCP, AWS_IAM) and/or the **MCP tool runtimes** (Cognito JWT). Tools reach **AWS APIs, CloudWatch, and Jira** (credentials fetched from the AgentCore Identity token vault).
6. Specialists invoke **Bedrock** models as needed, persist context to their **Memory**, and return results up to the supervisor.
7. Supervisor composes the final answer; backend streams/returns it to the SPA. Traces flow to **X-Ray / Application Signals**, logs to **CloudWatch**.

---

## 12. Findings & Recommendations

Ordered by priority. These are drawn from the live inventory.

| # | Severity | Finding | Recommendation |
|---|---|---|---|
| 1 | **High** | `msp-gateway-execution-role` has `AdministratorAccess` attached. | Replace with a least-privilege policy scoped to invoking the specific MCP targets / required services. |
| 2 | **High** | Long-lived AWS access key was embedded in `~/.kiro/settings/mcp.json` and shared in-session. | **Rotate the key now**; move to SSO or a named profile; remove secrets from config files. |
| 3 | **Medium** | No **Bedrock Guardrails** configured, though runtimes hold `ApplyGuardrail`. | Define guardrails (PII, denied topics, prompt-injection filters) and attach to model invocations. |
| 4 | **Medium** | Single **NAT Gateway** (one AZ). | Deploy one NAT per AZ for HA egress (if backend availability matters). |
| 5 | **Medium** | **AWS Config** has no recorder in-region. | Enable Config + conformance packs for drift/compliance tracking. |
| 6 | **Low/Med** | **CloudWatch log retention = never** on all groups (125). | Set retention (e.g., 30–90d) to control cost and meet data-retention policy. |
| 7 | **Low** | **Legacy** `MotadataAgents_*` runtimes and `ap-south-1` POC stacks remain. | Decommission if superseded to reduce cost and attack surface. |
| 8 | **Low** | AgentCore runtimes use **PUBLIC** network mode. | If tools/data must stay private, evaluate VPC network mode for runtimes. |
| 9 | **Info** | No customer-managed **KMS** keys (AWS-managed encryption only). | Consider CMKs where compliance requires key ownership/rotation control. |

---

## 13. Component Inventory (quick reference)

| Category | Count / Key Resources |
|---|---|
| AgentCore runtimes | 15 (1 supervisor, 7 A2A specialists, 3 MCP tools, 3 legacy) |
| AgentCore gateways | 2 (MCP, AWS_IAM) |
| AgentCore memories | 14 (per-agent) |
| Credential providers | 3 (2 OAuth2 Cognito, 1 Jira API key) |
| ECS | 1 cluster (`dev-ecs-cluster`), 1 Fargate service (2 tasks) |
| ECR | `dev-msp-assistant-backend` (+ CDK assets repo) |
| ALB | `dev-alb` (internet-facing) |
| CloudFront | 2 (active `E2VJ4TEA44SIHK`; POC `E2KKBKVV0SMTV0` in ap-south-1) |
| API Gateway | 1 REST (`dev-msp-assistant-api`) |
| Lambda | 2 (CDK custom resources only) |
| DynamoDB | 1 table (`dev-msp-assistant-chat-requests`) |
| S3 | 20 buckets |
| VPC | 1 platform VPC (`dev-vpc`, 3-tier, 3 AZ) + default |
| Cognito | 1 user pool, 2 clients |
| Bedrock | 71 inference profiles enabled; 0 guardrails |
| CloudWatch log groups | 125 (retention: never) |
| CloudTrail | 2 multi-region trails |
| AWS Config | 0 recorders |
| KMS CMKs | 0 |

---

_Generated from live AWS discovery. Items marked “(inferred)” combine control-plane evidence with reasonable interpretation; validate against the CDK source and agent code for internal wiring (e.g., exact per-agent model IDs, API Gateway role, and supervisor→specialist routing logic)._
