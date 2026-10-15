"""Investigator / Hypothesis agent — the hypothesis-driven RCA engine (LangGraph).

Implements the diagnosis loop from the plan:
  intake -> generate_hypotheses -> gather_evidence (delegates to telemetry + change agents via A2A)
         -> evaluate_hypotheses (confirm/reject with a grumpy critic) -> converge? -> conclude

State is a typed dict carried through the graph. Each hypothesis moves across lanes
(candidate -> investigating -> confirmed|rejected) and carries its evidence + reasons — this is
exactly what the P8 GUI hypothesis board renders, and what the P7 eval scores against the
scenario's ground-truth `expected_hypotheses`.

Evidence gathering delegates to the specialist A2A agents when their URLs are configured;
otherwise it falls back to calling the tools client directly (useful for local single-process
runs and tests). Memory (P2) will hook into `intake` (retrieve past episodes) and `conclude`
(write the episode) — left as clearly marked seams here.
"""
from __future__ import annotations

import json
import os
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from agents.common.context import RequestContext
from agents.common.llm import get_llm
from agents.common.a2a import A2AClient
from agents.common.tools_client import ToolsClient
from agents.common.memory import SreMemory, incident_signature

MAX_ROUNDS = int(os.getenv("INVESTIGATOR_MAX_ROUNDS", "2"))

# A specialist target may be an http(s) URL (local) or an AgentCore Runtime ARN (cloud).
# The *_AGENT_ARN form (set by CloudFormation) takes precedence; *_AGENT_URL stays for local dev.
# A2AClient auto-detects the transport from the string; empty -> in-process fallback.
TELEMETRY_AGENT_URL = os.getenv("TELEMETRY_AGENT_ARN") or os.getenv("TELEMETRY_AGENT_URL", "")
CHANGE_AGENT_URL = os.getenv("CHANGE_AGENT_ARN") or os.getenv("CHANGE_AGENT_URL", "")

# Long-term memory (episodic). No-op when SRE_MEMORY_ID is unset (local dev / tests).
_MEMORY = SreMemory()


class InvestigationState(TypedDict, total=False):
    context: dict               # RequestContext.to_dict()
    alarm: str                  # the triggering alarm / symptom description
    seed_signals: dict          # compact starting snapshot (changes + error logs/traces)
    hypotheses: list[dict]      # [{id, statement, status, evidence, reason}]
    evidence: dict              # {hypothesis_id: [evidence summaries]}
    round: int
    conclusion: dict            # {root_cause, confirmed_hypothesis_id, timeline, remediation}
    thought_stream: list[str]   # human-readable steps (GUI left panel)
    past_episodes: list[dict]   # [{text, score}] recalled from long-term memory at intake
    signature: str              # compact incident signature (retrieval key + stored key)


# --------------------------- helpers ---------------------------

def _ctx(state: InvestigationState) -> RequestContext:
    return RequestContext.from_dict(state["context"])


def _llm_json(system: str, user: str) -> Any:
    llm = get_llm()
    resp = llm.invoke([("system", system), ("user", user)])
    text = resp.content if hasattr(resp, "content") else str(resp)
    # tolerate fenced code blocks
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1:] if "\n" in text else text
        if text.endswith("json"):
            text = text[:-4]
    start = text.find("{")
    arr = text.find("[")
    if arr != -1 and (arr < start or start == -1):
        start = arr
    try:
        return json.loads(text[start:]) if start != -1 else json.loads(text)
    except Exception:
        return None


# --------------------------- nodes ---------------------------

def node_intake(state: InvestigationState) -> InvestigationState:
    ctx = _ctx(state)
    client = ToolsClient()
    seed = client.alarm_context(ctx)
    state["seed_signals"] = seed
    state["round"] = 0
    state["thought_stream"] = state.get("thought_stream", []) + [
        f"Intake: investigating alarm for tenant '{ctx.tenant_id}'. "
        f"Seed signals: {len(seed.get('recent_changes', []))} recent change(s), "
        f"{len(seed.get('error_logs', []))} error log(s), {len(seed.get('error_traces', []))} error trace(s)."
    ]

    # P2: retrieve-before-act. Recall past incident episodes for this tenant that match the
    # current incident signature, so hypothesis generation can reuse prior root causes/fixes.
    sig = incident_signature(state.get("alarm", ""), seed)
    state["signature"] = sig
    episodes = _MEMORY.retrieve_episodes(ctx, sig)
    state["past_episodes"] = episodes
    if episodes:
        state["thought_stream"].append(
            f"Memory: recalled {len(episodes)} past episode(s) for tenant '{ctx.tenant_id}' "
            f"(top score {episodes[0]['score']:.2f}). Using them to prime hypotheses."
        )
    elif _MEMORY.enabled:
        state["thought_stream"].append(
            f"Memory: no prior episodes matched for tenant '{ctx.tenant_id}'. Investigating fresh."
        )
    return state


