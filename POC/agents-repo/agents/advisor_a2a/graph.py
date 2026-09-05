"""LangGraph graph for the advisor specialist."""

from __future__ import annotations

from common.graph import build_react_agent
from agents.advisor_a2a.prompts import ADVISOR_SYSTEM
from agents.advisor_a2a.tools import get_tools


def build_graph():
    return build_react_agent(ADVISOR_SYSTEM, get_tools())
