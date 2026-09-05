#!/bin/bash
# Syncs shared utilities to all agent runtimes before deployment.
# Single source of truth: agents/shared/
# Run this before `agentcore deploy` to propagate changes.
#
# Why: AgentCore packages each agent's directory independently.
# The ../shared/ path doesn't exist in the deployed container,
# so shared files must be physically present in each agent dir.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED="$SCRIPT_DIR/shared"

# All shared modules to sync
SHARED_FILES=(gateway_client.py sanitize.py base_runtime.py call_aws_tool.py allowed_operations.py)

# All agent runtimes (supervisor + investigator + 6 specialists)
AGENTS=(runtime runtime_investigator runtime_jira runtime_advisor runtime_cost runtime_knowledge runtime_security runtime_cloudwatch)

echo "Syncing shared files to agent runtimes..."

for agent in "${AGENTS[@]}"; do
    for file in "${SHARED_FILES[@]}"; do
        if [ -f "$SHARED/$file" ]; then
            cp "$SHARED/$file" "$SCRIPT_DIR/$agent/$file"
        fi
    done
    echo "  ✓ $agent/"
done

echo "Done. All agents have latest shared files from agents/shared/"
