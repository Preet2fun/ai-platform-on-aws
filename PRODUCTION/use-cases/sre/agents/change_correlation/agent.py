"""Change-correlation specialist (A2A) — ties deploys/config/infra changes to the symptom timeline.

Role: given the incident window and symptom onset, return which changes (deploys, config edits,
scaling, infra events, k8s events) line up with the symptom onset and are plausible triggers —
and which are unrelated. This is what lets the investigator connect "a deploy at 14:08" to
"symptom at 14:20". Read-only.
"""
from __future__ import annotations

import json

from agents.common.context import RequestContext
from agents.common.llm import get_llm
from agents.common.tools_client import ToolsClient

_SYSTEM = """You are an SRE change-correlation analyst. Given a QUESTION (usually about what
changed around the incident) plus the tenant-scoped change log and platform/k8s events, identify:
- Which changes/events are TEMPORALLY ALIGNED with the symptom onset and are plausible triggers
  (state the change, its timestamp, and why it could cause the symptom).
- Which changes are UNRELATED (too early, wrong service, cosmetic) — say so, so the investigator
  can rule them out.
Be specific with timestamps and refs. Return 3-6 short bullet points. Do not invent changes."""


def _gather(client: ToolsClient, ctx: RequestContext) -> dict:
    return {
        "changes": client.changes(ctx),
        "events": client.events(ctx),
    }


def handle(question: str, ctx: RequestContext, client: ToolsClient | None = None) -> str:
    client = client or ToolsClient()
    data = _gather(client, ctx)
    llm = get_llm()
    prompt = (
        f"QUESTION: {question}\n\n"
        f"TENANT: {ctx.tenant_id}\n"
        f"CHANGE LOG + EVENTS (JSON):\n{json.dumps(data, indent=2)[:12000]}\n\n"
        "Correlate changes/events to the symptom per the instructions."
    )
    resp = llm.invoke([("system", _SYSTEM), ("user", prompt)])
    return resp.content if hasattr(resp, "content") else str(resp)
