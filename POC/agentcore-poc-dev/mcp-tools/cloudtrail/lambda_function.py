"""MCP Tool: CloudTrail — Lookup recent API events and changes."""
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
        tool_name = event.pop("toolName", event.pop("name", "lookup_events"))
    tool_input = event

    handlers = {
        "lookup_events": _lookup_events,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return _response(f"Unknown tool: {tool_name}. Available: {list(handlers.keys())}")

    try:
        result = handler(tool_input)
        return _response(result)
    except Exception as e:
        return _response(f"Error: {str(e)}")


def _lookup_events(params):
    ct = boto3.client("cloudtrail")
    hours = params.get("hours", 24)
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)

    kwargs = {"StartTime": start, "EndTime": end, "MaxResults": params.get("max_results", 20)}

    if params.get("event_name"):
        kwargs["LookupAttributes"] = [{"AttributeKey": "EventName", "AttributeValue": params["event_name"]}]
    elif params.get("username"):
        kwargs["LookupAttributes"] = [{"AttributeKey": "Username", "AttributeValue": params["username"]}]
    elif params.get("resource_type"):
        kwargs["LookupAttributes"] = [{"AttributeKey": "ResourceType", "AttributeValue": params["resource_type"]}]

    resp = ct.lookup_events(**kwargs)
    events = []
    for ev in resp.get("Events", []):
        events.append({
            "time": ev.get("EventTime", "").isoformat() if ev.get("EventTime") else "",
            "name": ev.get("EventName", ""),
            "username": ev.get("Username", ""),
            "source": ev.get("EventSource", ""),
            "resources": [r.get("ResourceName", "") for r in ev.get("Resources", [])[:3]],
        })
    return json.dumps({"events": events, "count": len(events)}, default=str)


def _response(content):
    return {"content": [{"text": content if isinstance(content, str) else json.dumps(content, default=str)}]}
