"""Supervisor LangGraph: an LLM router that delegates to A2A specialists.

Pattern: the LLM decides which specialist(s) to call; a `route_to_specialist`
tool invokes the specialist runtime over A2A (bedrock-agentcore:InvokeAgentRuntime)
and feeds the result back into the graph until the supervisor produces a final answer.
"""

from __future__ import annotations

from langchain_core.tools import tool

from common.a2a import A2AClient
from common.graph import build_react_agent
from agents.supervisor.prompts import SUPERVISOR_SYSTEM

SPECIALISTS = [
    "security",
    "cost",
    "cloudwatch",
    "jira",
    "knowledge",
    "investigator",
    "advisor",
]


def _make_tools(a2a: A2AClient):
    @tool
    def route_to_specialist(specialist: str, request: str, session_id: str = "") -> str:
        """Route a request to a specialist agent and return its response.

        Args:
            specialist: one of security, cost, cloudwatch, jira, knowledge,
                investigator, advisor.
            request: the natural-language request to hand to the specialist.
            session_id: optional session id for multi-turn continuity.
        """
        if specialist not in SPECIALISTS:
            return f"Unknown specialist '{specialist}'. Valid: {', '.join(SPECIALISTS)}"
        result = a2a.invoke(specialist, {"prompt": request}, session_id=session_id or None)
        return str(result)

    return [route_to_specialist]


def build_graph():
    """Compile and return the supervisor graph."""
    a2a = A2AClient()
    return build_react_agent(SUPERVISOR_SYSTEM, _make_tools(a2a))
