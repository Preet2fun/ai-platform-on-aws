"""Telemetry specialist — A2A runtime entrypoint (port 9000)."""
from __future__ import annotations

import os
import uvicorn

from agents.common.a2a import build_a2a_app, A2A_PORT
from agents.common.context import RequestContext
from agents.telemetry.agent import handle

app = build_a2a_app(
    name="SRE Telemetry Agent",
    description="Gathers and summarizes tenant-scoped metrics/logs/traces evidence for a hypothesis.",
    skills=[{"id": "gather-telemetry", "name": "Gather telemetry",
             "description": "Query metrics/logs/traces and summarize anomalous and normal signals with citations."}],
    handler=lambda text, ctx: handle(text, ctx),
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("A2A_PORT", A2A_PORT)))
