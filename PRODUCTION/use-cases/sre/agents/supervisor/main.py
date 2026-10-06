"""Supervisor — HTTP runtime entrypoint (AgentCore HTTP contract, port 8080).

Endpoints:
  GET  /ping          -> {"status": "Healthy"}  (AgentCore health check)
  POST /invocations   -> runs the supervisor graph; returns the aggregated investigation result.

Request body (JSON):
  {"tenant_id": "...", "alarm": "...", "scenario_id": "...", "session_id": "...", "stream": false}

In P3, `tenant_id` is derived from the inbound JWT claim rather than trusted from the body; for
P1 it is taken from the body (local dev). Supports JSON (default) and SSE streaming of the
thought-stream for the GUI.
"""
from __future__ import annotations

import json
import os
import uuid

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from agents.common.context import RequestContext
from agents.supervisor.graph import run_supervisor

app = FastAPI(title="SRE Supervisor", version="0.1.0")


@app.get("/ping")
def ping():
    return {"status": "Healthy"}


def _context_from_body(body: dict) -> RequestContext:
    # P3 SEAM: replace body tenant_id with the verified JWT `tenant_id` claim.
    return RequestContext(
        tenant_id=body.get("tenant_id", ""),
        scenario_id=body.get("scenario_id", ""),
        session_id=body.get("session_id") or str(uuid.uuid4()),
        incident_id=body.get("incident_id", ""),
    )


@app.post("/invocations")
async def invocations(request: Request):
    body = await request.json()
    ctx = _context_from_body(body)
    alarm = body.get("alarm", "")
    try:
        ctx.require_tenant()
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

    if not body.get("stream"):
        result = run_supervisor(alarm, ctx)
        return JSONResponse(result)

    def event_generator():
        yield f"data: {json.dumps({'type': 'start', 'tenant_id': ctx.tenant_id})}\n\n"
        result = run_supervisor(alarm, ctx)
        for step in result.get("thought_stream", []):
            yield f"data: {json.dumps({'type': 'thought', 'text': step})}\n\n"
        yield f"data: {json.dumps({'type': 'result', 'result': result})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
