"""CloudWatch MCP server (MCP protocol).

Deployed runtime: dev_cloudwatch_mcp  (entryPoint: cloudwatch_mcp.py).
Exposes read tools over CloudWatch logs / metrics / alarms.
"""

from __future__ import annotations

import boto3
from mcp.server.fastmcp import FastMCP

from common.config import get_settings
from common.observability import setup_logging

log = setup_logging()
mcp = FastMCP("cloudwatch-mcp")
_s = get_settings()


def _logs():
    return boto3.client("logs", region_name=_s.region)


def _cw():
    return boto3.client("cloudwatch", region_name=_s.region)


@mcp.tool()
def list_log_groups(prefix: str = "", limit: int = 25) -> list[str]:
    """List CloudWatch log groups, optionally filtered by name prefix."""
    kwargs = {"limit": limit}
    if prefix:
        kwargs["logGroupNamePrefix"] = prefix
    resp = _logs().describe_log_groups(**kwargs)
    return [g["logGroupName"] for g in resp.get("logGroups", [])]


@mcp.tool()
def describe_alarms(state: str = "ALARM") -> list[dict]:
    """List CloudWatch alarms in the given state (ALARM/OK/INSUFFICIENT_DATA)."""
    resp = _cw().describe_alarms(StateValue=state)
    return [
        {"name": a["AlarmName"], "metric": a.get("MetricName"), "state": a["StateValue"]}
        for a in resp.get("MetricAlarms", [])
    ]


if __name__ == "__main__":
    log.info("starting cloudwatch MCP server")
    mcp.run(transport="streamable-http")
