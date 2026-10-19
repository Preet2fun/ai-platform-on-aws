"""Minimal A2A (Agent-to-Agent) adapter for the AgentCore container contract.

Implements the A2A wire contract directly (no Strands dependency), per the AgentCore protocol
reference:
  - Port 9000, primary endpoint POST / (root), JSON-RPC 2.0
  - Agent Card at GET /.well-known/agent-card.json
  - GET /ping health check
  - JSON-RPC errors returned with HTTP 200

`A2AAgentServer` wraps any callable `handler(message_text, context) -> result_text` (our
specialists wrap a LangGraph graph) and serves it as an A2A runtime. `A2AClient` lets the
supervisor delegate to a specialist by URL. Tenant/scenario context rides in JSON-RPC
`params.metadata` so isolation is preserved across the hop.
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Callable

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .context import RequestContext
from . import tracing

A2A_PORT = int(os.getenv("A2A_PORT", "9000"))


# --------------------------- server ---------------------------

def build_a2a_app(
    *,
    name: str,
    description: str,
    skills: list[dict[str, Any]],
    handler: Callable[[str, RequestContext], str],
    version: str = "0.1.0",
) -> FastAPI:
    """Build a FastAPI app implementing the AgentCore A2A contract around `handler`.

    `handler(message_text, context)` returns the agent's response text. It runs synchronously
    here; FastAPI serves it. Streaming is not required for inter-agent delegation.
    """
    app = FastAPI(title=name, version=version)

    def _agent_card(base_url: str) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "version": version,
            "url": base_url,
            "protocolVersion": "0.3.0",
            "preferredTransport": "JSONRPC",
            "capabilities": {"streaming": False},
            "defaultInputModes": ["text"],
            "defaultOutputModes": ["text"],
            "skills": skills,
        }

    @app.get("/ping")
    def ping():
        return {"status": "Healthy"}

    @app.get("/.well-known/agent-card.json")
    def agent_card(request: Request):
        base = os.getenv("AGENTCORE_RUNTIME_URL", str(request.base_url))
        return _agent_card(base)

    @app.post("/")
    async def rpc(request: Request):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(_rpc_error(None, -32700, "Parse error"))
        rpc_id = body.get("id")
        method = body.get("method")
        params = body.get("params") or {}

        if method not in ("message/send", "message/stream"):
            return JSONResponse(_rpc_error(rpc_id, -32601, f"Method not found: {method}"))

        msg = params.get("message") or {}
        parts = msg.get("parts") or []
        text = " ".join(p.get("text", "") for p in parts if p.get("kind", "text") == "text").strip()
        metadata = params.get("metadata") or {}
        ctx = RequestContext.from_dict(metadata)
        otel_carrier = metadata.get("_otel") or {}  # W3C traceparent injected by the caller

        try:
            ctx.require_tenant()
        except ValueError as e:
            return JSONResponse(_rpc_error(rpc_id, -32052, f"Validation error - {e}"))

        # P6: continue the caller's trace so supervisor->investigator->specialist is ONE trace.
        try:
            with tracing.continue_trace(otel_carrier):
                with tracing.span(f"a2a.handle.{name}", context=ctx, kind="a2a_server"):
                    result_text = handler(text, ctx)
        except Exception as e:  # noqa: BLE001 - surface as JSON-RPC error (HTTP 200)
            return JSONResponse(_rpc_error(rpc_id, -32055, f"Runtime client error - {e}"))

        return JSONResponse({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "artifacts": [{
                    "artifactId": str(uuid.uuid4()),
                    "name": "agent_response",
                    "parts": [{"kind": "text", "text": result_text}],
                }]
            },
        })

    return app


def _rpc_error(rpc_id: Any, code: int, message: str) -> dict[str, Any]:
    # A2A: JSON-RPC errors carry HTTP 200 (handled by caller returning this body with default 200)
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


# --------------------------- client ---------------------------

def _is_agentcore_arn(target: str) -> bool:
    """A target is an AgentCore Runtime ARN (cloud transport) vs an http(s) URL (local transport)."""
    return target.startswith("arn:aws:bedrock-agentcore:")


def _build_jsonrpc_payload(text: str, context: RequestContext) -> dict[str, Any]:
    """The A2A JSON-RPC `message/send` envelope. Identical on both transports — only the
    transport (raw HTTP vs AgentCore InvokeAgentRuntime) differs."""
    metadata = context.to_dict()
    # P6: carry the active W3C trace context so the callee continues the SAME trace.
    metadata["_otel"] = tracing.inject_trace_context({})
    return {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
                "messageId": str(uuid.uuid4()),
            },
            "metadata": metadata,
        },
    }


def _parts_text(parts: list[dict[str, Any]]) -> list[str]:
    return [p.get("text", "") for p in parts if p.get("kind", "text") == "text"]


def _extract_artifact_text(data: dict[str, Any], source: str) -> str:
    """Pull the response text out of an A2A JSON-RPC result (shared by both transports).

    Tolerates both result shapes the A2A spec allows:
      - result.artifacts[].parts[]  (what our own build_a2a_app server returns)
      - result.message.parts[]      (plain message result)
      - result.parts[]              (bare message)
    """
    if "error" in data:
        raise RuntimeError(f"A2A error from {source}: {data['error']}")
    result = data.get("result") or {}
    texts: list[str] = []
    for a in result.get("artifacts") or []:
        texts.extend(_parts_text(a.get("parts", [])))
    if not texts:
        msg = result.get("message") or (result if result.get("parts") else {})
        texts.extend(_parts_text(msg.get("parts", [])))
    return "\n".join(t for t in texts if t)


class A2AClient:
    """Call a specialist A2A agent, carrying tenant/scenario context.

    `target` may be either:
      - an http(s) base URL  -> raw httpx POST to the A2A root (local / single-host dev)
      - an AgentCore Runtime ARN (``arn:aws:bedrock-agentcore:...:runtime/...``)
        -> boto3 ``invoke_agent_runtime`` signed with SigV4 (cloud, same-account
           service-to-service). The caller's runtime IAM role must hold
           ``bedrock-agentcore:InvokeAgentRuntime`` on the target.

    The transport is chosen by inspecting `target`, so the graph code is identical in both
    modes — only the env var value changes (URL locally, ARN in the cloud).
    """

    def __init__(self, target: str, timeout: float = 120.0, bearer_token: str | None = None,
                 qualifier: str = "DEFAULT"):
        self.target = target
        self.is_arn = _is_agentcore_arn(target)
        self.timeout = timeout
        self.bearer_token = bearer_token
        self.qualifier = qualifier
        if not self.is_arn:
            self.base_url = target.rstrip("/") + "/"

    # ---- local (http) transport ----

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json",
             "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": str(uuid.uuid4())}
        if self.bearer_token:
            h["Authorization"] = f"Bearer {self.bearer_token}"
        return h

    def _send_http(self, payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(self.base_url, json=payload, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    # ---- cloud (AgentCore SigV4) transport ----

    def _send_agentcore(self, payload: dict[str, Any]) -> dict[str, Any]:
        import json as _json

        import boto3  # imported lazily so local/test runs don't require AWS creds
        from botocore.config import Config as _BotoConfig

        # Nested A2A chains (investigator -> specialists -> tools, each an LLM round) can run for
        # minutes. boto3's default 60s read timeout is far too short, so set generous timeouts and
        # disable retries (the downstream work is not idempotent to blind retries).
        _cfg = _BotoConfig(read_timeout=max(self.timeout, 300), connect_timeout=10,
                           retries={"max_attempts": 0})
        client = boto3.client("bedrock-agentcore", config=_cfg)
        resp = client.invoke_agent_runtime(
            agentRuntimeArn=self.target,
            qualifier=self.qualifier,
            runtimeSessionId=_runtime_session_id(),
            payload=_json.dumps(payload).encode("utf-8"),
        )
        content_type = resp.get("contentType", "") or ""
        body = resp.get("response")
        if "text/event-stream" in content_type:
            chunks = []
            for line in body.iter_lines(chunk_size=10):
                if not line:
                    continue
                line = line.decode("utf-8") if isinstance(line, bytes) else line
                if line.startswith("data: "):
                    chunks.append(line[6:])
            raw = "".join(chunks)
        else:
            parts = []
            for chunk in body:
                parts.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
            raw = "".join(parts)
        try:
            return _json.loads(raw)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"A2A error from {self.target}: non-JSON response: {raw[:300]}") from e

    def send(self, text: str, context: RequestContext) -> str:
        payload = _build_jsonrpc_payload(text, context)
        data = self._send_agentcore(payload) if self.is_arn else self._send_http(payload)
        return _extract_artifact_text(data, self.target)

    def agent_card(self) -> dict[str, Any]:
        if self.is_arn:
            raise RuntimeError("agent_card() is only available over the http transport, not AgentCore ARN")
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(self.base_url + ".well-known/agent-card.json", headers=self._headers())
            resp.raise_for_status()
            return resp.json()


def _runtime_session_id() -> str:
    """AgentCore requires a session id of 33-256 chars; a bare uuid4 is only 36 but can dip below
    the floor with some formats, so we prefix to be safely in-range."""
    return f"sre-a2a-{uuid.uuid4().hex}{uuid.uuid4().hex}"