_HYPO_SYS = """You are a senior SRE forming competing root-cause hypotheses for an incident.
Given the alarm and a seed snapshot of recent changes + error signals, propose 3-5 DISTINCT,
competing hypotheses for the root cause. Include at least one that is plausible-but-likely-wrong
(a red herring to test). For each hypothesis, state what evidence would CONFIRM it and what would
REJECT it. Respond as JSON: a list of objects
{"id":"h1","statement":"...","confirm_if":"...","reject_if":"..."}. No prose outside the JSON."""


def node_generate(state: InvestigationState) -> InvestigationState:
    ctx = _ctx(state)
    user = (f"ALARM: {state.get('alarm','(none)')}\nTENANT: {ctx.tenant_id}\n"
            f"SEED SNAPSHOT (JSON):\n{json.dumps(state.get('seed_signals', {}), indent=2)[:8000]}")

    # P2: prime generation with recalled past episodes (if any). These are PRIORS, not answers —
    # the agent must still confirm/reject with current evidence, not assume history repeats.
    episodes = state.get("past_episodes") or []
    if episodes:
        recalled = "\n\n".join(f"[past episode score={e['score']:.2f}]\n{e['text']}" for e in episodes[:3])
        user += (
            "\n\nPAST INCIDENT EPISODES for this tenant (similar signatures). Treat these as PRIORS "
            "to consider — include a hypothesis matching the most likely prior root cause, but STILL "
            "verify it against current evidence and do not assume it recurs:\n" + recalled[:6000]
        )
    hs = _llm_json(_HYPO_SYS, user) or []
    hypotheses = []
    for h in hs:
        hypotheses.append({
            "id": h.get("id") or f"h{len(hypotheses)+1}",
            "statement": h.get("statement", ""),
            "confirm_if": h.get("confirm_if", ""),
            "reject_if": h.get("reject_if", ""),
            "status": "candidate",
            "evidence": [],
            "reason": "",
        })
    state["hypotheses"] = hypotheses
    state["evidence"] = {}
    state["thought_stream"] = state.get("thought_stream", []) + [
        "Generated hypotheses: " + "; ".join(f"[{h['id']}] {h['statement']}" for h in hypotheses)
    ]
    return state


def _delegate_telemetry(question: str, ctx: RequestContext) -> str:
    if TELEMETRY_AGENT_URL:
        return A2AClient(TELEMETRY_AGENT_URL).send(question, ctx)
    from agents.telemetry.agent import handle as tele_handle  # local fallback
    return tele_handle(question, ctx)


def _delegate_change(question: str, ctx: RequestContext) -> str:
    if CHANGE_AGENT_URL:
        return A2AClient(CHANGE_AGENT_URL).send(question, ctx)
    from agents.change_correlation.agent import handle as chg_handle  # local fallback
    return chg_handle(question, ctx)


def node_gather(state: InvestigationState) -> InvestigationState:
    ctx = _ctx(state)
    # One targeted telemetry pass + one change-correlation pass per round, framed by the open hypotheses.
    open_h = [h for h in state["hypotheses"] if h["status"] in ("candidate", "investigating")]
    hyp_text = "; ".join(f"[{h['id']}] {h['statement']} (confirm_if: {h['confirm_if']})" for h in open_h)
    tele = _delegate_telemetry(f"Gather evidence to confirm or reject these hypotheses: {hyp_text}", ctx)
    chg = _delegate_change(f"What changed around the incident, relevant to: {hyp_text}", ctx)
    state["evidence"] = {"telemetry": tele, "changes": chg}
    for h in open_h:
        h["status"] = "investigating"
    state["thought_stream"] = state.get("thought_stream", []) + [
        "Gathered evidence (telemetry + change correlation) for open hypotheses."
    ]
    return state


_EVAL_SYS = """You are a GRUMPY, skeptical SRE incident critic. For each open hypothesis, decide
"confirmed", "rejected", or "needs_more" based STRICTLY on the evidence provided. Reject a
hypothesis if its signal is normal/flat or the evidence points elsewhere, and give the reason.
Confirm only if the evidence specifically supports it AND competing hypotheses are weaker. Prefer
rejecting on weak causality over confirming. Respond as JSON: a list of
{"id":"h1","verdict":"confirmed|rejected|needs_more","reason":"..."}. No prose outside JSON."""


def node_evaluate(state: InvestigationState) -> InvestigationState:
    hyps = state["hypotheses"]
    user = (f"OPEN HYPOTHESES:\n{json.dumps([{k:h[k] for k in ('id','statement','confirm_if','reject_if')} for h in hyps], indent=2)}\n\n"
            f"EVIDENCE:\nTELEMETRY:\n{state['evidence'].get('telemetry','')}\n\nCHANGES:\n{state['evidence'].get('changes','')}")
    verdicts = _llm_json(_EVAL_SYS, user) or []
    vmap = {v.get("id"): v for v in verdicts}
    for h in hyps:
        v = vmap.get(h["id"])
        if not v:
            continue
        verdict = v.get("verdict", "needs_more")
        h["reason"] = v.get("reason", "")
        if verdict == "confirmed":
            h["status"] = "confirmed"
        elif verdict == "rejected":
            h["status"] = "rejected"
        else:
            h["status"] = "investigating"
    state["round"] = state.get("round", 0) + 1
    confirmed = [h for h in hyps if h["status"] == "confirmed"]
    rejected = [h for h in hyps if h["status"] == "rejected"]
    state["thought_stream"] = state.get("thought_stream", []) + [
        f"Evaluation round {state['round']}: {len(confirmed)} confirmed, {len(rejected)} rejected, "
        f"{len(hyps) - len(confirmed) - len(rejected)} still open."
    ]
    return state


