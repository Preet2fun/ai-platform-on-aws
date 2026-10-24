"""P8 GUI backend-for-frontend (BFF).

A browser cannot call the JWT-protected supervisor runtime directly (it needs a Cognito M2M token
+ the AgentCore SigV4 invoke endpoint; secrets must never reach the browser). This thin FastAPI
BFF holds the invoke logic and streams results to the UI over SSE:

  browser  --(SSE)-->  BFF  --(M2M token + invoke_agent_runtime)-->  supervisor runtime

It reuses evals/client.py for the token + invocation. The M2M client secret stays server-side
(fetched from Cognito at runtime). This is dev tooling (localhost); a user-facing deployment would
need its own inbound auth on the BFF (flagged for the security review).

Run (from PRODUCTION/use-cases/sre, with AWS creds):
  AWS_PROFILE=agentcore AWS_REGION=us-east-1 uvicorn gui.server:app --port 8900
Then open http://localhost:8900
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from evals import client

SRE_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = SRE_ROOT / "synthetic-data" / "tenants"
STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="SRE Hypothesis Board")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/app.js")
def appjs():
    return FileResponse(STATIC / "app.js")


@app.get("/styles.css")
def styles():
    return FileResponse(STATIC / "styles.css")


@app.get("/api/scenarios")
def scenarios():
    """Tenants + their scenarios (from the registry) to populate the picker, with the manifest
    alarm text as the default prompt. Manifest ground truth is NOT exposed to the UI."""
    with open(DATA_ROOT / "registry.yaml", encoding="utf-8") as f:
        reg = yaml.safe_load(f)
    out = []
    for t in reg.get("tenants", []):
        scen = []
        for sid in t.get("scenarios", []):
            alarm = sid
            mpath = DATA_ROOT / t["tenant_id"] / "scenarios" / sid / "manifest.yaml"
            if mpath.exists():
                m = yaml.safe_load(open(mpath, encoding="utf-8"))
                a = m.get("alarm", {})
                alarm = f"{a.get('name', sid)} — {m.get('title', '')}".strip(" —")
            scen.append({"scenario_id": sid, "alarm": alarm})
        out.append({"tenant_id": t["tenant_id"], "display_name": t.get("display_name", t["tenant_id"]),
                    "scenarios": scen})
    return {"tenants": out}


@app.post("/api/investigate")
async def investigate(request: Request):
    body = await request.json()
    tenant = body.get("tenant_id")
    scenario = body.get("scenario_id")
    alarm = body.get("alarm") or scenario
    if not tenant or not scenario:
        return JSONResponse(status_code=400, content={"error": "tenant_id and scenario_id required"})

    def gen():
        yield _sse({"type": "start", "tenant_id": tenant, "scenario_id": scenario, "alarm": alarm})
        yield _sse({"type": "status", "text": "Dispatching to supervisor (this runs the full A2A investigation, ~1-3 min)..."})
        try:
            result = client.run_investigation(tenant, scenario, alarm)
        except Exception as e:  # noqa: BLE001
            yield _sse({"type": "error", "text": f"investigation failed: {e}"})
            yield _sse({"type": "done"})
            return
        # Replay the thought-stream as events (lean mode: arrives after completion), then the board.
        for step in result.get("thought_stream", []):
            yield _sse({"type": "thought", "text": step})
        yield _sse({"type": "result", "result": result})
        yield _sse({"type": "done"})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"
