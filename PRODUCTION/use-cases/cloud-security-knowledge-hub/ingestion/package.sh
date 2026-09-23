#!/usr/bin/env bash
#
# Package the 5 ingestion Lambda handler zips and upload them to the artifacts bucket.
#
# Each zip is laid out with the handler module + common/ at the ROOT (Lambda handler string
# is "<module>.handler"), plus any third-party deps built for the Lambda runtime target
# (Linux, python3.12, x86_64) — NOT the local mac/python, so binary wheels (psycopg) load.
#
# Usage:
#   AWS_PROFILE=agentcore AWS_REGION=us-east-1 ./package.sh dev
#
# Prereqs: python3, pip, zip, awscli v2.

set -euo pipefail

ENV="${1:-dev}"
REGION="${AWS_REGION:-us-east-1}"
PROJECT="cshub"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="$HERE/.build"
BUCKET="${PROJECT}-${ENV}-artifacts-$(aws sts get-caller-identity --query Account --output text)"

# Lambda target (must match 02-ingestion.yaml Runtime + default arch)
PYVER="3.12"
PLATFORM="manylinux2014_x86_64"   # Lambda x86_64
# Use a pip whose interpreter is >=3.9 so cross-version --python-version works cleanly.
# Override with:  PIP="/path/to/pip" bash package.sh
PIP="${PIP:-/Library/Frameworks/Python.framework/Versions/3.12/bin/pip3}"

echo ">>> artifacts bucket: $BUCKET"
echo ">>> using pip: $PIP"
rm -rf "$BUILD"; mkdir -p "$BUILD"

# Build a dependency dir for a given set of pip packages, targeting the Lambda runtime.
# Empty package list => empty dir (pure-stdlib handlers).
build_deps() {
  local outdir="$1"; shift
  mkdir -p "$outdir"
  if [[ "$#" -gt 0 ]]; then
    "$PIP" install \
      --platform "$PLATFORM" \
      --python-version "$PYVER" \
      --implementation cp \
      --only-binary=:all: \
      --target "$outdir" \
      --no-cache-dir \
      "$@" >/dev/null
  fi
}

# Assemble one zip: <name> <handler_module.py> <deps...>
# common/ is always included (harmless for handlers that don't import it).
make_zip() {
  local name="$1" module="$2"; shift 2
  local stage="$BUILD/$name"
  echo ">>> packaging $name.zip (handler=$module.handler, deps: ${*:-none})"
  rm -rf "$stage"; mkdir -p "$stage"

  # handler module at root
  cp "$HERE/handlers/$module.py" "$stage/"
  # shared package at root
  cp -R "$HERE/common" "$stage/common"

  # third-party deps built for the Lambda target
  build_deps "$stage" "$@"

  # zip (contents at root, not nested under a dir)
  (cd "$stage" && zip -q -r "$BUILD/$name.zip" . -x '*.pyc' -x '*__pycache__*')
  echo "    -> $(du -h "$BUILD/$name.zip" | cut -f1)  $BUILD/$name.zip"
}

# ---- the five handlers ----
make_zip extract      extract       "pypdf>=5.0"
make_zip clean        clean
make_zip chunk        chunk
make_zip embed_upsert embed_upsert  "psycopg[binary]>=3.2"
make_zip manifest     manifest      "psycopg[binary]>=3.2"

# ---- upload to S3 (SSE-KMS bucket; aws cli uses the bucket default key) ----
echo ">>> uploading zips to s3://$BUCKET/ingestion/"
for z in extract clean chunk embed_upsert manifest; do
  aws s3 cp "$BUILD/$z.zip" "s3://$BUCKET/ingestion/$z.zip" --region "$REGION" >/dev/null
  echo "    uploaded ingestion/$z.zip"
done

echo ">>> done. Set LambdaCodeBucket=$BUCKET in the ingestion deploy."
