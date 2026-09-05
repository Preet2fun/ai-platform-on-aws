"""Pytest fixtures for agent unit tests.

Agent runtime and shared modules read AgentCore-injected environment variables at
import time via os.environ["KEY"] (e.g. AWS_REGION in call_aws_tool/gateway_client/
supervisor_runtime/investigator, GATEWAY_URL in gateway_client). Per the project
steering (.kiro/rules/code-generation-aws.md + .kiro/workspace.json), agent code
reads these with a hard-fail and no in-code fallback — AgentCore always injects them
in production.

To keep the test path clean without weakening that production behaviour (the README
states tests need no AWS credentials), this conftest sets the required variables for
the test session only, before any agent module is imported during collection.
"""

import os

# Set before agent modules are imported at collection time. setdefault() means a real
# value from the environment (e.g. in CI) still takes precedence.
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("GATEWAY_URL", "https://gateway.test.local/mcp")
