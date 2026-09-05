# DO NOT EDIT agent-local copies directly. Edit agents/shared/gateway_client.py then run: ./agents/sync_shared.sh

"""Connect to AgentCore Gateway MCP via SigV4 with cold-start retry logic.

Matches the sample's ResilientMCPClientManager pattern:
- Retries on cold-start failures (3 attempts, 5s delay)
- SigV4 authentication for Gateway
- Tools cached after first successful list
"""
import os
import json
import time
import logging
from typing import List

import boto3
import httpx
from botocore.session import Session as BotocoreSession
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)

GATEWAY_URL = os.environ["GATEWAY_URL"]  # Always set by agentcore deploy
AWS_REGION = os.environ["AWS_REGION"]

# Retry config (matches sample: cold start can take 10-30s)
MCP_RETRY_ATTEMPTS = 3
MCP_RETRY_DELAY = 5
MCP_TIMEOUT = 120

_cached_tools = None


def _sign_request(method: str, url: str, body: str) -> dict:
    """Sign a request with SigV4 for AgentCore Gateway."""
    session = BotocoreSession()
    creds = session.get_credentials().get_frozen_credentials()
    request = AWSRequest(method=method, url=url, data=body, headers={"Content-Type": "application/json"})
    SigV4Auth(creds, "bedrock-agentcore", AWS_REGION).add_auth(request)
    return dict(request.headers)


def _call_mcp_with_retry(method: str, params: dict = None) -> dict:
    """Call MCP JSON-RPC on Gateway with cold-start retry."""
    url = GATEWAY_URL
    if not url:
        raise ValueError("GATEWAY_URL not set")
    
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1})
    
    for attempt in range(MCP_RETRY_ATTEMPTS):
        try:
            headers = _sign_request("POST", url, body)
            resp = httpx.post(url, content=body, headers=headers, timeout=MCP_TIMEOUT)
            
            if resp.status_code == 200:
                data = resp.json()
                if "error" in data:
                    logger.warning(f"MCP error (attempt {attempt+1}): {data['error']}")
                    if attempt < MCP_RETRY_ATTEMPTS - 1:
                        time.sleep(MCP_RETRY_DELAY)
                        continue
                    raise RuntimeError(f"MCP error: {data['error']}")
                return data.get("result", {})
            else:
                logger.warning(f"MCP HTTP {resp.status_code} (attempt {attempt+1})")
                if attempt < MCP_RETRY_ATTEMPTS - 1:
                    time.sleep(MCP_RETRY_DELAY)
                    continue
                raise RuntimeError(f"MCP returned {resp.status_code}")
                
        except httpx.TimeoutException:
            logger.warning(f"MCP timeout (attempt {attempt+1}/{MCP_RETRY_ATTEMPTS})")
            if attempt < MCP_RETRY_ATTEMPTS - 1:
                time.sleep(MCP_RETRY_DELAY)
            else:
                raise
        except httpx.ConnectError as e:
            logger.warning(f"MCP connect error (attempt {attempt+1}): {e}")
            if attempt < MCP_RETRY_ATTEMPTS - 1:
                time.sleep(MCP_RETRY_DELAY)
            else:
                raise


def _invoke_tool(tool_name: str, arguments: dict) -> str:
    """Invoke a specific MCP tool via Gateway with retry."""
    try:
        result = _call_mcp_with_retry("tools/call", {"name": tool_name, "arguments": arguments})
        content = result.get("content", [])
        if content and isinstance(content, list):
            texts = [c.get("text", str(c)) for c in content if isinstance(c, dict)]
            return "\n".join(texts) if texts else json.dumps(content, default=str)
        return json.dumps(result, default=str)
    except Exception as e:
        return f"Tool error ({tool_name}): {e}"


def get_mcp_tools() -> List[StructuredTool]:
    """Discover and return MCP tools from Gateway as LangChain StructuredTools."""
    global _cached_tools
    if _cached_tools is not None and len(_cached_tools) > 0:
        return _cached_tools
    
    if not GATEWAY_URL:
        logger.warning("GATEWAY_URL not set")
        return []

    try:
        result = _call_mcp_with_retry("tools/list")
        tools_data = result.get("tools", [])
    except Exception as e:
        logger.error(f"Failed to list MCP tools: {e}")
        return []

    lc_tools = []
    for t in tools_data:
        name = t["name"]
        description = t.get("description", f"MCP tool: {name}")[:1024]

        def _make_invoke(tn: str):
            def invoke_fn(**kwargs) -> str:
                return _invoke_tool(tn, kwargs)
            return invoke_fn

        tool = StructuredTool.from_function(
            func=_make_invoke(name),
            name=name,
            description=description,
            return_direct=False,
        )
        lc_tools.append(tool)

    logger.info(f"Loaded {len(lc_tools)} MCP tools from Gateway")
    _cached_tools = lc_tools
    return lc_tools
