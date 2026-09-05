"""LangGraph base builder shared by all specialist agents.

Provides a standard ReAct-style tool-calling agent graph so each specialist only
needs to supply its system prompt and its tools.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from common.llm import build_llm


def build_react_agent(
    system_prompt: str,
    tools: Sequence[BaseTool] | None = None,
    *,
    model_id: str | None = None,
) -> Any:
    """Build a LangGraph ReAct agent (LLM + tools + system prompt).

    Args:
        system_prompt: the agent's role/instructions.
        tools: LangChain tools the agent may call (defaults to none).
        model_id: optional Bedrock model override for this agent.

    Returns:
        A compiled LangGraph graph exposing .invoke / .stream.
    """
    llm = build_llm(model_id=model_id)
    return create_react_agent(
        model=llm,
        tools=list(tools or []),
        prompt=system_prompt,
    )
