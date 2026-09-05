"""Centralized configuration, sourced from environment variables.

Mirrors the env vars set on the deployed AgentCore runtimes (notably
BEDROCK_AGENTCORE_MEMORY_ID / _NAME) plus shared model/gateway/cognito config.
"""

from __future__ import annotations

import functools
import os

from pydantic import BaseModel, Field


class Settings(BaseModel):
    # AWS
    region: str = Field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    account_id: str = Field(default_factory=lambda: os.getenv("AWS_ACCOUNT_ID", ""))

    # Bedrock model
    model_id: str = Field(
        default_factory=lambda: os.getenv(
            "BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
        )
    )
    temperature: float = Field(default_factory=lambda: float(os.getenv("BEDROCK_TEMPERATURE", "0.2")))
    max_tokens: int = Field(default_factory=lambda: int(os.getenv("BEDROCK_MAX_TOKENS", "4096")))

    # AgentCore Memory (per-runtime)
    memory_id: str = Field(default_factory=lambda: os.getenv("BEDROCK_AGENTCORE_MEMORY_ID", ""))
    memory_name: str = Field(default_factory=lambda: os.getenv("BEDROCK_AGENTCORE_MEMORY_NAME", ""))

    # AgentCore Gateway (MCP)
    gateway_url: str = Field(default_factory=lambda: os.getenv("AGENTCORE_GATEWAY_URL", ""))

    # Cognito (MCP runtime JWT auth)
    cognito_pool_id: str = Field(default_factory=lambda: os.getenv("COGNITO_USER_POOL_ID", ""))
    cognito_client_id: str = Field(default_factory=lambda: os.getenv("COGNITO_M2M_CLIENT_ID", ""))
    cognito_scope: str = Field(default_factory=lambda: os.getenv("COGNITO_SCOPE", "mcp-server/invoke"))
    cognito_token_url: str = Field(default_factory=lambda: os.getenv("COGNITO_TOKEN_URL", ""))

    # Credential providers (AgentCore Identity token vault)
    jira_api_key_provider: str = Field(
        default_factory=lambda: os.getenv("JIRA_API_KEY_PROVIDER", "dev-jira-api-key")
    )
    gateway_oauth2_provider: str = Field(
        default_factory=lambda: os.getenv("GATEWAY_OAUTH2_PROVIDER", "dev-msp-gateway-cognito")
    )

    # Observability
    otel_enabled: bool = Field(default_factory=lambda: os.getenv("OTEL_ENABLED", "true").lower() == "true")
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    def a2a_arn(self, specialist: str) -> str:
        """Resolve a specialist's runtime ARN from A2A_<NAME>_ARN env var."""
        return os.getenv(f"A2A_{specialist.upper()}_ARN", "")


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
