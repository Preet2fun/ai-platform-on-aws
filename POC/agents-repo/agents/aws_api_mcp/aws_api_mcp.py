"""AWS API MCP server (MCP protocol).

Deployed runtime: dev_aws_api_mcp  (entryPoint: aws_api_mcp.py, protocol MCP,
Cognito JWT authorizer, scope mcp-server/invoke).

Mirrors the awslabs AWS API MCP tools: `call_aws` and `suggest_aws_commands`.
Authorization is enforced by the AgentCore runtime's JWT authorizer; this module
implements the tool surface.
"""

from __future__ import annotations

import shlex
import subprocess

from mcp.server.fastmcp import FastMCP

from common.observability import setup_logging

log = setup_logging()
mcp = FastMCP("aws-api-mcp")


@mcp.tool()
def call_aws(command: str) -> str:
    """Execute a read-oriented AWS CLI command and return its output.

    Args:
        command: full AWS CLI command, e.g. "aws s3 ls" or
            "aws ec2 describe-instances --max-items 5".

    NOTE: In production, restrict this to read-only operations and apply
    least-privilege IAM on the runtime role. Never expose mutating commands
    without policy checks (see the guardrails gap analysis).
    """
    if not command.strip().startswith("aws "):
        return "Error: command must start with 'aws '."
    try:
        out = subprocess.run(
            shlex.split(command), capture_output=True, text=True, timeout=60, check=False
        )
        return out.stdout or out.stderr
    except Exception as e:  # pragma: no cover
        return f"Error running command: {e}"


@mcp.tool()
def suggest_aws_commands(task: str) -> str:
    """Suggest AWS CLI commands for a described task.

    Args:
        task: natural-language description of what the user wants to do.
    """
    # Placeholder: a real impl would call an LLM or a curated lookup.
    return f"Suggested approach for: {task}\n(implement command suggestion logic here)"


if __name__ == "__main__":
    log.info("starting aws-api MCP server")
    mcp.run(transport="streamable-http")
