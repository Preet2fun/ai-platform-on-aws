"""Reference-based scorer: grade an agent investigation against a scenario's hidden manifest.

Two kinds of checks, kept separate so you can trust them differently:
  - DETERMINISTIC (no LLM): did the agent confirm a hypothesis matching the true cause and reject
    the manifest's red herrings? Scored by matching the agent's confirmed/rejected hypotheses to
    the manifest's expected verdicts via an LLM-judged semantic alignment of statements (the ids
    differ between agent and manifest, so we align by meaning once, then the verdict check is
    mechanical).
  - LLM-AS-JUDGE (Claude): root-cause correctness and remediation soundness — semantic matches
    scored 0..1 with a written rationale you can audit.

Every metric returns {score, rationale, ...} so a low score points at WHY, and the judge's
reasoning is always surfaced (never a bare number).
"""
from __future__ import annotations

import json
from typing import Any

from agents.common.llm import get_llm


def _judge(system: str, user: str) -> dict:
    """Call Claude as judge; expect a single JSON object with at least {score, rationale}."""
    llm = get_llm()
    resp = llm.invoke([("system", system), ("user", user)])
    text = resp.content if hasattr(resp, "content") else str(resp)
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1:] if "\n" in text else text
    s = text.find("{")
    try:
        return json.loads(text[s:]) if s != -1 else {}
    except Exception:
        return {"score": 0.0, "rationale": f"judge returned non-JSON: {text[:200]}"}


# --------------------------- deterministic-ish: hypotheses ---------------------------

_ALIGN_SYS = """You align an AGENT's hypotheses to a GROUND-TRUTH hypothesis list by MEANING (ids
differ). For each ground-truth hypothesis, find the agent hypothesis that expresses the same claim
(or null if none). Respond JSON: {"alignment":[{"gt_id":"h1","agent_id":"hN or null",
"agent_status":"confirmed|rejected|investigating|none"}]}. No prose outside JSON."""


def score_hypotheses(agent: dict, manifest: dict) -> dict:
    """Did the agent confirm the true cause and reject the red herrings? Returns per-hypothesis
    correctness plus confirm_accuracy and red_herring_rejection sub-scores."""
    gt = manifest.get("expected_hypotheses", []) or []
    agent_h = [{"id": h.get("id"), "statement": h.get("statement", ""), "status": h.get("status", "")}
               for h in agent.get("hypotheses", [])]
    user = (f"GROUND-TRUTH HYPOTHESES:\n{json.dumps([{ 'id':g['id'],'statement':g['statement'] } for g in gt], indent=2)}\n\n"
            f"AGENT HYPOTHESES (with status):\n{json.dumps(agent_h, indent=2)}")
    alignment = (_judge(_ALIGN_SYS, user) or {}).get("alignment", [])
    amap = {a.get("gt_id"): a for a in alignment}

    results = []
    confirm_hits = confirm_total = 0
    reject_hits = reject_total = 0
    for g in gt:
        want = g.get("verdict")  # "confirm" | "reject"
        a = amap.get(g["id"], {})
        got_status = a.get("agent_status", "none")
        got = "confirm" if got_status == "confirmed" else ("reject" if got_status == "rejected" else "other")
        correct = (want == got)
        results.append({"gt_id": g["id"], "expected": want, "agent_status": got_status,
                        "correct": correct, "statement": g["statement"][:120]})
        if want == "confirm":
            confirm_total += 1
            confirm_hits += int(correct)
        elif want == "reject":
            reject_total += 1
            reject_hits += int(correct)

    return {
        "per_hypothesis": results,
        "confirm_accuracy": (confirm_hits / confirm_total) if confirm_total else None,
        "red_herring_rejection": (reject_hits / reject_total) if reject_total else None,
        "overall": (sum(r["correct"] for r in results) / len(results)) if results else None,
    }


# --------------------------- llm-as-judge: root cause + remediation ---------------------------

_RC_SYS = """You are a strict SRE evaluation judge. Compare the AGENT's root-cause conclusion to the
GROUND-TRUTH root cause. Score how well the agent identified the TRUE root cause on a 0.0-1.0 scale:
1.0 = correctly identifies the same root cause and mechanism; 0.5 = partially correct (right area,
wrong mechanism, or missing the trigger); 0.0 = wrong or inconclusive. Be strict about mechanism and
the true trigger, not just surface symptoms. Respond JSON:
{"score":0.0-1.0,"rationale":"...","identified_true_cause":true|false}. No prose outside JSON."""

_REM_SYS = """You are an SRE evaluation judge. Compare the AGENT's remediation to the GROUND-TRUTH
remediation. Score 0.0-1.0 how sound/aligned the agent's fix is (addresses the true cause, safe,
no obviously harmful step). Respond JSON: {"score":0.0-1.0,"rationale":"..."}. No prose outside JSON."""


def score_root_cause(agent: dict, manifest: dict) -> dict:
    concl = agent.get("conclusion", {}) or {}
    gt = manifest.get("ground_truth", {}) or {}
    user = (f"GROUND-TRUTH ROOT CAUSE:\n{gt.get('root_cause','')}\n\n"
            f"GROUND-TRUTH CAUSAL CHAIN:\n{json.dumps(gt.get('causal_chain', []), indent=2)}\n\n"
            f"AGENT ROOT CAUSE:\n{concl.get('root_cause','(none)')}\n\n"
            f"AGENT CONFIDENCE: {concl.get('confidence','?')}")
    return _judge(_RC_SYS, user)


def score_remediation(agent: dict, manifest: dict) -> dict:
    concl = agent.get("conclusion", {}) or {}
    gt = manifest.get("ground_truth", {}) or {}
    agent_rem = concl.get("remediation", "") or (agent.get("remediation", {}) or {}).get("proposal", "")
    user = (f"GROUND-TRUTH REMEDIATION:\n{gt.get('remediation','')}\n\n"
            f"AGENT REMEDIATION:\n{agent_rem or '(none)'}")
    return _judge(_REM_SYS, user)


# --------------------------- aggregate ---------------------------

def score_run(agent: dict, manifest: dict) -> dict:
    """Full score card for one investigation vs. its manifest."""
    concl = agent.get("conclusion", {}) or {}
    hyp = score_hypotheses(agent, manifest)
    rc = score_root_cause(agent, manifest)
    rem = score_remediation(agent, manifest)

    # confidence calibration: high confidence should coincide with a correct root cause
    conf = (concl.get("confidence") or "").lower()
    rc_correct = bool(rc.get("identified_true_cause"))
    calibrated = (conf == "high" and rc_correct) or (conf in ("low", "medium") and not rc_correct) \
        or (conf == "high" and rc.get("score", 0) >= 0.8)

    return {
        "scenario_id": manifest.get("scenario_id"),
        "tenant_id": manifest.get("tenant_id"),
        "root_cause": {"score": rc.get("score"), "identified_true_cause": rc.get("identified_true_cause"),
                       "rationale": rc.get("rationale")},
        "hypotheses": hyp,
        "remediation": {"score": rem.get("score"), "rationale": rem.get("rationale")},
        "confidence": conf,
        "confidence_calibrated": calibrated,
        "agent_confirmed_hypothesis_id": concl.get("confirmed_hypothesis_id"),
    }
