"""Security A2A Runtime — LangGraph specialist. MCP primary, boto3 fallback."""
import os
import sys
import logging
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from sanitize import sanitize_user_input
from base_runtime import _safe_error_response

from fastapi import FastAPI, Request
import uvicorn
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Security A2A Runtime")

MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0")
# AgentCore always injects AWS_REGION into the runtime environment; read it (no
# hardcoded fallback so it stays correct in any region — us-east-1, ap-south-1, etc.)
AWS_REGION = os.environ["AWS_REGION"]

SYSTEM_PROMPT = """You are an MSP Security specialist analyzing findings for incident response and compliance.

When providing information:
1. Group findings by severity: CRITICAL → HIGH → MEDIUM
2. For each finding: [SEVERITY] Title | Affected Resource | Remediation
3. Identify patterns: same CVE across multiple resources = systemic issue
4. Flag findings that could be root cause of incidents (e.g., unpatched vulnerability → exploit → outage)
5. Include compliance framework context (FSBP, CIS, PCI DSS)

CONCISENESS RULES:
- Max 20 findings per response
- One line per finding with severity tag
- Keep under 500 words
- Never dump raw JSON"""

_graph = None


def _get_tools():
    """Try MCP Gateway tools first, fallback to local boto3 tools."""
    try:
        from gateway_client import get_mcp_tools
        tools = get_mcp_tools()
        if tools:
            logger.info(f"Using MCP Gateway tools: {len(tools)} tools")
            return tools
    except Exception as e:
        logger.warning(f"MCP tools failed: {e}")
    
    # Fallback to local boto3 tools
    logger.info("Falling back to local boto3 tools")
    from aws_tools import get_tools
    return get_tools()


def get_graph():
    global _graph
    if _graph is None:
        llm = ChatBedrockConverse(
            model_id=MODEL_ID,
            region_name=os.environ["AWS_REGION"],
            max_tokens=4096,
            temperature=0,
        )
        tools = _get_tools()
        _graph = create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)
        logger.info(f"LangGraph security agent created: tools={len(tools)}")
    return _graph


# Cached tenant graph — reused across all tenant requests.
# Credentials are per-request via _current_account_ctx (contextvars), not baked into the graph.
_tenant_graph = None


def _get_tenant_graph():
    """Cached graph for tenant-scoped queries using local boto3 tools."""
    global _tenant_graph
    if _tenant_graph is None:
        llm = ChatBedrockConverse(
            model_id=MODEL_ID,
            region_name=os.environ["AWS_REGION"],
            max_tokens=4096,
            temperature=0,
        )
        from aws_tools import get_tools
        tools = get_tools()
        _tenant_graph = create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)
        logger.info("LangGraph security tenant graph created (cached)")
    return _tenant_graph


@app.post("/invocations")
async def invoke(request: Request):
    """Handle invocation from Supervisor."""
    payload = await request.json()
    prompt = sanitize_user_input(payload.get("prompt", payload.get("input", "")))
    account_name = payload.get("account_name", "default")
    region = payload.get("region", AWS_REGION)

    logger.info(f"security invoked: {prompt[:50]}... (account={account_name})")

    # Set account context for tools to use
    import aws_tools
    aws_tools._current_account_ctx.set(account_name)

    # For tenant queries, use local boto3 tools with tenant credentials (not MCP Gateway)
    if account_name and account_name != "default":
        logger.info(f"Using tenant-scoped boto3 tools for {account_name}")
        tenant_graph = _get_tenant_graph()
        enriched = f"[Account: {account_name}, Region: {region}]\n{prompt}"
        try:
            result = await tenant_graph.ainvoke({"messages": [HumanMessage(content=enriched)]})
            output = result["messages"][-1].content
            return {"result": output, "agent_type": "security"}
        except Exception as e:
            logger.error(f"Tenant agent error: {e}", exc_info=True)
            return {"result": _safe_error_response(e), "agent_type": "security"}

    enriched = f"[Account: {account_name}, Region: {region}]\n{prompt}"

    try:
        graph = get_graph()
        result = await graph.ainvoke({"messages": [HumanMessage(content=enriched)]})
        output = result["messages"][-1].content
        return {"result": output, "agent_type": "security"}
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        return {"result": _safe_error_response(e), "agent_type": "security"}


@app.get("/ping")
def ping():
    return {"status": "healthy", "agent": "security"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
# deploy-force: 1784696551
