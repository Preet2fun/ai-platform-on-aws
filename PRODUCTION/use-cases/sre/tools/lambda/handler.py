"""Gateway Lambda target for the synthetic SRE observability tools (P4).

The AgentCore Gateway fronts this Lambda as MCP tools. The gateway invokes the Lambda with:
  - event   = the tool arguments (flat map derived from the tool's inputSchema)
  - context.client_context.custom['bedrockAgentCoreToolName'] = "${target}___${tool}"

We strip the target prefix, dispatch to the matching fixture loader, and return the result as
JSON. Tenant isolation is preserved exactly as before: tenant_id is required on every tool and
only that tenant's fixtures are readable. The synthetic-data tree + fixtures.py are bundled into
the deployment package; manifest.yaml (ground truth) is never exposed.

This replaces the direct-SigV4 tools runtime path (P1). Security win: tool access now flows
through the gateway's single policy-enforced choke point, invoked by the gateway's own scoped
IAM role — no agent holds direct invoke rights to a tools endpoint.
"""
from __future__ import annotations

import json
from typing import Any

import fixtures as fx  # bundled alongside this handler

DELIMITER = "___"


def _tool_name(context) -> str:
    try:
        raw = context.client_context.custom["bedrockAgentCoreToolName"]
    except Exception:  # noqa: BLE001 - allow direct test invokes without client_context
        return ""
    return raw.split(DELIMITER, 1)[1] if DELIMITER in raw else raw


def _ok(body: Any) -> dict[str, Any]:
    return {"statusCode": 200, "body": json.dumps(body)}


def _err(status: int, msg: str) -> dict[str, Any]:
    return {"statusCode": status, "body": json.dumps({"error": msg})}


def _dispatch(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    tid = args.get("tenant_id")
    sid = args.get("scenario_id")
    if not tid:
        return _err(400, "tenant_id is required")

    try:
        if tool == "runbooks":
            return _ok({"tenant_id": tid, "runbooks": fx.get_runbooks(tid, args.get("query"), args.get("service"))})

        # all other tools are scenario-scoped — validate tenant + scenario first
        if not sid:
            return _err(400, "scenario_id is required")
        fx.tenant_config(tid)
        fx._scenario_dir(tid, sid)

        if tool == "metrics":
            return _ok({"tenant_id": tid, "series": fx.get_metrics(tid, sid, args.get("service"), args.get("metric"), args.get("start"), args.get("end"))})
        if tool == "logs":
            return _ok({"tenant_id": tid, "logs": fx.get_logs(tid, sid, args.get("service"), args.get("level"), args.get("contains"), args.get("start"), args.get("end"))})
        if tool == "traces":
            return _ok({"tenant_id": tid, "traces": fx.get_traces(tid, sid, args.get("service"), bool(args.get("errors_only", False)), args.get("start"), args.get("end"))})
        if tool == "changes":
            return _ok({"tenant_id": tid, "changes": fx.get_changes(tid, sid, args.get("service"), args.get("change_type"), args.get("start"), args.get("end"))})
        if tool == "events":
            return _ok({"tenant_id": tid, "events": fx.get_events(tid, sid, args.get("service"), args.get("source"), args.get("start"), args.get("end"))})
        return _err(400, f"unknown tool: {tool}")
    except fx.TenantNotFound as e:
        return _err(404, str(e))
    except fx.ScenarioNotFound as e:
        return _err(404, str(e))


def lambda_handler(event, context):
    tool = _tool_name(context)
    # event is the flat args map; tolerate a nested {"params": {...}} shape for direct testing too
    args = event if isinstance(event, dict) and "tenant_id" in event else (event.get("params", event) if isinstance(event, dict) else {})
    if not tool:
        # allow direct test invokes: {"tool": "...", "params": {...}}
        tool = event.get("tool", "") if isinstance(event, dict) else ""
        args = event.get("params", {}) if isinstance(event, dict) else {}
    return _dispatch(tool, args)
