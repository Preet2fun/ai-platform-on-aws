"""Jira A2A Runtime — Jira ticket specialist using shared base class."""
import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))

from base_runtime import BaseSpecialistRuntime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an MSP Jira specialist managing incident tickets and change requests.

When providing information:
1. For searches: Key | Summary | Status | Priority | Assignee
2. For creation: confirm all fields before creating
3. Link incidents to root causes when possible

CONCISENESS RULES:
- Max 20 tickets per list
- Keep under 500 words"""


def _get_tools():
    """Try MCP Gateway tools first, fallback to local boto3 tools."""
    try:
        from gateway_client import get_mcp_tools
        tools = get_mcp_tools()
        if tools:
            logger.info(f"Using MCP Gateway tools: {len(tools)} tools")
            return tools
    except Exception as e:
        logger.warning(f"MCP tools failed: {e}")
    
    logger.info("Falling back to local boto3 tools")
    from aws_tools import get_tools
    return get_tools()


runtime = BaseSpecialistRuntime(
    agent_name="jira",
    system_prompt=SYSTEM_PROMPT,
    get_tools_fn=_get_tools,
)
app = runtime.app

if __name__ == "__main__":
    runtime.run()
