"""Trace attribution: pull the P6 spans for an eval run and summarize per-step detail.

Why: a score tells you WHAT was wrong; the trace tells you WHERE. For each investigation we pull
the spans (joined by our session_id) and extract step-level timings, token usage, the A2A
delegations, memory recall, and any span errors. Attached to the eval score card so a low
root-cause or hypothesis score points at the exact LLM step / round / delegation that produced it.

Spans live in the per-agent CloudWatch log groups under the `spans` stream (P6,
UNIFIED_TRACES_DESTINATION_ENABLED). We read the investigator's group (the RCA engine) plus the
supervisor's for the top-level timing.
"""
from __future__ import annotations

import json
import os
import time

import boto3

REGION = os.getenv("AWS_REGION", "us-east-1")

RUNTIME_LOG_GROUPS = {
    "supervisor": "/aws/bedrock-agentcore/runtimes/sre_agentic_dev_supervisor-dSf6vD9ngf-DEFAULT",
    "investigator": "/aws/bedrock-agentcore/runtimes/sre_agentic_dev_investigator-31IK8f71Bt-DEFAULT",
    "telemetry": "/aws/bedrock-agentcore/runtimes/sre_agentic_dev_telemetry-ALtPd37P4v-DEFAULT",
    "change": "/aws/bedrock-agentcore/runtimes/sre_agentic_dev_change-wHsGWfFSA4-DEFAULT",
}

_NANO = 1_000_000_000


def _logs():
    return boto3.client("logs", region_name=REGION)


def _read_spans(log_group: str, since_seconds: int = 1800, limit: int = 300) -> list[dict]:
    """Read recent span JSON docs from a runtime's `spans` stream."""
    cl = _logs()
    try:
        resp = cl.get_log_events(
            logGroupName=log_group, logStreamName="spans",
            startTime=(int(time.time()) - since_seconds) * 1000, limit=limit, startFromHead=False,
        )
    except Exception:  # noqa: BLE001 - stream may not exist yet
        return []
    out = []
    for e in resp.get("events", []):
        msg = e.get("message", "")
        try:
            out.append(json.loads(msg))
        except Exception:  # noqa: BLE001
            continue
    return out


def _dur_ms(span: dict) -> float | None:
    d = span.get("durationNano")
    if d is None and span.get("startTimeUnixNano") and span.get("endTimeUnixNano"):
        d = span["endTimeUnixNano"] - span["startTimeUnixNano"]
    return round(d / 1_000_000, 1) if d else None


def _attr(span: dict, key: str):
    return (span.get("attributes") or {}).get(key)


def attribution_for_session(session_id: str, since_seconds: int = 1800) -> dict:
    """Summarize the trace for a run identified by our session_id.

    Returns step timings, token usage per LLM step, delegations, memory recall, errors, and the
    trace id — enough to point a failing eval at the exact span.
    """
    inv = _read_spans(RUNTIME_LOG_GROUPS["investigator"], since_seconds)
    # keep only spans belonging to this session (our custom spans carry sre.session_id;
    # ADOT auto spans carry session.id = our runtime session, which differs — so match on
    # sre.session_id for our spans and fall back to the shared traceId once we find the root)
    mine = [s for s in inv if _attr(s, "sre.session_id") == session_id]
    trace_id = None
    root = next((s for s in mine if s.get("name") == "investigation"), None)
    if root:
        trace_id = root.get("traceId")
    # widen to everything in the same trace (captures auto-instrumented chat/tool spans too)
    if trace_id:
        mine = [s for s in inv if s.get("traceId") == trace_id] or mine

    steps = []
    tokens_in = tokens_out = 0
    for s in mine:
        name = s.get("name", "")
        kind = _attr(s, "sre.step_kind") or ""
        rec = {"span": name, "kind": kind, "duration_ms": _dur_ms(s)}
        status = (s.get("status") or {}).get("code")
        if status == "ERROR":
            rec["error"] = (s.get("status") or {}).get("message", "")[:300]
        ti = _attr(s, "gen_ai.usage.input_tokens")
        to = _attr(s, "gen_ai.usage.output_tokens")
        if ti:
            rec["input_tokens"] = ti
            tokens_in += int(ti)
        if to:
            rec["output_tokens"] = to
            tokens_out += int(to)
        if name.startswith(("llm.", "a2a.", "investigation")):
            steps.append(rec)

    delegations = [s.get("name") for s in mine if s.get("name", "").startswith("a2a.delegate")]
    errors = [{"span": s.get("name"), "msg": (s.get("status") or {}).get("message", "")[:200]}
              for s in mine if (s.get("status") or {}).get("code") == "ERROR"]

    return {
        "trace_id": trace_id,
        "found_spans": len(mine),
        "steps": steps,
        "delegation_count": len(delegations),
        "tokens": {"input": tokens_in, "output": tokens_out, "total": tokens_in + tokens_out},
        "errors": errors,
        "root_total_ms": _dur_ms(root) if root else None,
    }
