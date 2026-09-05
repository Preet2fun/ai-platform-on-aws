"""AgentCore entry point for the supervisor (HTTP protocol).

Deployed runtime: dev_msp_supervisor_agent  (entryPoint: supervisor_runtime.py)

The BedrockAgentCoreApp harness exposes this as the runtime's HTTP handler.
Locally, `python -m agents.supervisor.supervisor_runtime` runs a REPL.
"""

from __future__ import annotations

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from langchain_core.messages import HumanMessage

from common.observability import setup_logging
from agents.supervisor.graph import build_graph

log = setup_logging()
app = BedrockAgentCoreApp()
_graph = build_graph()


@app.entrypoint
def handler(payload: dict) -> dict:
    """Runtime entrypoint. Expects {"prompt": "..."} (and optional session_id)."""
    prompt = payload.get("prompt", "")
    session_id = payload.get("session_id", "")
    log.info("supervisor received request (session=%s)", session_id or "-")
    state = _graph.invoke({"messages": [HumanMessage(content=prompt)]})
    answer = state["messages"][-1].content
    return {"response": answer}


if __name__ == "__main__":
    # Local dev REPL
    import sys

    if sys.stdin.isatty():
        print("Supervisor local REPL. Ctrl-D to exit.")
        for line in sys.stdin:
            line = line.strip()
            if line:
                print(handler({"prompt": line})["response"])
    else:
        app.run()
