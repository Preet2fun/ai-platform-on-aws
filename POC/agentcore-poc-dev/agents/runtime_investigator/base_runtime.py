# agents/shared/base_runtime.py
"""Base class for specialist A2A runtimes.

Eliminates boilerplate across 6 specialist agents. Each specialist only provides:
- agent_name: identifier for logging and responses
- system_prompt: the LLM system prompt
- get_tools(): returns the list of LangChain tools

Everything else (FastAPI app, health endpoint, invocation handler, graph creation,
error handling, MCP fallback) is handled by this base class.

Usage:
    from base_runtime import BaseSpecialistRuntime

    runtime = BaseSpecialistRuntime(
        agent_name="cloudwatch",
        system_prompt=SYSTEM_PROMPT,
        get_tools_fn=_get_tools,
    )
    app = runtime.app

    if __name__ == "__main__":
        runtime.run()
"""

import os
import logging
from typing import Callable, List

from fastapi import FastAPI, Request
import uvicorn
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from sanitize import sanitize_user_input

logger = logging.getLogger(__name__)


def _safe_error_response(e: Exception) -> str:
    """Return a generic error message safe to expose to callers. Full error is logged server-side."""
    from botocore.exceptions import ClientError
    if isinstance(e, ClientError):
        code = e.response.get("Error", {}).get("Code", "")
        if "Access" in code or "Authorization" in code:
            return "Permission denied for this operation"
        if "Throttl" in code:
            return "Service rate limit exceeded, please retry"
        if "Timeout" in code:
            return "AWS service timeout"
        return "AWS service error"
    if "timeout" in str(e).lower():
        return "Request timed out"
    return "An unexpected error occurred"


class BaseSpecialistRuntime:
    """Shared base for all specialist A2A runtimes."""

    def __init__(
        self,
        agent_name: str,
        system_prompt: str,
        get_tools_fn: Callable[[], List[BaseTool]],
        model_id: str = None,
        region: str = None,
    ):
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.get_tools_fn = get_tools_fn
        self.model_id = model_id or os.getenv("MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0")
        self.region = region or os.environ["AWS_REGION"]
        self._graph = None

        # Create FastAPI app
        self.app = FastAPI(title=f"{agent_name.title()} A2A Runtime")
        self._register_routes()

    def _build_graph(self):
        """Build the LangGraph ReAct agent."""
        llm = ChatBedrockConverse(
            model_id=self.model_id,
            region_name=self.region,
            max_tokens=4096,
            temperature=0,
        )
        tools = self.get_tools_fn()
        graph = create_react_agent(
            llm, tools, prompt=self.system_prompt,
        )
        logger.info(f"LangGraph {self.agent_name} agent created: tools={len(tools)}")
        return graph

    def get_graph(self):
        """Get or build the cached graph."""
        if self._graph is None:
            self._graph = self._build_graph()
        return self._graph

    def _register_routes(self):
        """Register FastAPI routes."""

        @self.app.post("/invocations")
        async def invoke(request: Request):
            payload = await request.json()
            prompt = sanitize_user_input(payload.get("prompt", payload.get("input", "")))
            account_name = payload.get("account_name", "default")
            region = payload.get("region", self.region)

            logger.info(f"{self.agent_name} invoked: {prompt[:50]}... (account={account_name})")
            enriched = f"[Account: {account_name}, Region: {region}]\n{prompt}"

            try:
                graph = self.get_graph()
                result = await graph.ainvoke({"messages": [HumanMessage(content=enriched)]})
                output = result["messages"][-1].content
                return {"result": output, "agent_type": self.agent_name}
            except Exception as e:
                logger.error(f"{self.agent_name} error: {e}", exc_info=True)
                return {"result": _safe_error_response(e), "agent_type": self.agent_name}

        @self.app.get("/ping")
        def ping():
            return {"status": "healthy", "agent": self.agent_name}

    def run(self, host: str = "0.0.0.0", port: int = 8080):
        """Start the uvicorn server."""
        logger.info(f"Starting {self.agent_name} runtime on port {port}...")
        uvicorn.run(self.app, host=host, port=port)
