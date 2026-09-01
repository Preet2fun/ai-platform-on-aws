"""Bedrock LLM factory for LangGraph/LangChain agents.

Uses langchain-aws ChatBedrockConverse against the account's cross-region
inference profiles (e.g. us.anthropic.claude-sonnet-4-5-...).
"""

from __future__ import annotations

from langchain_aws import ChatBedrockConverse

from common.config import Settings, get_settings


def build_llm(settings: Settings | None = None, *, model_id: str | None = None):
    """Return a configured Bedrock chat model.

    Args:
        settings: optional Settings override (defaults to get_settings()).
        model_id: optional per-agent model override.
    """
    s = settings or get_settings()
    return ChatBedrockConverse(
        model=model_id or s.model_id,
        region_name=s.region,
        temperature=s.temperature,
        max_tokens=s.max_tokens,
        # NOTE: attach a Bedrock Guardrail here once one is configured, e.g.:
        # guardrail_config={"guardrailIdentifier": "...", "guardrailVersion": "1"}
    )
