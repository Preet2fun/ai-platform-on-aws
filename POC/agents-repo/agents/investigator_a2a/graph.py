"""LangGraph graph for the investigator specialist."""

from __future__ import annotations

from common.graph import build_react_agent
from agents.investigator_a2a.prompts import INVESTIGATOR_SYSTEM
from agents.investigator_a2a.tools import get_tools


def build_graph():
    return build_react_agent(INVESTIGATOR_SYSTEM, get_tools())
