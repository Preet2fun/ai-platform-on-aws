"""AWS Knowledge MCP server (MCP protocol).

Deployed runtime: dev_aws_knowledge_mcp  (entryPoint: aws_knowledge_mcp.py).
Exposes AWS Knowledge / documentation search as MCP tools.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from common.observability import setup_logging

log = setup_logging()
mcp = FastMCP("aws-knowledge-mcp")


@mcp.tool()
def search_documentation(query: str, limit: int = 5) -> list[dict]:
    """Search AWS documentation / knowledge base for the given query.

    Args:
        query: the search phrase.
        limit: max results to return.

    Wire this to the AWS Knowledge MCP backend or your own KB search
    (e.g. the awslabs aws-knowledge endpoint / an S3+Athena index over
    motadata-itsm-genai-data). Returns [] until implemented.
    """
    log.info("knowledge search: %s", query)
    return []


if __name__ == "__main__":
    log.info("starting aws-knowledge MCP server")
    mcp.run(transport="streamable-http")
