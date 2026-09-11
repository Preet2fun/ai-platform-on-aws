"""Runtime configuration + Phase-2 feature flags for the query service.

Phase 1 (baseline) runs with all advanced flags OFF. Phase 2 turns them on one at a time
so each stage's impact is measured against the baseline (see AI-SDLC-AND-EVALS.md).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() == "true"


@dataclass(frozen=True)
class Settings:
    region: str = os.getenv("AWS_REGION", "us-east-1")
    db_endpoint: str = os.getenv("DB_ENDPOINT", "")
    db_name: str = os.getenv("DB_NAME", "cshub")
    db_secret_arn: str = os.getenv("DB_SECRET_ARN", "")
    embedding_model_id: str = os.getenv("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
    generation_model_id: str = os.getenv("GENERATION_MODEL_ID", "anthropic.claude-sonnet-4-5-20250929-v1:0")
    embedding_dim: int = int(os.getenv("EMBEDDING_DIM", "1024"))
    top_k: int = int(os.getenv("TOP_K", "6"))
    guardrail_id: str = os.getenv("GUARDRAIL_ID", "")
    guardrail_version: str = os.getenv("GUARDRAIL_VERSION", "DRAFT")

    # Phase-2 feature flags (OFF = baseline)
    enable_hybrid: bool = _flag("ENABLE_HYBRID")
    enable_rerank: bool = _flag("ENABLE_RERANK")
    enable_query_transform: bool = _flag("ENABLE_QUERY_TRANSFORM")
    enable_chain_of_note: bool = _flag("ENABLE_CHAIN_OF_NOTE")
    enable_crag: bool = _flag("ENABLE_CRAG")

    @property
    def guardrails_enabled(self) -> bool:
        return bool(self.guardrail_id)


def get_settings() -> Settings:
    return Settings()
