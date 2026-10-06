"""Investigator / Hypothesis specialist — A2A runtime entrypoint (port 9000).

Returns the full investigation result (hypotheses with lanes + conclusion + thought stream) as a
JSON string in the A2A artifact, so the supervisor and the P8 GUI can render the hypothesis board.
"""
from __future__ import annotations

import json
import os
import uvicorn

from agents.common.a2a import build_a2a_app, A2A_PORT
from agents.common.context import RequestContext
from agents.investigator.graph import run_investigation


def _handle(text: str, ctx: RequestContext) -> str:
    result = run_investigation(alarm=text, ctx=ctx)
    # return a compact, GUI/eval-friendly payload
    payload = {
        "alarm": result.get("alarm", ""),
        "hypotheses": result.get("hypotheses", []),
        "conclusion": result.get("conclusion", {}),
        "thought_stream": result.get("thought_stream", []),
    }
    return json.dumps(payload)


app = build_a2a_app(
    name="SRE Investigator Agent",
    description="Hypothesis-driven root-cause investigation: generates competing hypotheses, "
                "gathers evidence, rejects wrong ones, and concludes with a cited root cause.",
    skills=[{"id": "investigate-incident", "name": "Investigate incident",
             "description": "Run a hypothesis-driven RCA over an alarm and return hypotheses + conclusion."}],
    handler=_handle,
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("A2A_PORT", A2A_PORT)))
