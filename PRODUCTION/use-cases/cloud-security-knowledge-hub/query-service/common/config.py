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
    generation_model_id: str = os.getenv("GENERATION_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    embedding_dim: int = int(os.getenv("EMBEDDING_DIM", "1024"))
    top_k: int = int(os.getenv("TOP_K", "6"))
    guardrail_id: str = os.getenv("GUARDRAIL_ID", "")
    guardrail_version: str = os.getenv("GUARDRAIL_VERSION", "DRAFT")

    # Rerank (Phase-2 Stage 2): retrieve a wider candidate pool, then re-order by relevance.
    rerank_model_id: str = os.getenv("RERANK_MODEL_ID", "cohere.rerank-v3-5:0")
    rerank_candidate_k: int = int(os.getenv("RERANK_CANDIDATE_K", "20"))

    # Query transformation (Phase-2 Stage 3): generate N reworded variants of the question,
    # retrieve for each, merge+dedup the candidates (broadens recall before rerank).
    query_transform_n: int = int(os.getenv("QUERY_TRANSFORM_N", "3"))
    merged_candidate_cap: int = int(os.getenv("MERGED_CANDIDATE_CAP", "60"))

    # CRAG (Phase-2 Stage 5): grade retrieved context via the reranker's top relevance score;
    # if below this floor, take the corrective action (honest IDK) instead of stretching thin
    # context into a shaky answer. Requires rerank on (that's the grade source).
    crag_min_relevance: float = float(os.getenv("CRAG_MIN_RELEVANCE", "0.30"))

    # Phase-2 feature flags (OFF = baseline)
    enable_hybrid: bool = _flag("ENABLE_HYBRID")
    enable_rerank: bool = _flag("ENABLE_RERANK")
    enable_query_transform: bool = _flag("ENABLE_QUERY_TRANSFORM")
    enable_chain_of_note: bool = _flag("ENABLE_CHAIN_OF_NOTE")
    enable_crag: bool = _flag("ENABLE_CRAG")
    # Metadata filtering (Phase-2 / FI-3): when a query names an AWS service, restrict retrieval
    # to chunks tagged with that service so the answer chunk isn't crowded out by a large
    # multi-service doc. Non-fatal: falls back to unfiltered if too few filtered candidates.
    enable_metadata_filter: bool = _flag("ENABLE_METADATA_FILTER")

    @property
    def guardrails_enabled(self) -> bool:
        return bool(self.guardrail_id)


def get_settings() -> Settings:
    return Settings()
