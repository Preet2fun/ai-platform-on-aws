"""MCP Tool: Trusted Advisor — Get AWS best practice recommendations."""
import json
import boto3


def lambda_handler(event, context):
    # AgentCore Gateway: tool name in context, input as event directly
    delimiter = "___"
    try:
        original_tool_name = context.client_context.custom["bedrockAgentCoreToolName"]
        tool_name = original_tool_name[original_tool_name.index(delimiter) + len(delimiter):]
    except (AttributeError, KeyError, ValueError):
        tool_name = event.pop("toolName", event.pop("name", "get_recommendations"))
    tool_input = event

    handlers = {
        "get_recommendations": _get_recommendations,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return _response(f"Unknown tool: {tool_name}. Available: {list(handlers.keys())}")

    try:
        result = handler(tool_input)
        return _response(result)
    except Exception as e:
        return _response(f"Error: {str(e)}")


def _get_recommendations(params):
    # Try Trusted Advisor API (requires Business/Enterprise support)
    try:
        support = boto3.client("support", region_name="us-east-1")
        resp = support.describe_trusted_advisor_checks(language="en")
        checks = resp.get("checks", [])

        category = params.get("category", "").lower()
        if category:
            checks = [c for c in checks if category in c.get("category", "").lower()]

        results = []
        for check in checks[:10]:
            try:
                detail = support.describe_trusted_advisor_check_result(checkId=check["id"])
                status = detail.get("result", {}).get("status", "unknown")
                results.append({
                    "name": check["name"],
                    "category": check["category"],
                    "status": status,
                    "description": check.get("description", "")[:150],
                })
            except Exception:
                results.append({
                    "name": check["name"],
                    "category": check["category"],
                    "status": "unable_to_check",
                })

        return json.dumps({"recommendations": results, "count": len(results)}, default=str)
    except Exception as e:
        return json.dumps({
            "error": "Trusted Advisor requires Business or Enterprise support plan",
            "details": str(e)[:200],
        })


def _response(content):
    return {"content": [{"text": content if isinstance(content, str) else json.dumps(content, default=str)}]}
