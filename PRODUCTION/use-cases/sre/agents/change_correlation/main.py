"""Change-correlation specialist — A2A runtime entrypoint (port 9000)."""
from __future__ import annotations

import os
import uvicorn

from agents.common.a2a import build_a2a_app, A2A_PORT
from agents.change_correlation.agent import handle

app = build_a2a_app(
    name="SRE Change Correlation Agent",
    description="Correlates deploys/config/scaling/infra changes and k8s events to the incident timeline.",
    skills=[{"id": "correlate-changes", "name": "Correlate changes",
             "description": "Identify changes temporally aligned with symptom onset vs unrelated changes."}],
    handler=lambda text, ctx: handle(text, ctx),
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("A2A_PORT", A2A_PORT)))
