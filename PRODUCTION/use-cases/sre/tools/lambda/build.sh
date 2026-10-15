#!/usr/bin/env bash
# Package the Gateway tools Lambda: handler + fixtures + synthetic-data (NO manifest.yaml).
# Produces tools/lambda/build/tools-lambda.zip. Run from PRODUCTION/use-cases/sre.
set -euo pipefail

HERE="tools/lambda"
BUILD="$HERE/build"
STAGE="$BUILD/stage"
rm -rf "$BUILD"
mkdir -p "$STAGE/synthetic-data/tenants"

# 1) handler + shared fixtures (flat, so `import fixtures` works)
cp "$HERE/handler.py" "$STAGE/handler.py"
cp "tools/common/fixtures.py" "$STAGE/fixtures.py"

# 2) registry.yaml -> registry.json (so the Lambda needs no PyYAML)
python3 -c "import yaml,json,sys; json.dump(yaml.safe_load(open('synthetic-data/tenants/registry.yaml')), open('$STAGE/synthetic-data/tenants/registry.json','w'))"

# 3) copy per-tenant fixtures + runbooks, EXCLUDING manifest.yaml (ground truth must never ship)
cd synthetic-data/tenants
for tenant in */; do
  tenant="${tenant%/}"
  [ -d "$tenant" ] || continue
  mkdir -p "../../$STAGE/synthetic-data/tenants/$tenant/scenarios"
  [ -f "$tenant/runbooks.json" ] && cp "$tenant/runbooks.json" "../../$STAGE/synthetic-data/tenants/$tenant/runbooks.json" || true
  if [ -d "$tenant/scenarios" ]; then
    for scen in "$tenant"/scenarios/*/; do
      scen="${scen%/}"
      sname="$(basename "$scen")"
      dst="../../$STAGE/synthetic-data/tenants/$tenant/scenarios/$sname"
      mkdir -p "$dst"
      for f in metrics logs traces changes events; do
        [ -f "$scen/$f.json" ] && cp "$scen/$f.json" "$dst/$f.json" || true
      done
      # explicitly DO NOT copy manifest.yaml
    done
  fi
done
cd ../../

# 4) point fixtures at the bundled data dir inside the Lambda
#    (SRE_SYNTH_DATA_ROOT is set on the Lambda to /var/task/synthetic-data/tenants)

# 5) zip
cd "$STAGE"
zip -qr "../tools-lambda.zip" .
cd - >/dev/null
echo "built $BUILD/tools-lambda.zip"
unzip -l "$BUILD/tools-lambda.zip" | tail -5
# sanity: ensure no manifest leaked
if unzip -l "$BUILD/tools-lambda.zip" | grep -q "manifest.yaml"; then
  echo "ERROR: manifest.yaml leaked into the Lambda package!" >&2
  exit 1
fi
echo "OK: no manifest.yaml in package"
