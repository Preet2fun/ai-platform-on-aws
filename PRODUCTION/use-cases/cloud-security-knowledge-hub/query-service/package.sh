#!/usr/bin/env bash
#
# Package the query-service Lambda zip and upload it to the artifacts bucket.
# Layout: app.py + common/ at the ROOT (handler = "app.handler"), plus psycopg built for
# the Lambda runtime target (Linux / python3.12 / x86_64) so the binary driver loads.
#
# Usage:  AWS_PROFILE=agentcore AWS_REGION=us-east-1 bash ./package.sh dev

set -euo pipefail

ENV="${1:-dev}"
REGION="${AWS_REGION:-us-east-1}"
PROJECT="cshub"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="$HERE/.build"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="${PROJECT}-${ENV}-artifacts-${ACCOUNT}"

PYVER="3.12"
PLATFORM="manylinux2014_x86_64"
# Use a pip whose interpreter is >=3.9 so cross-version --python-version works cleanly.
PIP="${PIP:-/Library/Frameworks/Python.framework/Versions/3.12/bin/pip3}"

echo ">>> artifacts bucket: $BUCKET"
rm -rf "$BUILD"; mkdir -p "$BUILD/query"
stage="$BUILD/query"

# handler + shared package at zip root
cp "$HERE/app.py" "$stage/"
cp -R "$HERE/common" "$stage/common"
# custom ADOT collector config (FI-6) — pins traces to the X-Ray exporter (see collector.yaml)
cp "$HERE/collector.yaml" "$stage/"

# psycopg for the Lambda target
"$PIP" install --platform "$PLATFORM" --python-version "$PYVER" --implementation cp \
  --only-binary=:all: --target "$stage" --no-cache-dir "psycopg[binary]>=3.2" >/dev/null

(cd "$stage" && zip -q -r "$BUILD/query.zip" . -x '*.pyc' -x '*__pycache__*')
echo ">>> built $(du -h "$BUILD/query.zip" | cut -f1)  query.zip"

aws s3 cp "$BUILD/query.zip" "s3://$BUCKET/query-service/query.zip" --region "$REGION" >/dev/null
echo ">>> uploaded s3://$BUCKET/query-service/query.zip"
