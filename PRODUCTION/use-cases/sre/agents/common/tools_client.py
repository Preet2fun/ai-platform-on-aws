"""Client for the observability backends (metrics/logs/traces/changes/events/runbooks).

In P1 the specialists call the synthetic FastAPI backends directly over HTTP. In P4 the same
calls route through the AgentCore Gateway as MCP tools — the request/response contract is
identical, so only the base URL / transport changes, not the agent logic. Every call injects
`tenant_id` (and `scenario_id` where applicable) from the RequestContext to preserve isolation.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
import uuid
from typing import Any

import httpx

from .context import RequestContext

# Transport selection (first match wins):
#   1. SRE_GATEWAY_URL set  -> P4: call the AgentCore Gateway over MCP (JWT-authed). PREFERRED.
#   2. SRE_TOOLS_RUNTIME_ARN -> P1 legacy: SigV4 invoke_agent_runtime against the tools runtime.
#   3. SRE_TOOLS_BASE_URL / default -> local dev: GET http://host/<endpoint>?params.
GATEWAY_URL = os.getenv("SRE_GATEWAY_URL", "")
TOOLS_BASE_URL = os.getenv("SRE_TOOLS_RUNTIME_ARN") or os.getenv("SRE_TOOLS_BASE_URL", "http://localhost:8080")

# Gateway MCP auth (service-to-service). The specialist fetches a Cognito M2M token to call the
# gateway. Tenant identity is NOT this token — it rides in the tool arguments (tenant_id) and was
# already enforced at the supervisor (P3). Creds come from Secrets Manager (secret ARN) so no
# client secret sits in code; env fallback supported for local testing.
GATEWAY_TARGET = os.getenv("SRE_GATEWAY_TARGET", "sretools")
GATEWAY_TOKEN_ENDPOINT = os.getenv("SRE_GATEWAY_TOKEN_ENDPOINT", "")
GATEWAY_SCOPE = os.getenv("SRE_GATEWAY_SCOPE", "sre-api/invoke")
GATEWAY_CLIENT_SECRET_ARN = os.getenv("SRE_GATEWAY_CLIENT_SECRET_ARN", "")  # Secrets Manager ARN with {client_id, client_secret}
GATEWAY_CLIENT_ID = os.getenv("SRE_GATEWAY_CLIENT_ID", "")                   # env fallback (local test)
GATEWAY_CLIENT_SECRET = os.getenv("SRE_GATEWAY_CLIENT_SECRET", "")


def _is_agentcore_arn(target: str) -> bool:
    return target.startswith("arn:aws:bedrock-agentcore:")


def _tools_session_id() -> str:
    return f"sre-tools-{uuid.uuid4().hex}{uuid.uuid4().hex}"


# path -> gateway tool name (the six endpoints map 1:1 to the Lambda tools)
_PATH_TO_TOOL = {
    "/metrics": "metrics", "/logs": "logs", "/traces": "traces",
    "/changes": "changes", "/events": "events", "/runbooks": "runbooks",
}


class _GatewayTokenCache:
    """Fetches and caches a Cognito M2M access token for calling the gateway. Thread-safe."""

    def __init__(self):
        self._lock = threading.Lock()
        self._token = ""
        self._exp = 0.0

    def _creds(self) -> tuple[str, str]:
        if GATEWAY_CLIENT_SECRET_ARN:
            import boto3
            sm = boto3.client("secretsmanager")
            raw = sm.get_secret_value(SecretId=GATEWAY_CLIENT_SECRET_ARN)["SecretString"]
            d = json.loads(raw)
            return d["client_id"], d["client_secret"]
        if GATEWAY_CLIENT_ID and GATEWAY_CLIENT_SECRET:
            return GATEWAY_CLIENT_ID, GATEWAY_CLIENT_SECRET
        raise RuntimeError("no gateway credentials (set SRE_GATEWAY_CLIENT_SECRET_ARN or SRE_GATEWAY_CLIENT_ID/SECRET)")

    def token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._exp - 60:
                return self._token
            cid, sec = self._creds()
            basic = base64.b64encode(f"{cid}:{sec}".encode()).decode()
            resp = httpx.post(
                GATEWAY_TOKEN_ENDPOINT,
                headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
                data={"grant_type": "client_credentials", "scope": GATEWAY_SCOPE},
                timeout=30,
            )
            resp.raise_for_status()
            j = resp.json()
            self._token = j["access_token"]
            self._exp = time.time() + float(j.get("expires_in", 3600))
            return self._token


_TOKEN_CACHE = _GatewayTokenCache()


class ToolsClient:
    """Fetch observability evidence from the synthetic backends.

    Three transports (selected at construction):
      - Gateway MCP (SRE_GATEWAY_URL set) -> JWT-authed tools/call on the AgentCore Gateway. P4+.
      - AgentCore Runtime ARN -> SigV4 invoke_agent_runtime to the tools runtime dispatcher. P1 legacy.
      - http(s) URL -> GET /<endpoint>?params. Local dev.
    The returned JSON shape is identical across transports, so the six tool methods are unchanged.
    """

    def __init__(self, base_url: str | None = None, timeout: float = 30.0):
        self.timeout = timeout
        self.use_gateway = bool(GATEWAY_URL)
        self.gateway_url = GATEWAY_URL
        self.target = base_url or TOOLS_BASE_URL
        self.is_arn = _is_agentcore_arn(self.target)
        if not self.use_gateway and not self.is_arn:
            self.base_url = self.target.rstrip("/")

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        clean = {k: v for k, v in params.items() if v is not None}
        if self.use_gateway:
            return self._invoke_gateway(_PATH_TO_TOOL[path], clean)
        if self.is_arn:
            return self._invoke_cloud(path.lstrip("/"), clean)
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(f"{self.base_url}{path}", params=clean)
            resp.raise_for_status()
            return resp.json()

    def _invoke_gateway(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """Call the gateway over MCP (tools/call) and unwrap the Lambda {statusCode, body} envelope."""
        token = _TOKEN_CACHE.token()
        payload = {
            "jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "tools/call",
            "params": {"name": f"{GATEWAY_TARGET}___{tool}", "arguments": args},
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(self.gateway_url, json=payload, headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            })
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if "text/event-stream" in ct:
                data = None
                for line in resp.text.splitlines():
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                rpc = data or {}
            else:
                rpc = resp.json()
        if "error" in rpc:
            raise RuntimeError(f"gateway MCP error for '{tool}': {rpc['error']}")
        result = rpc.get("result", {})
        # MCP tool result: content[0].text holds the Lambda response JSON ({statusCode, body})
        content = result.get("content") or []
        text = next((c.get("text", "") for c in content if c.get("type") == "text"), "")
        envelope = json.loads(text) if text else {}
        status = envelope.get("statusCode", 200)
        body = envelope.get("body")
        parsed = json.loads(body) if isinstance(body, str) else (body or {})
        if status >= 400:
            raise RuntimeError(f"tool '{tool}' error ({status}): {parsed.get('error', parsed)}")
        return parsed

    def _invoke_cloud(self, tool: str, params: dict[str, Any]) -> dict[str, Any]:
        import boto3  # lazy import so local/test runs don't require AWS creds
        from botocore.config import Config as _BotoConfig

        _cfg = _BotoConfig(read_timeout=max(self.timeout, 120), connect_timeout=10,
                           retries={"max_attempts": 0})
        client = boto3.client("bedrock-agentcore", config=_cfg)
        payload = json.dumps({"tool": tool, "params": params}).encode("utf-8")
        resp = client.invoke_agent_runtime(
            agentRuntimeArn=self.target,
            qualifier="DEFAULT",
            runtimeSessionId=_tools_session_id(),
            payload=payload,
        )
        content_type = resp.get("contentType", "") or ""
        body = resp.get("response")
        if "text/event-stream" in content_type:
            chunks = []
            for line in body.iter_lines(chunk_size=10):
                if not line:
                    continue
                line = line.decode("utf-8") if isinstance(line, bytes) else line
                if line.startswith("data: "):
                    chunks.append(line[6:])
            raw = "".join(chunks)
        else:
            parts = []
            for chunk in body:
                parts.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
            raw = "".join(parts)
        data = json.loads(raw)
        if isinstance(data, dict) and "error" in data and len(data) == 1:
            raise RuntimeError(f"tools runtime error for '{tool}': {data['error']}")
        return data

    def metrics(self, ctx: RequestContext, service: str | None = None, metric: str | None = None,
                start: str | None = None, end: str | None = None) -> list[dict]:
        return self._get("/metrics", {"tenant_id": ctx.require_tenant(), "scenario_id": ctx.scenario_id,
                                      "service": service, "metric": metric, "start": start, "end": end}).get("series", [])

    def logs(self, ctx: RequestContext, service: str | None = None, level: str | None = None,
             contains: str | None = None, start: str | None = None, end: str | None = None) -> list[dict]:
        return self._get("/logs", {"tenant_id": ctx.require_tenant(), "scenario_id": ctx.scenario_id,
                                   "service": service, "level": level, "contains": contains,
                                   "start": start, "end": end}).get("logs", [])

    def traces(self, ctx: RequestContext, service: str | None = None, errors_only: bool = False,
               start: str | None = None, end: str | None = None) -> list[dict]:
        return self._get("/traces", {"tenant_id": ctx.require_tenant(), "scenario_id": ctx.scenario_id,
                                     "service": service, "errors_only": errors_only,
                                     "start": start, "end": end}).get("traces", [])

    def changes(self, ctx: RequestContext, service: str | None = None, change_type: str | None = None,
                start: str | None = None, end: str | None = None) -> list[dict]:
        return self._get("/changes", {"tenant_id": ctx.require_tenant(), "scenario_id": ctx.scenario_id,
                                      "service": service, "change_type": change_type,
                                      "start": start, "end": end}).get("changes", [])

    def events(self, ctx: RequestContext, service: str | None = None, source: str | None = None,
               start: str | None = None, end: str | None = None) -> list[dict]:
        return self._get("/events", {"tenant_id": ctx.require_tenant(), "scenario_id": ctx.scenario_id,
                                     "service": service, "source": source,
                                     "start": start, "end": end}).get("events", [])

    def runbooks(self, ctx: RequestContext, query: str | None = None, service: str | None = None) -> list[dict]:
        return self._get("/runbooks", {"tenant_id": ctx.require_tenant(),
                                       "query": query, "service": service}).get("runbooks", [])

    def alarm_context(self, ctx: RequestContext) -> dict[str, Any]:
        """Convenience: the scenario's starting signal set the supervisor seeds the investigation with.

        Returns a compact snapshot (recent changes + a few error logs + error traces) so the
        hypothesis agent has a starting point without a broad data dump.
        """
        return {
            "recent_changes": self.changes(ctx),
            "error_logs": self.logs(ctx, level="ERROR"),
            "error_traces": self.traces(ctx, errors_only=True),
        }
