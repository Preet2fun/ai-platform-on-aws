"""LangGraph graph for the jira specialist."""

from __future__ import annotations

from common.graph import build_react_agent
from agents.jira_a2a.prompts import JIRA_SYSTEM
from agents.jira_a2a.tools import get_tools


def build_graph():
    return build_react_agent(JIRA_SYSTEM, get_tools())
