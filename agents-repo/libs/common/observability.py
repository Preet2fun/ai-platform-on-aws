"""Logging + OpenTelemetry setup.

Runtimes ship logs to CloudWatch and traces to X-Ray / Application Signals
(IAM grants xray:PutTraceSegments etc.). When deployed with
`opentelemetry-instrument` as the entrypoint wrapper, spans are exported
automatically; this module just standardizes logging and a tracer handle.
"""

from __future__ import annotations

import logging

from common.config import get_settings


def setup_logging() -> logging.Logger:
    s = get_settings()
    logging.basicConfig(
        level=getattr(logging, s.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return logging.getLogger("msp-agents")


def get_tracer(name: str):
    """Return an OTEL tracer if instrumentation is available, else a no-op."""
    try:
        from opentelemetry import trace  # provided by aws-opentelemetry-distro

        return trace.get_tracer(name)
    except Exception:  # pragma: no cover - optional dependency at runtime
        class _NoopTracer:
            def start_as_current_span(self, *_a, **_k):
                from contextlib import nullcontext

                return nullcontext()

        return _NoopTracer()
