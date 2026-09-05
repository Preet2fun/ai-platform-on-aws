# app/core/config.py
"""
Configuration management for the FastAPI backend.
Loads environment variables and provides typed settings.

All configurable values live here as the SINGLE SOURCE OF TRUTH.
Production values come from .env or ECS task environment.
Defaults are for local development only.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # --- AWS Core ---
    AWS_REGION: str = "us-east-1"
    AWS_PROFILE: Optional[str] = None
    
    # --- Authentication (Cognito) ---
    COGNITO_USER_POOL_ID: str
    COGNITO_CLIENT_ID: str
    COGNITO_CLIENT_SECRET: Optional[str] = Field(default=None, repr=False)
    
    # --- API ---
    API_VERSION: str = "v1"
    SERVICE_NAME: str = "msp-assistant-api"
    FRONTEND_URL: str = "http://localhost:5173"
    CLOUDFRONT_DOMAIN: Optional[str] = ""
    
    # --- Bedrock Model ---
    MODEL: str = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
    BEDROCK_KNOWLEDGE_BASE_ID: Optional[str] = ""
    
    # --- DynamoDB Tables ---
    CHAT_REQUESTS_TABLE: str = "msp-assistant-chat-requests"
    CONVERSATIONS_TABLE: str = "poc-conversations"
    
    # --- Observability ---
    OTEL_SERVICE_NAME: str = "msp-assistant-backend"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4318"
    
    # --- Jira ---
    JIRA_URL: Optional[str] = ""
    JIRA_EMAIL: Optional[str] = ""
    JIRA_API_TOKEN: Optional[str] = Field(default="", repr=False)
    JIRA_PROJECT_KEY: Optional[str] = ""
    UNRESOLVED_TICKET_EMAIL: Optional[str] = ""
    
    # --- Demo/Test ---
    API_ID: Optional[str] = ""
    TEST_ALARM_NAME: Optional[str] = ""
    
    # --- AgentCore (populated by deploy.sh) ---
    SUPERVISOR_RUNTIME_ARN: Optional[str] = ""
    GATEWAY_ARN: Optional[str] = ""
    GATEWAY_URL: Optional[str] = ""
    MEMORY_ID: Optional[str] = ""
    
    # --- A2A Specialist Runtime ARNs (populated by deploy.sh) ---
    CLOUDWATCH_A2A_ARN: Optional[str] = ""
    SECURITY_A2A_ARN: Optional[str] = ""
    COST_A2A_ARN: Optional[str] = ""
    ADVISOR_A2A_ARN: Optional[str] = ""
    JIRA_A2A_ARN: Optional[str] = ""
    KNOWLEDGE_A2A_ARN: Optional[str] = ""
    INVESTIGATOR_A2A_ARN: Optional[str] = ""
    
    # --- Remediation ---
    REMEDIATION_DETECTION_MODE: str = "llm"  # llm | regex
    GUARD_MODE: str = "demo"  # demo | production
    VERIFICATION_MAX_RETRIES: int = 3
    VERIFICATION_RETRY_DELAY_SECONDS: int = 30
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
