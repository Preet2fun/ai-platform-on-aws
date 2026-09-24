"""OpenTelemetry GenAI tracing helpers (FI-6).

Emits **content-carrying spans** per query so each conversation trace records the user
question, the exact retrieved chunks (id + text + score), and the model answer — the data an
online eval needs to score faithfulness against *real* retrieved context (closes the online
half of FI-4). The spans follow the OpenTelemetry GenAI semantic conventions where they exist,
with a few custom `cshub.*` attributes for the retrieval detail.

Design goals:
- **Non-fatal / optional.** If the OTel SDK isn't present (e.g. the ADOT layer isn't attached,
  or in local unit tests), every function here degrades to a no-op and the pipeline runs
  unchanged. Tracing must never break a user's answer.
- **Runtime provided by the ADOT layer.** In Lambda, the ADOT layer + `AWS_LAMBDA_EXEC_WRAPPER
  =/opt/otel-instrument` set up the tracer provider and the X-Ray exporter. We only *use* the
  tracer here; we do not configure exporters in code.
- **Bounded payloads.** Question/answer/chunk text are truncated so spans stay well under
  backend attribute-size limits (X-Ray caps segment/annotation sizes).

Enable/disable without redeploying code via env var `ENABLE_GENAI_TRACING` (default "true").
"""
from __future__ import annotations

import contextlib
import os
from typing import Any, Iterator

# GenAI semantic-convention attribute keys (subset) + cshub custom keys.
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_OP = "gen_ai.operation.name"
GEN_AI_REQ_MODEL = "gen_ai.request.model"
GEN_AI_PROMPT = "gen_ai.prompt"
GEN_AI_COMPLETION = "gen_ai.completion"

# Truncation limits (chars) — keep spans small; full answer already went to the user.
_Q_MAX = 1000
_ANS_MAX = 4000
_CHUNK_MAX = 1500          # per retrieved chunk
_MAX_CHUNKS_ON_SPAN = 8    # cap how many chunks we attach

_TRACING_ON = os.getenv("ENABLE_GENAI_TRACING", "true").strip().lower() == "true"

# Try to bind a tracer. If OTel isn't importable, everything below no-ops.
try:  # pragma: no cover - import availability depends on runtime layer
    from opentelemetry import trace as _otel_trace

    _tracer = _otel_trace.get_tracer("cshub.query")
    _OTEL = True
except Exception:  # noqa: BLE001
    _tracer = None
    _OTEL = False


def enabled() -> bool:
    """True only when tracing is switched on AND the OTel SDK is available."""
    return _TRACING_ON and _OTEL


@contextlib.contextmanager
def span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
    """Start a span (context manager). No-op if tracing is unavailable.

    Yields the span object (or None). Records exceptions on the span but re-raises them, so
    tracing observes failures without changing control flow.
    """
    if not enabled():
        yield None
        return
    with _tracer.start_as_current_span(name) as sp:  # type: ignore[union-attr]
        try:
            if attributes:
                for k, v in attributes.items():
                    if v is not None:
                        sp.set_attribute(k, v)
            yield sp
        except Exception as exc:  # noqa: BLE001
            with contextlib.suppress(Exception):
                sp.record_exception(exc)
            raise


def set_attr(sp: Any, key: str, value: Any) -> None:
    """Safe single-attribute setter (no-op if span is None or set fails)."""
    if sp is None or value is None:
        return
    with contextlib.suppress(Exception):
        sp.set_attribute(key, value)


def record_question(sp: Any, request_id: str, question: str, model_id: str) -> None:
    """Attach identity + the user question to the current span."""
    if sp is None:
        return
    set_attr(sp, "cshub.request_id", request_id)
    set_attr(sp, GEN_AI_SYSTEM, "aws.bedrock")
    set_attr(sp, GEN_AI_OP, "rag.query")
    set_attr(sp, GEN_AI_REQ_MODEL, model_id)
    set_attr(sp, GEN_AI_PROMPT, (question or "")[:_Q_MAX])
    set_attr(sp, "cshub.question", (question or "")[:_Q_MAX])


def record_retrieval(sp: Any, hits: list[Any]) -> None:
    """Attach the retrieved chunks (id + score + text) so eval can ground on real context.

    `hits` are retrieval.Hit objects (chunk_id, doc_id, text, score, metadata). We attach a
    bounded, structured view: per-chunk attributes plus a single joined `cshub.retrieved_context`
    blob that the scorer can read directly.
    """
    if sp is None:
        return
    set_attr(sp, "cshub.retrieved_count", len(hits))
    blob_parts: list[str] = []
    for i, h in enumerate(hits[:_MAX_CHUNKS_ON_SPAN]):
        cid = getattr(h, "chunk_id", "")
        did = getattr(h, "doc_id", "")
        score = getattr(h, "score", None)
        text = (getattr(h, "text", "") or "")[:_CHUNK_MAX]
        set_attr(sp, f"cshub.chunk.{i}.id", str(cid))
        set_attr(sp, f"cshub.chunk.{i}.doc_id", str(did))
        if isinstance(score, (int, float)):
            set_attr(sp, f"cshub.chunk.{i}.score", float(score))
        set_attr(sp, f"cshub.chunk.{i}.text", text)
        blob_parts.append(f"[{i + 1}] ({did}) {text}")
    # one concatenated context blob (bounded) — convenient single field for the scorer
    joined = "\n\n---\n\n".join(blob_parts)
    set_attr(sp, "cshub.retrieved_context", joined[:12000])


def record_answer(sp: Any, answer: str, *, blocked: str | None = None,
                  is_idk: bool | None = None) -> None:
    """Attach the model answer + outcome flags to the current span."""
    if sp is None:
        return
    set_attr(sp, GEN_AI_COMPLETION, (answer or "")[:_ANS_MAX])
    set_attr(sp, "cshub.answer", (answer or "")[:_ANS_MAX])
    if blocked is not None:
        set_attr(sp, "cshub.blocked", str(blocked))
    if is_idk is not None:
        set_attr(sp, "cshub.is_idk", bool(is_idk))
