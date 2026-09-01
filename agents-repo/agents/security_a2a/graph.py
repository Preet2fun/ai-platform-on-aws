"""LangGraph graph for the security specialist."""

from __future__ import annotations

from common.graph import build_react_agent
from agents.security_a2a.prompts import SECURITY_SYSTEM
from agents.security_a2a.tools import get_tools


def build_graph():
    return build_react_agent(SECURITY_SYSTEM, get_tools())
