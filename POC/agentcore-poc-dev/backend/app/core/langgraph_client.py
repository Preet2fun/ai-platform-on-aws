"""
LangGraph Client — wraps boto3.invoke_agent_runtime for the supervisor.

Same interface as the original AgentCoreClient. Uses boto3 to call
AgentCore Runtime (where the LangGraph supervisor runs).
"""
import json
import logging
import uuid
import asyncio
import threading
from typing import Dict, Any, Optional, AsyncGenerator
import boto3
from botocore.config import Config
from app.core.config import settings

logger = logging.getLogger(__name__)

_client_instances: Dict[str, "LangGraphClient"] = {}
_client_instances_lock = threading.Lock()


def get_langgraph_client(region: str = None) -> "LangGraphClient":
    """Return a cached LangGraphClient singleton for the given region."""
    region = region or settings.AWS_REGION
    if region in _client_instances:
        return _client_instances[region]
    with _client_instances_lock:
        if region not in _client_instances:
            _client_instances[region] = LangGraphClient(region=region)
            logger.info(f"Created LangGraphClient singleton for region: {region}")
    return _client_instances[region]


# Backward-compatible alias
get_agentcore_client = get_langgraph_client


class LangGraphClient:
    """Client for invoking AgentCore Runtime (LangGraph supervisor) via boto3."""

    def __init__(self, region: str = None):
        self.region = region or settings.AWS_REGION
        client_config = Config(
            read_timeout=300,
            connect_timeout=10,
            retries={'max_attempts': 1}
        )
        self.runtime_client = boto3.client('bedrock-agentcore', region_name=region, config=client_config)

    async def invoke_runtime(
        self,
        runtime_arn: str,
        payload: Dict[str, Any],
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Invoke runtime (non-streaming). Collects final 'complete' event."""
        if not session_id:
            session_id = str(uuid.uuid4())
        try:
            async for evt in self.invoke_runtime_stream(runtime_arn, payload, session_id):
                event_name = evt.get("event", "")
                if event_name == "complete":
                    data = evt.get("data", {})
                    return {
                        "response": data.get("response", ""),
                        "agent_type": data.get("agent_type", "supervisor"),
                        "session_id": session_id,
                        "success": True,
                    }
                elif event_name == "error":
                    return {
                        "response": evt.get("data", {}).get("message", "Agent error"),
                        "agent_type": "error",
                        "session_id": session_id,
                        "success": False,
                    }
            return {"response": "", "agent_type": "error", "session_id": session_id, "success": False}
        except Exception as e:
            logger.error(f"invoke_runtime error: {e}", exc_info=True)
            return {
                "response": "An unexpected error occurred. Please try again.",
                "agent_type": "error",
                "session_id": session_id,
                "success": False,
            }

    async def invoke_runtime_stream(
        self,
        runtime_arn: str,
        payload: Dict[str, Any],
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Invoke AgentCore Runtime with SSE streaming."""
        if not session_id:
            session_id = str(uuid.uuid4())

        try:
            payload_bytes = json.dumps(payload).encode('utf-8')
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.runtime_client.invoke_agent_runtime(
                    agentRuntimeArn=runtime_arn,
                    runtimeSessionId=session_id,
                    payload=payload_bytes,
                    qualifier='DEFAULT'
                )
            )

            content_type = response.get("contentType", "")

            if "text/event-stream" not in content_type:
                # Non-SSE response
                raw_bytes = b''
                for chunk in response.get("response", []):
                    raw_bytes += chunk
                response_text = raw_bytes.decode('utf-8', errors='replace')
                try:
                    result = json.loads(response_text) if response_text else {}
                except json.JSONDecodeError:
                    result = {"response": response_text}
                yield {"event": "complete", "data": {
                    "response": result.get("result", result.get("response", response_text)),
                    "agent_type": result.get("agent_type", "supervisor"),
                }}
                return

            # SSE stream parsing
            current_event = ""
            current_data = ""
            queue = asyncio.Queue()

            def _stream_lines_to_queue():
                try:
                    for line in response["response"].iter_lines(chunk_size=64):
                        decoded = line.decode("utf-8", errors="replace") if line else ""
                        loop.call_soon_threadsafe(queue.put_nowait, decoded)
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)

            loop.run_in_executor(None, _stream_lines_to_queue)

            while True:
                line = await queue.get()
                if line is None:
                    break
                if line.startswith("event:"):
                    current_event = line[6:].strip()
                elif line.startswith("data:"):
                    current_data = line[5:].strip()
                elif line == "" and current_event:
                    try:
                        data = json.loads(current_data) if current_data else {}
                    except json.JSONDecodeError:
                        data = {"text": current_data}
                    yield {"event": current_event, "data": data}
                    current_event = ""
                    current_data = ""

        except Exception as e:
            logger.error(f"invoke_runtime_stream error: {e}", exc_info=True)
            yield {"event": "error", "data": {"message": str(e)}}


# Alias for backward compatibility
AgentCoreClient = LangGraphClient
