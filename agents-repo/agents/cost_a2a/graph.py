"""LangGraph graph for the cost specialist."""

from __future__ import annotations

from common.graph import build_react_agent
from agents.cost_a2a.prompts import COST_SYSTEM
from agents.cost_a2a.tools import get_tools


def build_graph():
    return build_react_agent(COST_SYSTEM, get_tools())
