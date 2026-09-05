"""Thin client over AgentCore Memory (short-term events + long-term records).

The deployed per-agent runtimes currently use short-term memory only
(strategies: []). This client supports both STM event create/list and the
long-term retrieve API so agents can adopt semantic/summary/episodic strategies
without code changes once those strategies are attached to the memory resource.
"""

from __future__ import annotations

import time
from typing import Any

import boto3

from common.config import Settings, get_settings


class MemoryClient:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        # Data-plane client for events + retrieval
        self._dp = boto3.client("bedrock-agentcore", region_name=self.s.region)

    # ── short-term memory (raw events) ──────────────────────────────
    def add_event(self, actor_id: str, session_id: str, payload: list[dict[str, Any]]) -> dict:
        """Append a conversational event to short-term memory."""
        return self._dp.create_event(
            memoryId=self.s.memory_id,
            actorId=actor_id,
            sessionId=session_id,
            eventTimestamp=time.time(),
            payload=payload,
        )

    def recent_events(self, actor_id: str, session_id: str, max_results: int = 20) -> list[dict]:
        resp = self._dp.list_events(
            memoryId=self.s.memory_id,
            actorId=actor_id,
            sessionId=session_id,
            maxResults=max_results,
        )
        return resp.get("events", [])

    # ── long-term memory (semantic/summary/episodic records) ────────
    def retrieve(self, namespace: str, query: str, top_k: int = 5) -> list[dict]:
        """Semantic retrieval of long-term memory records.

        No-op-safe: returns [] if the memory has no long-term strategies yet.
        """
        try:
            resp = self._dp.retrieve_memory_records(
                memoryId=self.s.memory_id,
                namespace=namespace,
                searchCriteria={"searchQuery": query, "topK": top_k},
            )
            return resp.get("memoryRecordSummaries", [])
        except self._dp.exceptions.ClientError:
            # e.g. no strategy configured; degrade gracefully to STM-only behavior
            return []
