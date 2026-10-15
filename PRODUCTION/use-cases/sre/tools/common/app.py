"""Shared FastAPI app for the synthetic observability backends.

Design: one small FastAPI application exposes six routers (metrics/logs/traces/changes/
events/runbooks). Each route is **tenant-scoped** — `tenant_id` is required on every call —
and the backend enforces tenant isolation (a tenant can only read its own fixtures). An
optional `scenario_id` selects which incident fixtures to serve (P0 local dev); in the agent
runtime the active scenario is pinned per session.

Each router maps 1:1 to an MCP tool in P4 (OpenAPI -> MCP via the AgentCore Gateway), so the
OpenAPI schema here *is* the tool contract. In P9, `cloudwatch_tools` implements the same
routes against real CloudWatch.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from . import fixtures as fx


def _resolve(tenant_id: str, scenario_id: str):
    try:
        fx.tenant_config(tenant_id)
    except fx.TenantNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    try:
        fx._scenario_dir(tenant_id, scenario_id)
    except fx.ScenarioNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


def create_app(title: str = "SRE Synthetic Observability") -> FastAPI:
    app = FastAPI(title=title, version="0.1.0")

    @app.get("/health")
    def health():
        return {"status": "ok", "tenants": fx.known_tenants()}

    @app.get("/tenants")
    def tenants():
        return {"tenants": fx.known_tenants()}

    @app.get("/tenants/{tenant_id}/scenarios")
    def scenarios(tenant_id: str):
        try:
            return {"tenant_id": tenant_id, "scenarios": fx.tenant_scenarios(tenant_id)}
        except fx.TenantNotFound as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ---- metrics-api ----
    @app.get("/metrics", tags=["metrics-api"])
    def metrics(tenant_id: str = Query(...), scenario_id: str = Query(...),
                service: str | None = None, metric: str | None = None,
                start: str | None = None, end: str | None = None):
        """Return tenant-scoped metric time-series, optionally filtered by service/metric/window."""
        _resolve(tenant_id, scenario_id)
        return {"tenant_id": tenant_id, "series": fx.get_metrics(tenant_id, scenario_id, service, metric, start, end)}

    # ---- logs-api ----
    @app.get("/logs", tags=["logs-api"])
    def logs(tenant_id: str = Query(...), scenario_id: str = Query(...),
             service: str | None = None, level: str | None = None,
             contains: str | None = None, start: str | None = None, end: str | None = None):
        """Return tenant-scoped log lines, filterable by service/level/substring/window."""
        _resolve(tenant_id, scenario_id)
        return {"tenant_id": tenant_id, "logs": fx.get_logs(tenant_id, scenario_id, service, level, contains, start, end)}

    # ---- traces-api ----
    @app.get("/traces", tags=["traces-api"])
    def traces(tenant_id: str = Query(...), scenario_id: str = Query(...),
               service: str | None = None, errors_only: bool = False,
               start: str | None = None, end: str | None = None):
        """Return tenant-scoped trace summaries (spans), optionally errors-only or by service."""
        _resolve(tenant_id, scenario_id)
        return {"tenant_id": tenant_id, "traces": fx.get_traces(tenant_id, scenario_id, service, errors_only, start, end)}

    # ---- changes-api ----
    @app.get("/changes", tags=["changes-api"])
    def changes(tenant_id: str = Query(...), scenario_id: str = Query(...),
                service: str | None = None, change_type: str | None = None,
                start: str | None = None, end: str | None = None):
        """Return tenant-scoped deploys / config / scaling / infra changes."""
        _resolve(tenant_id, scenario_id)
        return {"tenant_id": tenant_id, "changes": fx.get_changes(tenant_id, scenario_id, service, change_type, start, end)}

    # ---- k8s-events-api ----
    @app.get("/events", tags=["k8s-events-api"])
    def events(tenant_id: str = Query(...), scenario_id: str = Query(...),
               service: str | None = None, source: str | None = None,
               start: str | None = None, end: str | None = None):
        """Return tenant-scoped k8s/platform events."""
        _resolve(tenant_id, scenario_id)
        return {"tenant_id": tenant_id, "events": fx.get_events(tenant_id, scenario_id, service, source, start, end)}

    # ---- runbooks-api ----
    @app.get("/runbooks", tags=["runbooks-api"])
    def runbooks(tenant_id: str = Query(...), query: str | None = None, service: str | None = None):
        """Search tenant-level operational runbooks by keyword/service (not scenario-scoped)."""
        try:
            return {"tenant_id": tenant_id, "runbooks": fx.get_runbooks(tenant_id, query, service)}
        except fx.TenantNotFound as e:
            raise HTTPException(status_code=404, detail=str(e))

    # ---- AgentCore HTTP contract: /ping + /invocations ----
    # When this backend runs as an AgentCore Runtime (HTTP protocol), the platform only forwards
    # POST /invocations (JSON) and GET /ping. The six GET routes above cannot be reached through
    # invoke_agent_runtime, so /invocations is a tool dispatcher: {"tool": "...", "params": {...}}.
    # The GET routes are kept for local dev and for the P4 Gateway (OpenAPI -> MCP) mapping.

    @app.get("/ping")
    def ping():
        return {"status": "Healthy"}

    def _call_tool(tool: str, p: dict[str, Any]) -> dict[str, Any]:
        tid = p.get("tenant_id")
        sid = p.get("scenario_id")
        if not tid:
            raise HTTPException(status_code=400, detail="tenant_id is required")
        if tool == "runbooks":
            return {"tenant_id": tid, "runbooks": fx.get_runbooks(tid, p.get("query"), p.get("service"))}
        # all other tools are scenario-scoped
        _resolve(tid, sid)
        if tool == "metrics":
            return {"tenant_id": tid, "series": fx.get_metrics(tid, sid, p.get("service"), p.get("metric"), p.get("start"), p.get("end"))}
        if tool == "logs":
            return {"tenant_id": tid, "logs": fx.get_logs(tid, sid, p.get("service"), p.get("level"), p.get("contains"), p.get("start"), p.get("end"))}
        if tool == "traces":
            return {"tenant_id": tid, "traces": fx.get_traces(tid, sid, p.get("service"), bool(p.get("errors_only", False)), p.get("start"), p.get("end"))}
        if tool == "changes":
            return {"tenant_id": tid, "changes": fx.get_changes(tid, sid, p.get("service"), p.get("change_type"), p.get("start"), p.get("end"))}
        if tool == "events":
            return {"tenant_id": tid, "events": fx.get_events(tid, sid, p.get("service"), p.get("source"), p.get("start"), p.get("end"))}
        raise HTTPException(status_code=400, detail=f"unknown tool: {tool}")

    @app.post("/invocations")
    async def invocations(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"error": "invalid JSON body"})
        tool = body.get("tool")
        params = body.get("params") or {}
        if not tool:
            return JSONResponse(status_code=400, content={"error": "missing 'tool'"})
        try:
            return _call_tool(tool, params)
        except HTTPException as e:
            return JSONResponse(status_code=e.status_code, content={"error": e.detail})

    return app


app = create_app()
