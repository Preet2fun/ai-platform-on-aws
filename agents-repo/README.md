# Motadata MSP AI Assistant — Agents Monorepo

LangGraph-based source for the multi-agent system deployed on **Amazon Bedrock AgentCore**
(AWS account `001961766007`, region `us-east-1`).

This repo is the **canonical source** for the agent code. AWS only stores the *built*
artifacts (`deployment.zip` per runtime) in S3
(`bedrock-agentcore-codebuild-sources-001961766007-us-east-1/<runtime>/deployment.zip`);
there is no CodeCommit repo. Deploy from here.

## Architecture at a glance

```
Backend (ECS Fargate)
      │  HTTP
      ▼
┌─────────────────────┐   A2A (bedrock-agentcore:InvokeAgentRuntime)
│  Supervisor agent   │ ─────────────────────────────────────────────┐
│  (LangGraph router) │                                               │
└─────────────────────┘                                               ▼
                              ┌───────────────────────────────────────────────────┐
                              │  A2A specialist agents (LangGraph)                  │
                              │  security · cost · cloudwatch · jira ·              │
                              │  knowledge · investigator · advisor                 │
                              └───────────────────┬───────────────────────────────┘
                                                  │  MCP
                              ┌───────────────────▼───────────────────────────────┐
                              │  MCP tool servers  aws_api · aws_knowledge · cw    │
                              │  + AgentCore Gateway targets (Jira, AWS APIs)      │
                              └────────────────────────────────────────────────────┘
                                                  │
                                                  ▼   Amazon Bedrock (Claude/Nova/...)
```

Each agent maps 1:1 to a deployed AgentCore Runtime. Protocols match the deployment:
supervisor = **HTTP**, specialists = **A2A**, tool servers = **MCP**.

## Layout

```
agents-repo/
├── agents/
│   ├── supervisor/                 # dev_msp_supervisor_agent  (HTTP)
│   ├── security_a2a/               # dev_security_a2a_runtime  (A2A)
│   ├── cost_a2a/                   # dev_cost_a2a_runtime       (A2A)
│   ├── cloudwatch_a2a/             # dev_cloudwatch_a2a_runtime (A2A)
│   ├── jira_a2a/                   # dev_jira_a2a_runtime       (A2A)
│   ├── knowledge_a2a/              # dev_knowledge_a2a_runtime  (A2A)
│   ├── investigator_a2a/           # dev_investigator_a2a_runtime (A2A)
│   ├── advisor_a2a/                # dev_advisor_a2a_runtime    (A2A)
│   ├── aws_api_mcp/                # dev_aws_api_mcp            (MCP)
│   ├── aws_knowledge_mcp/          # dev_aws_knowledge_mcp      (MCP)
│   └── cloudwatch_mcp/             # dev_cloudwatch_mcp         (MCP)
├── libs/
│   └── common/                     # shared LangGraph + AgentCore glue
├── scripts/
│   └── deploy.sh                   # build + push deployment.zip per runtime
├── pyproject.toml
├── requirements.txt
├── Makefile
├── .env.example
└── .gitignore
```

## Prerequisites

- Python 3.11 (matches the AgentCore runtime `PYTHON_3_11`)
- AWS credentials with the `agentcore` profile
- `uv` or `pip` for dependency management

## Quick start

```bash
cp .env.example .env          # fill in IDs (region, memory ids, cognito, gateway url)
make install                  # install deps + shared lib (editable)
make run-supervisor           # run the supervisor locally
make test                     # run tests
```

## Deploy

```bash
# Build and push one runtime's deployment.zip to S3 (used by the AgentCore build)
./scripts/deploy.sh supervisor
./scripts/deploy.sh security_a2a
# ...or all:
make deploy-all
```

> Deployment uses the AgentCore SDK/CLI build flow: the runtime code is zipped, uploaded
> to the codebuild-sources S3 bucket, and CodeBuild produces the runtime image. See
> `scripts/deploy.sh` and each agent's `agentcore.yaml`.

## Environment / config

All runtime configuration is via environment variables (see `.env.example`), matching the
deployed runtimes' env vars — notably `BEDROCK_AGENTCORE_MEMORY_ID` and
`BEDROCK_AGENTCORE_MEMORY_NAME`.
