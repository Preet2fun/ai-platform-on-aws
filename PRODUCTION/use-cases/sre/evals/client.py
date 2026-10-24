"""Eval client: invoke the deployed supervisor (JWT) per tenant, or score an existing trace.

Reference-based evaluation needs the agent's actual output. This module obtains it two ways:
  - fresh run: fetch the tenant's M2M token, invoke the supervisor, return the full JSON result.
  - existing trace: (future) pull a prior run's result from its CloudWatch trace by id.

Per-tenant Cognito client credentials are read from the identity stack / Cognito at runtime; the
tenant->client_id mapping mirrors the supervisor's enforced mapping (P3).
"""
from __future__ import annotations

import base64
import json
import os
import urllib.parse
import uuid

import boto3
import httpx

REGION = os.getenv("AWS_REGION", "us-east-1")
POOL_ID = os.getenv("SRE_POOL_ID", "us-east-1_wWlzIHoRM")
TOKEN_ENDPOINT = os.getenv(
    "SRE_TOKEN_ENDPOINT",
    "https://sre-agentic-dev-auth.auth.us-east-1.amazoncognito.com/oauth2/token",
)
SUPERVISOR_ARN = os.getenv(
    "SRE_SUPERVISOR_ARN",
    "arn:aws:bedrock-agentcore:us-east-1:001961766007:runtime/sre_agentic_dev_supervisor-dSf6vD9ngf",
)
SCOPE = os.getenv("SRE_GATEWAY_SCOPE", "sre-api/invoke")

# tenant -> Cognito M2M client_id (matches the supervisor's ClientTenantMap, P3)
TENANT_CLIENT = {
    "acme-retail": os.getenv("SRE_ACME_CLIENT_ID", "66f0eb5m3ri4ad02d6hjjd37db"),
    "globex-fintech": os.getenv("SRE_GLOBEX_CLIENT_ID", "5cnjgnqi4o2avg62egtu6be4tt"),
}


def _client_secret(client_id: str) -> str:
    cog = boto3.client("cognito-idp", region_name=REGION)
    return cog.describe_user_pool_client(UserPoolId=POOL_ID, ClientId=client_id)["UserPoolClient"]["ClientSecret"]


def _token(tenant: str) -> str:
    cid = TENANT_CLIENT[tenant]
    sec = _client_secret(cid)
    basic = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    r = httpx.post(
        TOKEN_ENDPOINT,
        headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "scope": SCOPE},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def run_investigation(tenant: str, scenario: str, alarm: str, timeout: float = 840.0) -> dict:
    """Invoke the deployed supervisor for (tenant, scenario) and return the full result dict.

    tenant identity is derived by the supervisor from the token's client_id (P3), so we send the
    scenario + alarm only; tenant comes from WHICH client's token we use.
    """
    token = _token(tenant)
    escaped = urllib.parse.quote(SUPERVISOR_ARN, safe="")
    url = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{escaped}/invocations?qualifier=DEFAULT"
    session_id = str(uuid.uuid4())  # our logical session id; appears on spans as sre.session_id
    body = {"scenario_id": scenario, "alarm": alarm, "session_id": session_id}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": f"eval-{uuid.uuid4().hex}{uuid.uuid4().hex}",
    }
    with httpx.Client(timeout=timeout) as c:
        resp = c.post(url, json=body, headers=headers)
    resp.raise_for_status()
    result = json.loads(resp.text)
    # thread our session id through so the runner can fetch the matching trace for attribution
    result.setdefault("_eval_session_id", session_id)
    return result
