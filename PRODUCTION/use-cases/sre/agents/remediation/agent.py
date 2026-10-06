"""Remediation specialist (A2A) — proposes a HITL-gated fix + ticket. NEVER auto-applies.

Role: given a confirmed root cause, propose a concrete remediation and a ticket draft (title,
summary, suggested actions, risk, rollback). It returns a PROPOSAL only — any change action is
gated behind human approval (enforced in the GUI/supervisor in P8, and by not wiring any
write-capable tool here). This keeps the SRE agent safe by construction.
"""
from __future__ import annotations

import json

from agents.common.context import RequestContext
from agents.common.llm import get_llm
from agents.common.tools_client import ToolsClient

_SYSTEM = """You are an SRE remediation planner. Given a confirmed root cause (and any matching
runbook), produce a remediation PROPOSAL as JSON:
{"ticket_title":"...","summary":"...","suggested_actions":["..."],"risk":"low|medium|high",
"rollback":"...","requires_approval":true}.
You NEVER execute changes — you only propose. Always set requires_approval true. Keep actions
concrete and ordered (immediate mitigation first, then durable fix, then preventative alarm)."""


def handle(root_cause: str, ctx: RequestContext, client: ToolsClient | None = None) -> str:
    client = client or ToolsClient()
    runbooks = client.runbooks(ctx, query=root_cause[:80])
    llm = get_llm()
    prompt = (f"CONFIRMED ROOT CAUSE: {root_cause}\n\n"
              f"MATCHING RUNBOOKS (JSON):\n{json.dumps(runbooks, indent=2)[:6000]}\n\n"
              "Produce the remediation proposal JSON.")
    resp = llm.invoke([("system", _SYSTEM), ("user", prompt)])
    return resp.content if hasattr(resp, "content") else str(resp)
