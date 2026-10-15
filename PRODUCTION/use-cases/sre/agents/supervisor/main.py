"""Supervisor — HTTP runtime entrypoint (AgentCore HTTP contract, port 8080).

Endpoints:
  GET  /ping          -> {"status": "Healthy"}  (AgentCore health check)
  POST /invocations   -> runs the supervisor graph; returns the aggregated investigation result.

Request body (JSON):
  {"tenant_id": "...", "alarm": "...", "scenario_id": "...", "session_id": "...", "stream": false}

In P3, `tenant_id` is derived from the inbound JWT claim rather than trusted from the body; for
P1 it is taken from the body (local dev). Supports JSON (default) and SSE streaming of the
thought-stream for the GUI.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import uuid

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from agents.common.context import RequestContext
from agents.supervisor.graph import run_supervisor

log = logging.getLogger("sre.supervisor")

app = FastAPI(title="SRE Supervisor", version="0.1.0")

# ---------------------------------------------------------------------------
# P3 inbound identity: map a VERIFIED Cognito client_id -> tenant_id.
#
# The AgentCore platform validates the inbound JWT (signature, exp, iss, and client_id against
# the authorizer's AllowedClients) BEFORE the request reaches this container. We therefore trust
# the client_id claim and derive the tenant from it. We DO NOT trust tenant_id from the request
# body — that would let a caller spoof another tenant.
#
# The map is provided via env var SRE_CLIENT_TENANT_MAP as JSON: {"<client_id>": "<tenant_id>"}.
# When the map is empty (local dev / tests, no authorizer), we fall back to the request body so
# the smoke test and local runs keep working unchanged.
# ---------------------------------------------------------------------------
def _load_client_tenant_map() -> dict[str, str]:
    raw = os.getenv("SRE_CLIENT_TENANT_MAP", "").strip()
    if not raw:
        return {}
    try:
        m = json.loads(raw)
        return {str(k): str(v) for k, v in m.items()} if isinstance(m, dict) else {}
    except Exception as e:  # noqa: BLE001
        log.warning("invalid SRE_CLIENT_TENANT_MAP: %s", e)
        return {}


CLIENT_TENANT_MAP = _load_client_tenant_map()
AUTH_ENFORCED = bool(CLIENT_TENANT_MAP)


def _client_id_from_jwt(auth_header: str) -> str | None:
    """Extract client_id from a Bearer JWT. Signature is NOT verified here — the AgentCore platform
    already verified it upstream; we only need to read the (trusted) claim."""
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header[7:].strip()
    parts = token.split(".")
    if len(parts) < 2:
        return None
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)  # pad base64url
        claims = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("could not decode JWT payload: %s", e)
        return None
    # Cognito M2M client-credentials tokens carry the caller client id in `client_id`.
    return claims.get("client_id") or claims.get("aud")


@app.get("/ping")
def ping():
    return {"status": "Healthy"}


def _resolve_tenant(request: Request, body: dict) -> tuple[str | None, str | None]:
    """Return (tenant_id, error). When auth is enforced (client->tenant map present), the tenant
    is derived from the verified JWT client_id and the body tenant_id is ignored. When not enforced
    (local dev / no authorizer), fall back to the body tenant_id."""
    if not AUTH_ENFORCED:
        return body.get("tenant_id", ""), None
    client_id = _client_id_from_jwt(request.headers.get("Authorization", ""))
    if not client_id:
        return None, "missing or unreadable bearer token (inbound auth required)"
    tenant = CLIENT_TENANT_MAP.get(client_id)
    if not tenant:
        return None, f"client_id '{client_id}' is not mapped to any tenant"
    # If a caller also put a tenant_id in the body, it must not contradict the verified identity.
    body_tenant = body.get("tenant_id")
    if body_tenant and body_tenant != tenant:
        log.warning("rejecting tenant spoof attempt: body=%s verified=%s", body_tenant, tenant)
        return None, "request tenant_id does not match authenticated client identity"
    return tenant, None


def _context_from_request(request: Request, body: dict, tenant_id: str) -> RequestContext:
    return RequestContext(
        tenant_id=tenant_id,
        scenario_id=body.get("scenario_id", ""),
        session_id=body.get("session_id") or str(uuid.uuid4()),
        incident_id=body.get("incident_id", ""),
    )


@app.post("/invocations")
async def invocations(request: Request):
    body = await request.json()
    tenant_id, err = _resolve_tenant(request, body)
    if err:
        # 403: identity problem (spoof / unmapped / missing token when enforced)
        return JSONResponse(status_code=403, content={"error": err})
    ctx = _context_from_request(request, body, tenant_id or "")
    alarm = body.get("alarm", "")
    try:
        ctx.require_tenant()
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

    if not body.get("stream"):
        result = run_supervisor(alarm, ctx)
        return JSONResponse(result)

    def event_generator():
        yield f"data: {json.dumps({'type': 'start', 'tenant_id': ctx.tenant_id})}\n\n"
        result = run_supervisor(alarm, ctx)
        for step in result.get("thought_stream", []):
            yield f"data: {json.dumps({'type': 'thought', 'text': step})}\n\n"
        yield f"data: {json.dumps({'type': 'result', 'result': result})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
