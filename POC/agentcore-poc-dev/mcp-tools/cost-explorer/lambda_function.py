"""MCP Tool: Cost Explorer — Query AWS spending and cost data."""
import json
import boto3
from datetime import datetime, timedelta, timezone


def lambda_handler(event, context):
    # AgentCore Gateway: tool name in context, input as event directly
    delimiter = "___"
    try:
        original_tool_name = context.client_context.custom["bedrockAgentCoreToolName"]
        tool_name = original_tool_name[original_tool_name.index(delimiter) + len(delimiter):]
    except (AttributeError, KeyError, ValueError):
        tool_name = event.pop("toolName", event.pop("name", "get_cost_and_usage"))
    tool_input = event

    handlers = {
        "get_cost_and_usage": _get_cost_and_usage,
        "get_cost_forecast": _get_cost_forecast,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return _response(f"Unknown tool: {tool_name}. Available: {list(handlers.keys())}")

    try:
        result = handler(tool_input)
        return _response(result)
    except Exception as e:
        return _response(f"Error: {str(e)}")


def _get_cost_and_usage(params):
    ce = boto3.client("ce")
    days = params.get("days", 30)
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    granularity = params.get("granularity", "MONTHLY")
    group_by = params.get("group_by", "SERVICE")

    resp = ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity=granularity,
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": group_by}],
    )

    services = []
    for period in resp.get("ResultsByTime", []):
        for group in period.get("Groups", []):
            name = group["Keys"][0]
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            if amount > 0.01:
                services.append({"service": name, "cost": round(amount, 2), "currency": "USD"})

    services.sort(key=lambda x: x["cost"], reverse=True)
    total = sum(s["cost"] for s in services)
    return json.dumps({"services": services[:10], "total": round(total, 2), "period": f"{start} to {end}"}, default=str)


def _get_cost_forecast(params):
    ce = boto3.client("ce")
    start = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    end = (datetime.now(timezone.utc) + timedelta(days=params.get("days", 30))).strftime("%Y-%m-%d")

    try:
        resp = ce.get_cost_forecast(
            TimePeriod={"Start": start, "End": end},
            Metric="UNBLENDED_COST",
            Granularity="MONTHLY",
        )
        forecast = resp.get("Total", {}).get("Amount", "0")
        return json.dumps({"forecast": round(float(forecast), 2), "currency": "USD", "period": f"{start} to {end}"})
    except Exception as e:
        return json.dumps({"error": str(e), "note": "Forecast requires sufficient historical data"})


def _response(content):
    return {"content": [{"text": content if isinstance(content, str) else json.dumps(content, default=str)}]}
