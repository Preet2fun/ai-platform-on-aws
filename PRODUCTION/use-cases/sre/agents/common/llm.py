"""Bedrock Claude LLM factory (LangChain) — the single model entry point for every agent.

Model is Claude Sonnet (per the approved decision), via `langchain-aws`'s ChatBedrockConverse,
which supports tool-calling and structured output used by the LangGraph agents. Region, model id,
and temperature come from env so the same code runs locally and in the AgentCore container.
"""
from __future__ import annotations

import os
from functools import lru_cache

# Default to the Claude Sonnet inference profile used across this platform.
DEFAULT_MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
DEFAULT_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))
DEFAULT_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2048"))


@lru_cache(maxsize=8)
def get_llm(model_id: str = DEFAULT_MODEL_ID,
            temperature: float = DEFAULT_TEMPERATURE,
            max_tokens: int = DEFAULT_MAX_TOKENS):
    """Return a cached ChatBedrockConverse bound to Claude on Bedrock.

    Lazy import so unit tests / tooling that don't call the model don't need langchain-aws
    installed, and so container cold-start only pays the import once.
    """
    from langchain_aws import ChatBedrockConverse

    return ChatBedrockConverse(
        model=model_id,
        region_name=AWS_REGION,
        temperature=temperature,
        max_tokens=max_tokens,
    )
