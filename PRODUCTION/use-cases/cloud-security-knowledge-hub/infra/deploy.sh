#!/usr/bin/env bash
#
# P0 deploy — Cloud Security Knowledge Hub foundation.
# Deploys the stacks in dependency order (cross-stack exports link them).
# Raw CloudFormation via the AWS CLI. Idempotent (uses `deploy`/change sets).
#
# Usage:
#   ./deploy.sh <env>            # e.g. dev   (default: dev)
#   AWS_PROFILE=agentcore AWS_REGION=us-east-1 ./deploy.sh dev
#
# Prereqs: awscli v2, credentials for account 001961766007, jq.

set -euo pipefail

ENV="${1:-dev}"
REGION="${AWS_REGION:-us-east-1}"
PROJECT="cshub"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARAMS="$HERE/params/${ENV}.json"

if [[ ! -f "$PARAMS" ]]; then echo "missing params file: $PARAMS" >&2; exit 1; fi

# Build a `Key=Value` param string from the JSON for a given set of keys.
mkparams() {
  local keys=("$@") out=()
  for k in "${keys[@]}"; do
    v=$(jq -r --arg k "$k" '.[$k] // empty' "$PARAMS")
    [[ -n "$v" ]] && out+=("$k=$v")
  done
  echo "${out[@]}"
}

deploy() {
  local stack="$1" tmpl="$2"; shift 2
  echo ">>> deploying $stack"
  aws cloudformation deploy \
    --region "$REGION" \
    --stack-name "$stack" \
    --template-file "$HERE/$tmpl" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides $(mkparams "$@") \
    --tags project="$PROJECT" env="$ENV"
}

# 1) network (no imports)
deploy "${PROJECT}-${ENV}-network" 00-network.yaml \
  ProjectName EnvName VpcCidr

# 2) data stores (imports network)
deploy "${PROJECT}-${ENV}-data" 01-data-stores.yaml \
  ProjectName EnvName MinAcu MaxAcu EngineVersion

# 3) pgvector bootstrap (imports data)
deploy "${PROJECT}-${ENV}-pgvector" 02-pgvector-bootstrap.yaml \
  ProjectName EnvName EmbeddingDim

# 4) CI/CD OIDC (independent)
deploy "${PROJECT}-${ENV}-cicd" 06-cicd.yaml \
  ProjectName EnvName GitHubOrg GitHubRepo GitHubRef CreateOidcProvider

echo ">>> P0 foundation deployed. Key outputs:"
aws cloudformation describe-stacks --region "$REGION" \
  --stack-name "${PROJECT}-${ENV}-data" \
  --query "Stacks[0].Outputs" --output table
