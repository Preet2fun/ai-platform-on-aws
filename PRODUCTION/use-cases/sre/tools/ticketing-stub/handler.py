"""Stub 'ticketing' API for the P4 credential-vault demo.

Stands in for a real ticketing SaaS (Jira/ServiceNow). Exposed via a Lambda Function URL and
fronted by the AgentCore Gateway as an OpenAPI target with an API-KEY credential provider.

The whole point of the demo: prove the Gateway injects the vault-stored API key into the
outbound request. This stub inspects the incoming request for the configured header and reports
received_auth=true/false, plus a fabricated ticket id. It never validates a real key — it only
confirms the gateway attached one, demonstrating that the secret flowed vault -> gateway -> API
without ever touching the agent, the LLM, or the tool arguments.
"""
import json
import uuid

# The header the gateway is configured to inject the API key into (see credentialParameterName).
API_KEY_HEADER = "x-api-key"


def lambda_handler(event, context):
    # Lambda Function URL event: headers are lower-cased in event["headers"].
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    received_key = headers.get(API_KEY_HEADER)

    body_raw = event.get("body") or "{}"
    try:
        payload = json.loads(body_raw)
    except Exception:  # noqa: BLE001
        payload = {}

    resp = {
        "ticket_id": f"SRE-{uuid.uuid4().hex[:8].upper()}",
        "status": "created",
        # True iff the gateway injected the API key header. This is the demo's proof point.
        "received_auth": bool(received_key),
        "summary": payload.get("summary", ""),
        "tenant_id": payload.get("tenant_id", ""),
    }
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(resp),
    }