def _should_continue(state: InvestigationState) -> str:
    confirmed = [h for h in state["hypotheses"] if h["status"] == "confirmed"]
    open_h = [h for h in state["hypotheses"] if h["status"] in ("candidate", "investigating")]
    if confirmed or not open_h or state.get("round", 0) >= MAX_ROUNDS:
        return "conclude"
    return "gather"


_CONCLUDE_SYS = """You are an SRE writing the final root-cause conclusion. Given the hypotheses
with their final statuses, evidence, and reasons, produce JSON:
{"root_cause":"...","confirmed_hypothesis_id":"hN or null","timeline":["t1 ...","t2 ..."],
"remediation":"...","confidence":"high|medium|low"}. Base it only on confirmed evidence; if nothing
was confirmed, say so honestly in root_cause and set confidence low. No prose outside JSON."""


def node_conclude(state: InvestigationState) -> InvestigationState:
    ctx = _ctx(state)
    user = (f"ALARM: {state.get('alarm','')}\n"
            f"HYPOTHESES (final):\n{json.dumps(state['hypotheses'], indent=2)[:10000]}\n\n"
            f"EVIDENCE:\n{json.dumps(state.get('evidence', {}), indent=2)[:6000]}")
    concl = _llm_json(_CONCLUDE_SYS, user) or {
        "root_cause": "Inconclusive", "confirmed_hypothesis_id": None,
        "timeline": [], "remediation": "", "confidence": "low"}
    state["conclusion"] = concl
    state["thought_stream"] = state.get("thought_stream", []) + [
        f"Conclusion ({concl.get('confidence','?')} confidence): {concl.get('root_cause','')[:160]}"
    ]

    # P2: write-after-act. Persist this incident as an episode so future investigations for this
    # tenant can recall it. Only write reasonably-grounded conclusions (skip low-confidence noise).
    if _MEMORY.enabled and concl.get("confidence") in ("high", "medium"):
        episode_text = _format_episode(state, concl)
        rec_id = _MEMORY.write_episode(
            ctx,
            signature=state.get("signature", "") or state.get("alarm", ""),
            episode_text=episode_text,
        )
        if rec_id:
            state["thought_stream"].append(
                f"Memory: wrote incident episode to long-term memory for tenant '{ctx.tenant_id}'."
            )
    return state


def _format_episode(state: InvestigationState, concl: dict) -> str:
    """Render a compact, searchable episode body: what happened, what was confirmed/rejected, fix."""
    lines: list[str] = []
    lines.append(f"ALARM: {state.get('alarm','')}")
    confirmed = [h for h in state.get("hypotheses", []) if h.get("status") == "confirmed"]
    rejected = [h for h in state.get("hypotheses", []) if h.get("status") == "rejected"]
    if confirmed:
        lines.append("CONFIRMED:")
        for h in confirmed:
            lines.append(f"  - {h.get('statement','')} :: {h.get('reason','')[:300]}")
    if rejected:
        lines.append("REJECTED (red herrings to deprioritize next time):")
        for h in rejected:
            lines.append(f"  - {h.get('statement','')[:200]}")
    lines.append(f"ROOT CAUSE: {concl.get('root_cause','')}")
    if concl.get("remediation"):
        lines.append(f"REMEDIATION: {concl.get('remediation','')}")
    if concl.get("confidence"):
        lines.append(f"CONFIDENCE: {concl.get('confidence')}")
    return "\n".join(lines)


def build_graph():
    g = StateGraph(InvestigationState)
    g.add_node("intake", node_intake)
    g.add_node("generate", node_generate)
    g.add_node("gather", node_gather)
    g.add_node("evaluate", node_evaluate)
    g.add_node("conclude", node_conclude)
    g.set_entry_point("intake")
    g.add_edge("intake", "generate")
    g.add_edge("generate", "gather")
    g.add_edge("gather", "evaluate")
    g.add_conditional_edges("evaluate", _should_continue, {"gather": "gather", "conclude": "conclude"})
    g.add_edge("conclude", END)
    return g.compile()


_GRAPH = None


def run_investigation(alarm: str, ctx: RequestContext) -> InvestigationState:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    init: InvestigationState = {"context": ctx.to_dict(), "alarm": alarm}
    return _GRAPH.invoke(init)
