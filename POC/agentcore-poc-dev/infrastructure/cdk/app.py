#!/usr/bin/env python3
"""
MSP Assistant AgentCore Migration - CDK App Entry Point
========================================================
Orchestrates the three-stack deployment for the MSP Ops Automation platform.

Stack deployment order (enforced by add_dependency):
  1. AgentCoreStack  — AgentCore Memory, Gateway, Observability.
                       Deployed first; exports ARNs consumed by BackendStack.
                       Resources are created imperatively via boto3 (CDK L2
                       constructs for AgentCore are not yet available).

  2. BackendStack    — ECS Fargate service + ALB + API Gateway + Cognito.
                       Receives agentcore_resources dict (ARNs/IDs) from
                       AgentCoreStack and bakes them into ECS environment vars.
                       Depends on: AgentCoreStack.

  3. FrontendStack   — React SPA on S3 + CloudFront CDN.
                       Receives the API Gateway URL and Cognito config from
                       BackendStack at synthesis time, and embeds them in a
                       runtime config.json served alongside the SPA.
                       Depends on: BackendStack.

Context variables (passed via --context or cdk.json):
  account                 — AWS account ID (defaults to CDK caller account)
  region                  — AWS region (defaults to us-east-1)
  supervisor_runtime_arn  — AgentCore Supervisor Runtime ARN (set by deploy.sh)
  cloudwatch_a2a_arn, security_a2a_arn, cost_a2a_arn,
  advisor_a2a_arn, jira_a2a_arn, knowledge_a2a_arn, investigator_a2a_arn
                          — A2A Specialist Runtime ARNs for direct routing
                            (optional; populated by deploy.sh Step 9)
  alb_dns                 — ALB DNS name for CloudFront → ALB SSE streaming
                            origin (empty on first deploy; set on re-deploys)

Deploy: cdk deploy --all
"""
import aws_cdk as cdk
from stacks.backend_stack import BackendStack
from stacks.agentcore_stack import AgentCoreStack
from stacks.frontend_stack import FrontendStack

app = cdk.App()

# AWS account/region for all stacks.
env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "us-east-1"
)

# --- Environment name ---
# Drives the resource-name prefix and the `Environment` tag applied to EVERY resource
# across all three stacks. This mirrors the Terraform VPC module convention where each
# resource is named "${environment}-<resource>" (e.g. "dev-vpc", "dev-public-subnet-0")
# and carries an Environment=${environment} tag.
#
# Resolution order:
#   1. `--context environment=<name>` on the CLI (e.g. deploy.sh)
#   2. the "environment" key in cdk.json
#   3. fallback to "dev" (matches the Terraform module default)
environment_name = app.node.try_get_context("environment") or "dev"

# --- CloudFormation stack names ---
# The deployed CloudFormation stack names carry the environment prefix
# (e.g. "dev-MSPAssistantBackendStack"), matching the "${environment}-<resource>"
# convention used everywhere else.
#
# The CDK construct IDs (2nd positional arg) are kept STABLE and unprefixed so that
# `cdk deploy <ConstructId>` targets in deploy.sh continue to work regardless of
# environment. The env-prefixed name is set explicitly via the `stack_name` property.
# Names are lowercase kebab-case (e.g. "dev-msp-assistant-backend-stack").
# NOTE: `cdk --outputs-file` keys the JSON by stack_name, so deploy.sh reads outputs
# under the prefixed keys (e.g. .["dev-msp-assistant-backend-stack"]).
AGENTCORE_STACK_NAME = f"{environment_name}-msp-assistant-agentcore-stack"
BACKEND_STACK_NAME = f"{environment_name}-msp-assistant-backend-stack"
FRONTEND_STACK_NAME = f"{environment_name}-msp-assistant-frontend-stack"

# 1. AgentCore Infrastructure
agentcore_stack = AgentCoreStack(
    app, "MSPAssistantAgentCoreStack",
    stack_name=AGENTCORE_STACK_NAME,
    environment_name=environment_name,
    env=env,
    description="AgentCore Runtime, Gateway, Memory, Identity, Policy, Observability (uksb-lfevfsxkwc)(tag:agentcore)"
)

# 2. Backend (ECS Fargate + ALB + API Gateway)
backend_stack = BackendStack(
    app, "MSPAssistantBackendStack",
    stack_name=BACKEND_STACK_NAME,
    agentcore_resources=agentcore_stack.resources,
    environment_name=environment_name,
    env=env,
    description="FastAPI on ECS Fargate with ALB and API Gateway (uksb-lfevfsxkwc)(tag:backend)"
)
backend_stack.add_dependency(agentcore_stack)

# 3. Frontend (S3 + CloudFront)
frontend_stack = FrontendStack(
    app, "MSPAssistantFrontendStack",
    stack_name=FRONTEND_STACK_NAME,
    api_url=backend_stack.api_url,
    alb_dns=app.node.try_get_context("alb_dns") or "",
    cognito_config=backend_stack.cognito_config,
    environment_name=environment_name,
    env=env,
    description="React SPA on S3 with CloudFront CDN (uksb-lfevfsxkwc)(tag:frontend)"
)
frontend_stack.add_dependency(backend_stack)

# --- Stack-wide tags ---
# Applied to every resource in every stack. The `Environment` tag matches the
# Terraform module convention (Environment = var.environment) so resources created
# by CDK and Terraform share a consistent tagging scheme.
for stack in [agentcore_stack, backend_stack, frontend_stack]:
    cdk.Tags.of(stack).add("Project", "MSP-Assistant-AgentCore")
    cdk.Tags.of(stack).add("ManagedBy", "CDK")
    cdk.Tags.of(stack).add("Environment", environment_name)

app.synth()
