"""Telemetry specialist (A2A) — gathers metrics/logs/traces evidence for a hypothesis.

Role: given a focused question from the supervisor/investigator (e.g. "is product-db connection
pool saturated?"), craft precise tool queries against the observability backends, and return a
concise, cited evidence summary. Read-only. LangGraph single-node agent: the LLM is given the
tenant-scoped tool outputs and asked to summarize the relevant signal (and explicitly say when a
signal is normal — important so the investigator can REJECT hypotheses).
"""
from __future__ import annotations

import json

from agents.common.context import RequestContext
from agents.common.llm import get_llm
from agents.common.tools_client import ToolsClient

_SYSTEM = """You are an SRE telemetry analyst. You are given a focused QUESTION and the
tenant-scoped observability signals (metrics, logs, traces) relevant to it. Summarize ONLY what
the evidence shows, concisely, with specific numbers and timestamps. Crucially:
- If a signal is anomalous, state the anomaly and when it started.
- If a signal is NORMAL/healthy, say so explicitly (this lets the investigator reject hypotheses).
- Never speculate beyond the data. Cite the signal (service + metric/log) for each claim.
Return 3-8 short bullet points."""


def _gather(client: ToolsClient, ctx: RequestContext) -> dict:
    return {
        "metrics": client.metrics(ctx),
        "error_logs": client.logs(ctx, level="ERROR"),
        "warning_logs": client.logs(ctx, level="WARNING"),
        "error_traces": client.traces(ctx, errors_only=True),
    }


def handle(question: str, ctx: RequestContext, client: ToolsClient | None = None) -> str:
    client = client or ToolsClient()
    evidence = _gather(client, ctx)
    llm = get_llm()
    prompt = (
        f"QUESTION: {question}\n\n"
        f"TENANT: {ctx.tenant_id}\n"
        f"OBSERVABILITY SIGNALS (JSON):\n{json.dumps(evidence, indent=2)[:12000]}\n\n"
        "Summarize the evidence per the instructions."
    )
    resp = llm.invoke([("system", _SYSTEM), ("user", prompt)])
    return resp.content if hasattr(resp, "content") else str(resp)
