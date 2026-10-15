"""P4 Checkpoint 1 proof — call the Gateway over MCP with a Cognito JWT.

Does: fetch M2M token -> MCP initialize -> tools/list -> tools/call (changes for acme) ->
cross-tenant check (globex token/args against acme scenario must 404-style error).

Usage:
  CLIENT_ID=... CLIENT_SECRET=... python3 infra/test-gateway-mcp.py
Env: GATEWAY_URL, TOKEN_ENDPOINT, SCOPE (defaults for the dev stack).
"""
import base64
import json
import os
import sys
import uuid

import httpx

GATEWAY_URL = os.getenv("GATEWAY_URL", "https://sreagenticdevgw-xgroozgkst.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp")
TOKEN_ENDPOINT = os.getenv("TOKEN_ENDPOINT", "https://sre-agentic-dev-auth.auth.us-east-1.amazoncognito.com/oauth2/token")
SCOPE = os.getenv("SCOPE", "sre-api/invoke")
TARGET = "sretools"  # tool names are "<target>___<tool>"


def token(cid, sec):
    basic = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    r = httpx.post(TOKEN_ENDPOINT, headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
                   data={"grant_type": "client_credentials", "scope": SCOPE}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def mcp(tok, method, params, _id=1):
    r = httpx.post(GATEWAY_URL, headers={
        "Authorization": f"Bearer {tok}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }, json={"jsonrpc": "2.0", "id": _id, "method": method, "params": params}, timeout=60)
    # MCP streamable-http may return SSE; handle both
    ct = r.headers.get("content-type", "")
    if "text/event-stream" in ct:
        out = []
        for line in r.text.splitlines():
            if line.startswith("data: "):
                out.append(line[6:])
        return json.loads(out[-1]) if out else {"raw": r.text}
    return r.json()


def main():
    cid, sec = os.environ.get("CLIENT_ID"), os.environ.get("CLIENT_SECRET")
    if not cid or not sec:
        print("set CLIENT_ID and CLIENT_SECRET"); sys.exit(2)
    tok = token(cid, sec)
    print("token len", len(tok))

    init = mcp(tok, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "sre-test", "version": "0.1"}}, 1)
    print("initialize ok:", "result" in init)

    lst = mcp(tok, "tools/list", {}, 2)
    tools = [t["name"] for t in (lst.get("result", {}).get("tools", []))]
    print("tools/list ->", tools)

    # call changes for acme
    call = mcp(tok, "tools/call", {"name": f"{TARGET}___changes",
               "arguments": {"tenant_id": "acme-retail", "scenario_id": "rds-connection-exhaustion"}}, 3)
    res = call.get("result", {})
    txt = json.dumps(res)[:200]
    print("tools/call changes(acme) ->", "isError" if res.get("isError") else "ok", txt[:160])

    # cross-tenant: acme's token asking for globex's scenario on an acme scenario id -> should error
    call2 = mcp(tok, "tools/call", {"name": f"{TARGET}___metrics",
                "arguments": {"tenant_id": "globex-fintech", "scenario_id": "rds-connection-exhaustion"}}, 4)
    res2 = call2.get("result", {})
    print("tools/call metrics(globex+acme-scenario) ->", json.dumps(res2)[:160])


if __name__ == "__main__":
    main()
