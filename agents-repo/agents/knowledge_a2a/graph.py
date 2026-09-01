"""LangGraph graph for the knowledge specialist."""

from __future__ import annotations

from common.graph import build_react_agent
from agents.knowledge_a2a.prompts import KNOWLEDGE_SYSTEM
from agents.knowledge_a2a.tools import get_tools


def build_graph():
    return build_react_agent(KNOWLEDGE_SYSTEM, get_tools())
