"""Tools for the security specialist.

Wire real tools here. Options:
- Call the AgentCore Gateway (MCP) to reach security-relevant tools/targets.
- Call boto3 directly for read-only AWS data.
- For jira: use IdentityClient.api_key() to fetch the Jira key from the token vault.

Left as a stub so the graph compiles; add @tool functions and return them.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool


def get_tools() -> list[BaseTool]:
    return []
