"""MCP Tool: Security Hub — Query security findings and compliance."""
import json
import boto3


def lambda_handler(event, context):
    # AgentCore Gateway: tool name in context, input as event directly
    delimiter = "___"
    try:
        original_tool_name = context.client_context.custom["bedrockAgentCoreToolName"]
        tool_name = original_tool_name[original_tool_name.index(delimiter) + len(delimiter):]
    except (AttributeError, KeyError, ValueError):
        tool_name = event.pop("toolName", event.pop("name", "get_findings"))
    tool_input = event

    handlers = {
        "get_findings": _get_findings,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return _response(f"Unknown tool: {tool_name}. Available: {list(handlers.keys())}")

    try:
        result = handler(tool_input)
        return _response(result)
    except Exception as e:
        return _response(f"Error: {str(e)}")


def _get_findings(params):
    sh = boto3.client("securityhub")
    filters = {}

    severity = params.get("severity")
    if severity:
        filters["SeverityLabel"] = [{"Value": severity.upper(), "Comparison": "EQUALS"}]

    status = params.get("status", "ACTIVE")
    filters["WorkflowStatus"] = [{"Value": status, "Comparison": "EQUALS"}]
    filters["RecordState"] = [{"Value": "ACTIVE", "Comparison": "EQUALS"}]

    resp = sh.get_findings(Filters=filters, MaxResults=params.get("max_results", 10))
    findings = []
    for f in resp.get("Findings", []):
        findings.append({
            "title": f.get("Title", ""),
            "severity": f.get("Severity", {}).get("Label", ""),
            "status": f.get("Workflow", {}).get("Status", ""),
            "resource_type": f.get("Resources", [{}])[0].get("Type", "") if f.get("Resources") else "",
            "resource_id": f.get("Resources", [{}])[0].get("Id", "")[:60] if f.get("Resources") else "",
            "description": f.get("Description", "")[:200],
            "created": f.get("CreatedAt", ""),
        })
    return json.dumps({"findings": findings, "count": len(findings)}, default=str)


def _response(content):
    return {"content": [{"text": content if isinstance(content, str) else json.dumps(content, default=str)}]}
