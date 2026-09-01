#!/usr/bin/env bash
#
# Build + push a runtime's deployment bundle to the AgentCore codebuild-sources
# S3 bucket, mirroring the deployed flow:
#   bedrock-agentcore-codebuild-sources-001961766007-us-east-1/<runtime>/deployment.zip
#
# Usage: ./scripts/deploy.sh <agent_pkg>
#   e.g. ./scripts/deploy.sh supervisor
#
# Requires: awscli v2 (>=2.2x), zip, the `agentcore` profile.
# This packages code to S3. Triggering the actual AgentCore build/update is done
# via the AgentCore CLI/SDK (see the note at the end) or CI.

set -euo pipefail

AGENT="${1:-}"
if [[ -z "$AGENT" ]]; then
  echo "usage: $0 <agent_pkg>  (e.g. supervisor, security_a2a, aws_api_mcp)" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENT_DIR="$REPO_ROOT/agents/$AGENT"
CONFIG="$AGENT_DIR/agentcore.yaml"

if [[ ! -f "$CONFIG" ]]; then
  echo "No agentcore.yaml for '$AGENT' at $CONFIG" >&2
  exit 1
fi

export AWS_PROFILE="${AWS_PROFILE:-agentcore}"
export AWS_REGION="${AWS_REGION:-us-east-1}"

# Parse minimal fields from agentcore.yaml (bucket + prefix) without a YAML lib.
S3_BUCKET="$(grep -E '^\s*s3_bucket:' "$CONFIG" | awk '{print $2}')"
S3_PREFIX="$(grep -E '^\s*s3_prefix:' "$CONFIG" | awk '{print $2}')"
RUNTIME_NAME="$(grep -E '^\s*name:' "$CONFIG" | head -1 | awk '{print $2}')"

echo ">>> Packaging $AGENT (runtime: $RUNTIME_NAME)"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

# Bundle = shared lib + this agent package + requirements. This preserves the
# `common` and `agents.<pkg>` import paths used by the entrypoints.
mkdir -p "$BUILD_DIR/agents"
cp -R "$REPO_ROOT/libs/common" "$BUILD_DIR/common"
cp -R "$AGENT_DIR" "$BUILD_DIR/agents/$AGENT"
# minimal package marker so `agents` is importable
touch "$BUILD_DIR/agents/__init__.py"
cp "$REPO_ROOT/requirements.txt" "$BUILD_DIR/requirements.txt"

ZIP_PATH="$BUILD_DIR/deployment.zip"
( cd "$BUILD_DIR" && zip -qr "$ZIP_PATH" . -x '*.pyc' -x '__pycache__/*' )

echo ">>> Uploading to s3://$S3_BUCKET/$S3_PREFIX"
aws s3 cp "$ZIP_PATH" "s3://$S3_BUCKET/$S3_PREFIX"

echo ">>> Done. Bundle pushed."
cat <<EOF

Next step — trigger the AgentCore build/update from this bundle:

  # Using the AgentCore CLI (recommended):
  #   agentcore launch --config "$CONFIG"
  #
  # Or update the existing runtime in place via the control-plane API
  # (bedrock-agentcore-control update-agent-runtime) pointing at:
  #   s3://$S3_BUCKET/$S3_PREFIX

EOF
