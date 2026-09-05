"""LangGraph graph for the cloudwatch specialist."""

from __future__ import annotations

from common.graph import build_react_agent
from agents.cloudwatch_a2a.prompts import CLOUDWATCH_SYSTEM
from agents.cloudwatch_a2a.tools import get_tools


def build_graph():
    return build_react_agent(CLOUDWATCH_SYSTEM, get_tools())
