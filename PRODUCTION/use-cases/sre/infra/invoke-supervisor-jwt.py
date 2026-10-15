"""P3 Checkpoint 3 harness — invoke the supervisor with a Cognito M2M Bearer token (not SigV4).

Fetches a client-credentials access token from the Cognito token endpoint for the given tenant's
app client, then calls the supervisor runtime's /invocations over HTTPS with Authorization: Bearer.

This is how a real caller reaches a JWT-protected AgentCore runtime: SigV4 (invoke_agent_runtime)
no longer works once the inbound JWT authorizer is enabled.

Usage:
  CLIENT_ID=... CLIENT_SECRET=... python3 infra/invoke-supervisor-jwt.py <scenario> "<alarm>" [body_tenant]
    - body_tenant (optional): if set, included in the request body to test spoof-rejection.
Env:
  TOKEN_ENDPOINT  (default: the dev pool token endpoint)
  SUPERVISOR_ARN  (default: the dev supervisor runtime ARN)
  REGION          (default: us-east-1)
  SCOPE           (default: sre-api/invoke)
  NO_TOKEN=1      skip fetching a token (to test the 401 path)
"""
import base64
import json
import os
import sys
import urllib.parse
import uuid

import httpx

REGION = os.getenv("REGION", "us-east-1")
TOKEN_ENDPOINT = os.getenv(
    "TOKEN_ENDPOINT",
    "https://sre-agentic-dev-auth.auth.us-east-1.amazoncognito.com/oauth2/token",
)
SUPERVISOR_ARN = os.getenv(
    "SUPERVISOR_ARN",
    "arn:aws:bedrock-agentcore:us-east-1:001961766007:runtime/sre_agentic_dev_supervisor-dSf6vD9ngf",
)
SCOPE = os.getenv("SCOPE", "sre-api/invoke")


def fetch_token(client_id: str, client_secret: str) -> str:
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = httpx.post(
        TOKEN_ENDPOINT,
        headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "scope": SCOPE},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def invoke(token: str | None, body: dict) -> tuple[int, str]:
    escaped = urllib.parse.quote(SUPERVISOR_ARN, safe="")
    url = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{escaped}/invocations?qualifier=DEFAULT"
    headers = {
        "Content-Type": "application/json",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": f"p3-{uuid.uuid4().hex}{uuid.uuid4().hex}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with httpx.Client(timeout=840) as client:
        resp = client.post(url, json=body, headers=headers)
        return resp.status_code, resp.text


def main():
    scenario = sys.argv[1] if len(sys.argv) > 1 else "rds-connection-exhaustion"
    alarm = sys.argv[2] if len(sys.argv) > 2 else "RDS connection pool exhausted on checkout-service; 5xx spiking"
    body_tenant = sys.argv[3] if len(sys.argv) > 3 else None

    body = {"scenario_id": scenario, "alarm": alarm, "session_id": str(uuid.uuid4())}
    if body_tenant:
        body["tenant_id"] = body_tenant  # for spoof test

    token = None
    if os.getenv("NO_TOKEN") != "1":
        cid, sec = os.environ.get("CLIENT_ID"), os.environ.get("CLIENT_SECRET")
        if not cid or not sec:
            print("ERROR: set CLIENT_ID and CLIENT_SECRET (or NO_TOKEN=1)")
            sys.exit(2)
        token = fetch_token(cid, sec)
        print(f"got token (len={len(token)})")

    status, text = invoke(token, body)
    print(f"HTTP {status}")
    print(text[:4000])


if __name__ == "__main__":
    main()
