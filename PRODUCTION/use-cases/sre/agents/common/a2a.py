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
        ctx = RequestContext.from_dict(params.get("metadata") or {})

        try:
            ctx.require_tenant()
        except ValueError as e:
            return JSONResponse(_rpc_error(rpc_id, -32052, f"Validation error - {e}"))

        try:
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

class A2AClient:
    """Call a specialist A2A agent by base URL, carrying tenant/scenario context."""

    def __init__(self, base_url: str, timeout: float = 120.0, bearer_token: str | None = None):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.bearer_token = bearer_token

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json",
             "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": str(uuid.uuid4())}
        if self.bearer_token:
            h["Authorization"] = f"Bearer {self.bearer_token}"
        return h

    def send(self, text: str, context: RequestContext) -> str:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": text}],
                    "messageId": str(uuid.uuid4()),
                },
                "metadata": context.to_dict(),
            },
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(self.base_url, json=payload, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
        if "error" in data:
            raise RuntimeError(f"A2A error from {self.base_url}: {data['error']}")
        artifacts = (data.get("result") or {}).get("artifacts") or []
        texts = []
        for a in artifacts:
            for p in a.get("parts", []):
                if p.get("kind", "text") == "text":
                    texts.append(p.get("text", ""))
        return "\n".join(t for t in texts if t)

    def agent_card(self) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(self.base_url + ".well-known/agent-card.json", headers=self._headers())
            resp.raise_for_status()
            return resp.json()
