"""Remediation (HITL) specialist — A2A runtime entrypoint (port 9000)."""
from __future__ import annotations

import os
import uvicorn

from agents.common.a2a import build_a2a_app, A2A_PORT
from agents.remediation.agent import handle

app = build_a2a_app(
    name="SRE Remediation Agent",
    description="Proposes a HITL-gated remediation + ticket draft for a confirmed root cause. Never auto-applies.",
    skills=[{"id": "propose-remediation", "name": "Propose remediation",
             "description": "Given a confirmed root cause, propose actions + ticket draft requiring human approval."}],
    handler=lambda text, ctx: handle(text, ctx),
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("A2A_PORT", A2A_PORT)))
