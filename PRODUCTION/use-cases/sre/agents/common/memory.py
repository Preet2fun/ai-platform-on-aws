"""AgentCore Memory adapter for the SRE investigator (long-term, episodic + semantic).

Why this exists
---------------
Without memory, the investigator re-derives every incident from scratch. This adapter gives it
long-term memory so it can:
  - RETRIEVE past incident episodes at `intake` (retrieve-before-act), to seed hypotheses with
    what was previously confirmed and what fixed it; and
  - WRITE an episode at `conclude` (write-after-act), capturing signature -> hypotheses tried ->
    confirmed/rejected -> root cause -> remediation.

Design choices
--------------
- **Direct records, not just async extraction.** Episodes are written with
  `batch_create_memory_records` as structured records we control, so recall is deterministic and
  immediately queryable (we do not depend on the async extraction pipeline for the episodic path).
  The memory resource still carries built-in strategies (SEMANTIC/EPISODIC) so conversational
  events can also be extracted, but the RCA episode path is explicit.
- **Multi-tenant isolation via namespace.** actorId = tenant_id, and every namespace is prefixed
  with the tenant: `sre/{tenant}/episodes`. A retrieve for one tenant can never match another
  tenant's namespace. This mirrors the tenant scoping enforced in the tools backend.
- **Fail-open / no-op when unconfigured.** If `SRE_MEMORY_ID` is unset (local dev / tests), every
  method is a safe no-op: retrieve returns [], write returns None. The investigator behaves exactly
  as it did pre-P2. Memory errors never fail an investigation — they are logged and swallowed.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any

from .context import RequestContext

log = logging.getLogger("sre.memory")

MEMORY_ID = os.getenv("SRE_MEMORY_ID", "")
# Relevance floor for retrieved episodes (cosine-similarity-derived score; not a percentage).
MIN_SCORE = float(os.getenv("SRE_MEMORY_MIN_SCORE", "0.2"))
TOP_K = int(os.getenv("SRE_MEMORY_TOP_K", "3"))


def _episodes_namespace(tenant_id: str) -> str:
    return f"sre/{tenant_id}/episodes"


def _facts_namespace(tenant_id: str) -> str:
    return f"sre/{tenant_id}/facts"


class SreMemory:
    """Long-term memory for the investigator. No-op when SRE_MEMORY_ID is unset."""

    def __init__(self, memory_id: str = MEMORY_ID, region: str | None = None):
        self.memory_id = memory_id
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self.memory_id)

    def _client_lazy(self):
        if self._client is None:
            import boto3  # lazy so local/test runs without creds don't import-fail
            from botocore.config import Config

            self._client = boto3.client(
                "bedrock-agentcore",
                region_name=self.region,
                config=Config(read_timeout=30, connect_timeout=5, retries={"max_attempts": 2}),
            )
        return self._client

    # --------------------------- retrieve (intake) ---------------------------

    def retrieve_episodes(self, ctx: RequestContext, query: str, top_k: int = TOP_K) -> list[dict[str, Any]]:
        """Return past incident episodes for THIS tenant relevant to `query`.

        Returns a list of {content, score} dicts, highest score first, filtered by MIN_SCORE.
        No-op (returns []) when memory is disabled or on any error.
        """
        if not self.enabled or not query.strip():
            return []
        tenant = ctx.require_tenant()
        try:
            resp = self._client_lazy().retrieve_memory_records(
                memoryId=self.memory_id,
                namespace=_episodes_namespace(tenant),
                searchCriteria={"searchQuery": query[:10000], "topK": top_k},
            )
        except Exception as e:  # noqa: BLE001 - memory must never break an investigation
            log.warning("memory retrieve failed (tenant=%s): %s", tenant, e)
            return []

        out: list[dict[str, Any]] = []
        for rec in resp.get("memoryRecordSummaries", []) or []:
            score = rec.get("score", 0.0) or 0.0
            if score < MIN_SCORE:
                continue
            content = rec.get("content") or {}
            text = content.get("text") if isinstance(content, dict) else str(content)
            out.append({"text": text or "", "score": score})
        out.sort(key=lambda r: r["score"], reverse=True)
        return out

    # --------------------------- write (conclude) ---------------------------

    def write_episode(self, ctx: RequestContext, *, signature: str, episode_text: str) -> str | None:
        """Persist one incident episode for THIS tenant. Returns the record id, or None if disabled.

        `signature` is a short, searchable description of the incident (what future retrievals match
        on); `episode_text` is the full structured episode body. Both are stored in the record text
        so semantic search over the namespace can surface it. Errors are swallowed (logged).
        """
        if not self.enabled:
            return None
        tenant = ctx.require_tenant()
        req_id = f"ep-{uuid.uuid4().hex}"[:80]
        body = f"INCIDENT SIGNATURE: {signature}\n\n{episode_text}"
        try:
            resp = self._client_lazy().batch_create_memory_records(
                memoryId=self.memory_id,
                records=[{
                    "requestIdentifier": req_id,
                    "namespaces": [_episodes_namespace(tenant)],
                    "content": {"text": body},
                    "timestamp": time.time(),
                }],
            )
        except Exception as e:  # noqa: BLE001
            log.warning("memory write failed (tenant=%s): %s", tenant, e)
            return None
        created = resp.get("successfulRecords") or resp.get("records") or []
        if created:
            return created[0].get("memoryRecordId") or req_id
        return req_id


def incident_signature(alarm: str, seed_signals: dict[str, Any]) -> str:
    """Build a compact, stable signature for an incident from the alarm + seed snapshot.

    Used both as the retrieval query at intake and as the stored signature at conclude, so a
    recurring incident produces a similar signature and matches its own past episode.
    """
    changes = seed_signals.get("recent_changes", []) if seed_signals else []
    svcs = sorted({c.get("service", "") for c in changes if c.get("service")})
    change_kinds = sorted({c.get("type", "") for c in changes if c.get("type")})
    parts = [alarm.strip()]
    if svcs:
        parts.append("services=" + ",".join(svcs))
    if change_kinds:
        parts.append("changes=" + ",".join(change_kinds))
    return " | ".join(p for p in parts if p)
