"""AgentCore entry point for the advisor specialist (A2A protocol).

Deployed runtime: dev_advisor_a2a_runtime  (entryPoint: advisor_a2a_runtime.py)
"""

from __future__ import annotations

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from langchain_core.messages import HumanMessage

from common.observability import setup_logging
from agents.advisor_a2a.graph import build_graph

log = setup_logging()
app = BedrockAgentCoreApp()
_graph = build_graph()


@app.entrypoint
def handler(payload: dict) -> dict:
    """A2A entrypoint. Expects {"prompt": "..."}."""
    prompt = payload.get("prompt", "")
    log.info("advisor specialist received request")
    state = _graph.invoke({"messages": [HumanMessage(content=prompt)]})
    return {"response": state["messages"][-1].content}


if __name__ == "__main__":
    app.run()
