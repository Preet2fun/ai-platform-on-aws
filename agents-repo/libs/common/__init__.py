"""Shared building blocks for the Motadata MSP AI Assistant agents.

Everything agents need in common lives here: config, the Bedrock LLM factory,
the AgentCore Memory client, identity/credential helpers, the LangGraph base
builder, and observability setup.
"""

from common.config import Settings, get_settings
from common.llm import build_llm
from common.memory import MemoryClient
from common.graph import build_react_agent

__all__ = [
    "Settings",
    "get_settings",
    "build_llm",
    "MemoryClient",
    "build_react_agent",
]
