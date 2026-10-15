#!/usr/bin/env bash
# Build the 6 ARM64 container images (5 agents + tools) and push to ECR.
# Run from PRODUCTION/use-cases/sre with Docker running and ECR login done.
set -euo pipefail

ACCOUNT=001961766007
REGION=us-east-1
REGISTRY="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
TAG="${TAG:-v1}"

echo "### Building TOOLS image ###"
docker buildx build --platform linux/arm64 -f tools/Dockerfile \
  -t "${REGISTRY}/sre-agentic-dev-tools:${TAG}" --push .

# 5 agents share agents/Dockerfile; AGENT_MODULE + PORT select which one runs.
build_agent () {
  local repo="$1" module="$2" port="$3"
  echo "### Building AGENT image: ${repo} (module=${module}, port=${port}) ###"
  docker buildx build --platform linux/arm64 -f agents/Dockerfile \
    --build-arg AGENT_MODULE="${module}" --build-arg PORT="${port}" \
    -t "${REGISTRY}/sre-agentic-dev-${repo}:${TAG}" --push .
}

build_agent supervisor         agents.supervisor.main         8080
build_agent investigator       agents.investigator.main       9000
build_agent telemetry          agents.telemetry.main          9000
build_agent change-correlation agents.change_correlation.main 9000
build_agent remediation        agents.remediation.main        9000

echo "### ALL 6 IMAGES BUILT + PUSHED (tag=${TAG}) ###"
