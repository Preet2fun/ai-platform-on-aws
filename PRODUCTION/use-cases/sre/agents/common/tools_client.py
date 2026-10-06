"""Client for the observability backends (metrics/logs/traces/changes/events/runbooks).

In P1 the specialists call the synthetic FastAPI backends directly over HTTP. In P4 the same
calls route through the AgentCore Gateway as MCP tools — the request/response contract is
identical, so only the base URL / transport changes, not the agent logic. Every call injects
`tenant_id` (and `scenario_id` where applicable) from the RequestContext to preserve isolation.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from .context import RequestContext

TOOLS_BASE_URL = os.getenv("SRE_TOOLS_BASE_URL", "http://localhost:8080")


class ToolsClient:
    def __init__(self, base_url: str = TOOLS_BASE_URL, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        clean = {k: v for k, v in params.items() if v is not None}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(f"{self.base_url}{path}", params=clean)
            resp.raise_for_status()
            return resp.json()

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
