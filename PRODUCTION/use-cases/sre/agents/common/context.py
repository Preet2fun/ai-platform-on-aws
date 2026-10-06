"""Per-request tenant/scenario context.

Multi-tenancy requirement: every A2A hop and every tool call must carry the tenant identity so
data access, memory namespaces, and traces stay tenant-scoped. The supervisor extracts
`tenant_id` from the inbound JWT claim (P3) and threads it — plus the active `scenario_id`
(P0/P1 synthetic selection; a real deployment pins the live incident) and a `session_id` — into
every downstream call via this context object.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class RequestContext:
    tenant_id: str
    scenario_id: str = ""         # which synthetic incident is active (P0/P1); real deploy: live incident id
    session_id: str = ""          # AgentCore session id (>=33 chars; UUID)
    incident_id: str = ""         # logical incident identifier for memory/eval correlation
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RequestContext":
        d = dict(d or {})
        return cls(
            tenant_id=d.get("tenant_id", ""),
            scenario_id=d.get("scenario_id", ""),
            session_id=d.get("session_id", ""),
            incident_id=d.get("incident_id", ""),
            extra=d.get("extra", {}) or {},
        )

    def require_tenant(self) -> str:
        if not self.tenant_id:
            raise ValueError("tenant_id is required on every request (multi-tenant isolation)")
        return self.tenant_id
