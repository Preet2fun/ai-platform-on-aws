"""A2A client: how the supervisor invokes specialist runtimes.

Wraps bedrock-agentcore:InvokeAgentRuntime (the IAM action granted to the
supervisor via the InvokeA2ASpecialists policy) so the router can call any
specialist by name using its runtime ARN.
"""

from __future__ import annotations

import json
from typing import Any

import boto3

from common.config import Settings, get_settings


class A2AClient:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        self._c = boto3.client("bedrock-agentcore", region_name=self.s.region)

    def invoke(self, specialist: str, payload: dict[str, Any], *, session_id: str | None = None) -> dict:
        """Invoke a specialist A2A runtime and return its parsed response.

        Args:
            specialist: logical name (e.g. "security", "cost") -> resolves
                A2A_<NAME>_ARN from config.
            payload: request body forwarded to the specialist.
            session_id: optional session id for multi-turn continuity.
        """
        arn = self.s.a2a_arn(specialist)
        if not arn:
            raise ValueError(f"No runtime ARN configured for specialist '{specialist}' "
                             f"(set A2A_{specialist.upper()}_ARN)")
        kwargs: dict[str, Any] = {
            "agentRuntimeArn": arn,
            "payload": json.dumps(payload).encode("utf-8"),
        }
        if session_id:
            kwargs["runtimeSessionId"] = session_id
        resp = self._c.invoke_agent_runtime(**kwargs)
        body = resp.get("response")
        if hasattr(body, "read"):
            body = body.read()
        if isinstance(body, (bytes, bytearray)):
            body = body.decode("utf-8")
        try:
            return json.loads(body) if body else {}
        except (json.JSONDecodeError, TypeError):
            return {"raw": body}
