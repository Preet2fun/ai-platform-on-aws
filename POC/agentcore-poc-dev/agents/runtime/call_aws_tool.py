# agents/shared/call_aws_tool.py
"""Shared call_aws tool implementation — DRY, single source of truth.

Each agent runtime imports this and wraps it with its own session provider
(tenant-scoped or default boto3).
"""

import json
import logging
import os
from typing import Callable

import boto3
from langchain_core.tools import tool

from allowed_operations import is_operation_allowed
from base_runtime import _safe_error_response

logger = logging.getLogger(__name__)

AWS_REGION = os.environ["AWS_REGION"]  # Always set by AgentCore runtime

# Auto-correct common LLM mistakes for service names
SERVICE_MAP = {
    "bedrock-agentcore": "bedrock-agentcore-control",
    "bedrock-agent": "bedrock-agentcore-control",
    "agentcore": "bedrock-agentcore-control",
    "cost-explorer": "ce",
    "costexplorer": "ce",
    "trusted-advisor": "trustedadvisor",
    "security-hub": "securityhub",
    "cloud-trail": "cloudtrail",
    "cloud-watch": "cloudwatch",
}

# Max characters returned to the model from any single AWS call. Bounds token usage
# and prevents dumping large payloads into the prompt (LLM cost/latency guard).
_MAX_OUTPUT_CHARS = 5000
# Max bytes read from an s3.get_object body. get_object returns a StreamingBody; we
# read a bounded slice instead of the whole (potentially huge) object into memory.
_MAX_S3_BODY_BYTES = 4096


def make_call_aws_tool(session_fn: Callable[..., boto3.Session], default_region: str = AWS_REGION):
    """Factory that creates a call_aws @tool with a specific session provider.
    
    Args:
        session_fn: A callable(region) that returns a boto3.Session (may be tenant-scoped)
        default_region: Default region for this agent
    """

    @tool
    def call_aws(service: str, operation: str, parameters: str = "{}", region: str = default_region) -> str:
        """Call any AWS API. Service name hints: ec2, ecs, lambda, rds, s3, dynamodb, cloudtrail, securityhub, ce (cost explorer)."""
        try:
            service = SERVICE_MAP.get(service, service)
            if not is_operation_allowed(service, operation):
                return f"Operation '{operation}' on service '{service}' is not permitted. Only read/describe/list/get operations are allowed."
            session = session_fn(region)
            client = session.client(service, region_name=region)
            params = json.loads(parameters) if parameters else {}
            result = getattr(client, operation)(**params)
            result.pop("ResponseMetadata", None)
            # s3.get_object returns a StreamingBody in result["Body"]; json.dumps would
            # serialise its repr, not the content. Read a bounded amount and close the
            # stream (rule 16: bounded reads + explicit resource cleanup).
            if operation == "get_object" and "Body" in result:
                body = result["Body"]
                try:
                    raw = body.read(_MAX_S3_BODY_BYTES)
                finally:
                    body.close()
                try:
                    result["Body"] = raw.decode("utf-8", errors="replace")
                except (AttributeError, UnicodeDecodeError):
                    result["Body"] = f"<{len(raw)} bytes binary content>"
            output = json.dumps(result, default=str, indent=2)
            return output[:_MAX_OUTPUT_CHARS] if len(output) > _MAX_OUTPUT_CHARS else output
        except Exception as e:
            logger.error(f"call_aws {service}.{operation} failed", exc_info=True)
            return f"AWS API error ({service}.{operation}): {_safe_error_response(e)}"

    return call_aws
