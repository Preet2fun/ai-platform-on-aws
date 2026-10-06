"""Supervisor orchestration (LangGraph).

Entry point for an incident. Flow:
  receive (tenant + alarm + scenario) -> investigate (A2A -> investigator) ->
  propose_remediation (A2A -> remediation, only if a root cause was confirmed) -> aggregate.

The supervisor is deliberately thin: the heavy hypothesis loop lives in the investigator. The
supervisor owns tenant-context propagation, delegation, and assembling the final response the GUI
renders. When specialist A2A URLs aren't configured (local single-process dev/tests), it calls the
specialist handlers in-process via the same code path.
"""
from __future__ import annotations

import json
import os
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from agents.common.context import RequestContext
from agents.common.a2a import A2AClient

INVESTIGATOR_AGENT_URL = os.getenv("INVESTIGATOR_AGENT_URL", "")
REMEDIATION_AGENT_URL = os.getenv("REMEDIATION_AGENT_URL", "")


class SupervisorState(TypedDict, total=False):
    context: dict
    alarm: str
    investigation: dict        # the investigator's full payload
    remediation: dict          # the remediation proposal (if confirmed)
    response: dict             # aggregated final response


def _ctx(state: SupervisorState) -> RequestContext:
    return RequestContext.from_dict(state["context"])


def node_investigate(state: SupervisorState) -> SupervisorState:
    ctx = _ctx(state)
    if INVESTIGATOR_AGENT_URL:
        raw = A2AClient(INVESTIGATOR_AGENT_URL).send(state.get("alarm", ""), ctx)
        try:
            state["investigation"] = json.loads(raw)
        except Exception:
            state["investigation"] = {"raw": raw}
    else:
        from agents.investigator.graph import run_investigation  # local fallback
        result = run_investigation(alarm=state.get("alarm", ""), ctx=ctx)
        state["investigation"] = {
            "alarm": result.get("alarm", ""),
            "hypotheses": result.get("hypotheses", []),
            "conclusion": result.get("conclusion", {}),
            "thought_stream": result.get("thought_stream", []),
        }
    return state


def _confirmed_root_cause(investigation: dict) -> str | None:
    concl = investigation.get("conclusion") or {}
    if concl.get("confirmed_hypothesis_id") and (concl.get("confidence") in ("high", "medium")):
        return concl.get("root_cause")
    # also accept if any hypothesis is confirmed
    for h in investigation.get("hypotheses", []):
        if h.get("status") == "confirmed":
            return concl.get("root_cause") or h.get("statement")
    return None


def node_remediate(state: SupervisorState) -> SupervisorState:
    ctx = _ctx(state)
    rc = _confirmed_root_cause(state.get("investigation", {}))
    if not rc:
        state["remediation"] = {"status": "skipped", "reason": "no confirmed root cause"}
        return state
    if REMEDIATION_AGENT_URL:
        raw = A2AClient(REMEDIATION_AGENT_URL).send(rc, ctx)
    else:
        from agents.remediation.agent import handle as rem_handle  # local fallback
        raw = rem_handle(rc, ctx)
    try:
        state["remediation"] = json.loads(raw)
    except Exception:
        state["remediation"] = {"proposal": raw}
    return state


def node_aggregate(state: SupervisorState) -> SupervisorState:
    ctx = _ctx(state)
    inv = state.get("investigation", {})
    state["response"] = {
        "tenant_id": ctx.tenant_id,
        "scenario_id": ctx.scenario_id,
        "alarm": state.get("alarm", ""),
        "hypotheses": inv.get("hypotheses", []),
        "conclusion": inv.get("conclusion", {}),
        "remediation": state.get("remediation", {}),
        "thought_stream": inv.get("thought_stream", []),
    }
    return state


def build_graph():
    g = StateGraph(SupervisorState)
    g.add_node("investigate", node_investigate)
    g.add_node("remediate", node_remediate)
    g.add_node("aggregate", node_aggregate)
    g.set_entry_point("investigate")
    g.add_edge("investigate", "remediate")
    g.add_edge("remediate", "aggregate")
    g.add_edge("aggregate", END)
    return g.compile()


_GRAPH = None


def run_supervisor(alarm: str, ctx: RequestContext) -> dict[str, Any]:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    out = _GRAPH.invoke({"context": ctx.to_dict(), "alarm": alarm})
    return out.get("response", {})
