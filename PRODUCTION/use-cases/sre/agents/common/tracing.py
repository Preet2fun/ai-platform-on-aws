"""Custom OpenTelemetry tracing for the SRE agents (P6, full/production-grade spans).

Purpose
-------
Produce ONE rich, end-to-end trace per investigation that is detailed enough to drive evals
(P7): every LangGraph step, every A2A delegation, every tool call, and every LLM call appears
as a span carrying tenant/incident/session ids, timings, and — where enabled — the LLM
prompts/responses and tool inputs/outputs (via AWS_GENAI_CONTENT_EXTRACTION_OPT_OUT=true).

Design
------
- Thin wrapper over the OTel API. ADOT (via `opentelemetry-instrument`) wires the SDK + exporter
  at runtime; this module only creates spans on the active tracer. If no SDK is configured (local
  dev / tests), OTel's default no-op tracer makes every call a cheap no-op — zero behavior change.
- Span/attribute names follow the GenAI semantic conventions (`gen_ai.*`) where applicable so the
  CloudWatch GenAI Observability page and span->eval converters render them correctly.
- Cross-process trace continuity (supervisor -> investigator -> specialists) is handled by
  injecting/extracting W3C traceparent into the A2A JSON-RPC `metadata` (see a2a.py), so the whole
  chain is a single trace rather than one disjoint trace per runtime.
"""
from __future__ import annotations

import functools
from contextlib import contextmanager
from typing import Any

try:
    from opentelemetry import trace
    from opentelemetry.propagate import extract, inject
    _tracer = trace.get_tracer("sre.agents")
except Exception:  # noqa: BLE001 - OTel always importable once ADOT is a dep; guard anyway
    trace = None
    _tracer = None

    def inject(carrier):  # type: ignore
        return None

    def extract(carrier):  # type: ignore
        return None


def _set(span, key: str, value: Any) -> None:
    if value is None:
        return
    try:
        if isinstance(value, (str, bool, int, float)):
            span.set_attribute(key, value)
        else:
            import json
            span.set_attribute(key, json.dumps(value, default=str)[:8000])
    except Exception:  # noqa: BLE001
        pass


def ctx_attrs(context) -> dict[str, Any]:
    """Standard tenant/incident/session attributes stamped on every span for filtering in evals."""
    if context is None:
        return {}
    return {
        "sre.tenant_id": getattr(context, "tenant_id", "") or "",
        "sre.scenario_id": getattr(context, "scenario_id", "") or "",
        "sre.session_id": getattr(context, "session_id", "") or "",
        "sre.incident_id": getattr(context, "incident_id", "") or "",
    }


@contextmanager
def span(name: str, *, context=None, kind: str = "internal", attrs: dict[str, Any] | None = None):
    """Start a span named `name`. No-op if OTel SDK isn't configured.

    `kind` is a free-form label stored as sre.step_kind (node|delegation|tool|llm|...).
    """
    if _tracer is None:
        yield None
        return
    # record_exception=True / set_status_on_exception=True let OTel handle error recording itself,
    # so we must NOT also try/except+reraise around the yield (that double-handling triggers
    # "generator didn't stop after throw()"). Just yield; OTel marks the span on exception.
    with _tracer.start_as_current_span(
        name, record_exception=True, set_status_on_exception=True
    ) as sp:
        _set(sp, "sre.step_kind", kind)
        for k, v in (ctx_attrs(context)).items():
            _set(sp, k, v)
        for k, v in (attrs or {}).items():
            _set(sp, k, v)
        yield sp


def record_llm(sp, *, model: str, system: str, user: str, output: str,
               input_tokens: int | None = None, output_tokens: int | None = None) -> None:
    """Attach GenAI-convention LLM call detail to the current span (for eval error analysis)."""
    if sp is None:
        return
    _set(sp, "gen_ai.system", "aws.bedrock")
    _set(sp, "gen_ai.request.model", model)
    _set(sp, "gen_ai.prompt.0.role", "system")
    _set(sp, "gen_ai.prompt.0.content", system)
    _set(sp, "gen_ai.prompt.1.role", "user")
    _set(sp, "gen_ai.prompt.1.content", user)
    _set(sp, "gen_ai.completion.0.role", "assistant")
    _set(sp, "gen_ai.completion.0.content", output)
    _set(sp, "gen_ai.usage.input_tokens", input_tokens)
    _set(sp, "gen_ai.usage.output_tokens", output_tokens)


def record_tool(sp, *, tool: str, args: Any, result: Any) -> None:
    """Attach tool input/output to the current span."""
    if sp is None:
        return
    _set(sp, "gen_ai.tool.name", tool)
    _set(sp, "sre.tool.input", args)
    _set(sp, "sre.tool.output", result)


def inject_trace_context(carrier: dict[str, Any]) -> dict[str, Any]:
    """Inject the active trace context (W3C traceparent) into a dict carrier for cross-process A2A."""
    carrier = dict(carrier or {})
    try:
        inject(carrier)
    except Exception:  # noqa: BLE001
        pass
    return carrier


@contextmanager
def continue_trace(carrier: dict[str, Any]):
    """Activate a trace context extracted from an inbound carrier (A2A metadata). No-op without OTel."""
    if _tracer is None or not carrier:
        yield
        return
    try:
        from opentelemetry.context import attach, detach
        token = attach(extract(carrier))
        try:
            yield
        finally:
            detach(token)
    except Exception:  # noqa: BLE001
        yield
