"""MCP Tool: CloudWatch — Query alarms, metrics, and monitoring data."""
import json
import boto3
from datetime import datetime, timedelta, timezone


def lambda_handler(event, context):
    """Handle MCP tool invocations for CloudWatch operations."""
    # AgentCore Gateway passes tool name in context, input as event directly
    delimiter = "___"
    try:
        original_tool_name = context.client_context.custom['bedrockAgentCoreToolName']
        tool_name = original_tool_name[original_tool_name.index(delimiter) + len(delimiter):]
    except (AttributeError, KeyError, ValueError):
        tool_name = event.pop("toolName", event.pop("name", "describe_alarms"))

    # event IS the input params directly
    tool_input = event

    handlers = {
        "describe_alarms": _describe_alarms,
        "get_metric_statistics": _get_metric_statistics,
        "list_metrics": _list_metrics,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return _response(f"Unknown tool: {tool_name}. Available: {list(handlers.keys())}")

    try:
        result = handler(tool_input)
        return _response(result)
    except Exception as e:
        return _response(f"Error: {str(e)}")


def _describe_alarms(params):
    cw = boto3.client("cloudwatch")
    kwargs = {}
    if params.get("state_value"):
        kwargs["StateValue"] = params["state_value"]
    if params.get("alarm_names"):
        kwargs["AlarmNames"] = params["alarm_names"]
    kwargs["MaxRecords"] = params.get("max_records", 20)

    resp = cw.describe_alarms(**kwargs)
    alarms = []
    for a in resp.get("MetricAlarms", []):
        alarms.append({
            "name": a["AlarmName"],
            "state": a["StateValue"],
            "metric": a["MetricName"],
            "namespace": a["Namespace"],
            "threshold": a.get("Threshold"),
            "comparison": a.get("ComparisonOperator"),
            "description": a.get("AlarmDescription", ""),
            "updated": a.get("StateUpdatedTimestamp", "").isoformat() if a.get("StateUpdatedTimestamp") else "",
        })
    return json.dumps({"alarms": alarms, "count": len(alarms)}, default=str)


def _get_metric_statistics(params):
    cw = boto3.client("cloudwatch")
    hours = params.get("hours", 1)
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)

    resp = cw.get_metric_statistics(
        Namespace=params["namespace"],
        MetricName=params["metric_name"],
        Dimensions=[{"Name": k, "Value": v} for k, v in params.get("dimensions", {}).items()],
        StartTime=start,
        EndTime=end,
        Period=params.get("period", 300),
        Statistics=params.get("statistics", ["Average"]),
    )
    datapoints = sorted(resp.get("Datapoints", []), key=lambda x: x["Timestamp"])
    return json.dumps({"datapoints": datapoints, "count": len(datapoints)}, default=str)


def _list_metrics(params):
    cw = boto3.client("cloudwatch")
    kwargs = {}
    if params.get("namespace"):
        kwargs["Namespace"] = params["namespace"]
    kwargs["RecentlyActive"] = "PT3H"

    resp = cw.list_metrics(**kwargs)
    metrics = [{"namespace": m["Namespace"], "name": m["MetricName"]} for m in resp.get("Metrics", [])[:30]]
    namespaces = list(set(m["namespace"] for m in metrics))
    return json.dumps({"metrics": metrics, "namespaces": namespaces}, default=str)


def _response(content):
    return {"content": [{"text": content if isinstance(content, str) else json.dumps(content, default=str)}]}
