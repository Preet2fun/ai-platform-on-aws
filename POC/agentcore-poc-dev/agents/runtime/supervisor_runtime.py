"""MSP Supervisor Runtime — LangGraph + plain FastAPI (AgentCore compatible).

HTTP protocol on port 8080. Routes to 6 specialist A2A agents.
Uses AgentCore Memory for conversational context.
"""
import os
import re
import sys
import json
import logging
import uuid
import contextvars
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
import uvicorn
import boto3
from langchain_aws import ChatBedrockConverse
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from sanitize import sanitize_user_input
from base_runtime import _safe_error_response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MSP Supervisor Runtime")

MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-sonnet-4-5-20250929-v1:0")
MEMORY_ID = os.getenv("MEMORY_ID", "")
AWS_REGION = os.environ["AWS_REGION"]

# A2A specialist ARNs — set via environment variables (deploy.sh populates these)
AGENT_ARNS = {
    "cloudwatch": os.environ.get("CLOUDWATCH_A2A_ARN", ""),
    "security": os.environ.get("SECURITY_A2A_ARN", ""),
    "cost": os.environ.get("COST_A2A_ARN", ""),
    "advisor": os.environ.get("ADVISOR_A2A_ARN", ""),
    "jira": os.environ.get("JIRA_A2A_ARN", ""),
    "knowledge": os.environ.get("KNOWLEDGE_A2A_ARN", ""),
    "investigator": os.environ.get("INVESTIGATOR_A2A_ARN", ""),
}

# ARN format: arn:aws:bedrock-agentcore:<region>:<12-digit-account>:runtime/<name>
_ARN_PATTERN = re.compile(r"^arn:aws:bedrock-agentcore:[a-z0-9-]+:\d{12}:runtime/.+$")


def _validate_agent_arns() -> None:
    """Log startup ARN health — surfaces typos immediately instead of failing on first invocation."""
    configured = []
    missing = []
    malformed = []
    for name, arn in AGENT_ARNS.items():
        if not arn:
            missing.append(name)
        elif not _ARN_PATTERN.match(arn):
            malformed.append((name, arn))
        else:
            configured.append(name)

    logger.info("Agent ARNs configured: %s", configured)
    if missing:
        logger.info("Agent ARNs not configured (will skip): %s", missing)
    if malformed:
        for name, arn in malformed:
            logger.warning(
                "Malformed ARN for '%s': '%s' — expected arn:aws:bedrock-agentcore:<region>:<account>:runtime/<name>",
                name, arn
            )


# Run validation at import time (startup)
_validate_agent_arns()

_runtime_client = None
_memory_client = None
_current_account_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("current_account", default="default")


def _get_runtime_client():
    global _runtime_client
    if _runtime_client is None:
        from botocore.config import Config
        _runtime_client = boto3.client(
            "bedrock-agentcore",
            region_name=AWS_REGION,
            config=Config(read_timeout=180, connect_timeout=10)
        )
    return _runtime_client


def _get_memory_client():
    global _memory_client
    if _memory_client is None:
        _memory_client = boto3.client("bedrock-agentcore", region_name=AWS_REGION)
    return _memory_client


def _invoke_specialist(agent_name: str, prompt: str, account_name: str = "") -> str:
    """Call a specialist A2A agent via invoke_agent_runtime."""
    arn = AGENT_ARNS.get(agent_name)
    if not arn:
        return f"Agent '{agent_name}' not configured."
    acct = account_name or _current_account_ctx.get()
    try:
        client = _get_runtime_client()
        import uuid as _uuid
        resp = client.invoke_agent_runtime(
            agentRuntimeArn=arn,
            runtimeSessionId=f"sup-{_uuid.uuid4().hex}",
            payload=json.dumps({
                "prompt": prompt,
                "account_name": acct,
                "region": AWS_REGION
            }).encode()
        )
        result = json.loads(resp["response"].read())
        return result.get("result", str(result))
    except Exception as e:
        logger.error(f"Error calling {agent_name}", exc_info=True)
        return f"Error calling {agent_name}: {_safe_error_response(e)}"


# --- 6 Delegation Tools ---
@tool
def check_cloudwatch(prompt: str) -> str:
    """Query live AWS CloudWatch for current alarms, metric values, and log groups.
    Use ONLY for checking real-time AWS monitoring status — not for investigating incidents or finding root causes."""
    return _invoke_specialist("cloudwatch", prompt)


@tool
def check_security(prompt: str) -> str:
    """Check Security Hub findings, CVEs, and compliance posture."""
    return _invoke_specialist("security", prompt)


@tool
def analyze_costs(prompt: str) -> str:
    """Analyze AWS costs, spending breakdown, and savings opportunities."""
    return _invoke_specialist("cost", prompt)


@tool
def check_advisor(prompt: str) -> str:
    """Check Trusted Advisor recommendations across all pillars."""
    return _invoke_specialist("advisor", prompt)


@tool
def manage_jira(prompt: str) -> str:
    """Manage Jira tickets — search, create, update, transition."""
    return _invoke_specialist("jira", prompt)


@tool
def search_knowledge(prompt: str) -> str:
    """Search AWS documentation, guides, and best practices."""
    return _invoke_specialist("knowledge", prompt)


@tool
def investigate_scenario(prompt: str) -> str:
    """Perform Root Cause Analysis by investigating a tenant's telemetry database.
    Connects to the database automatically (discovers via RDS tags + Secrets Manager),
    explores schema, runs SQL queries, correlates metrics/logs/traces, narrows dimensions,
    dismisses false leads, and produces a structured RCA report.

    Use this tool when the user wants to:
    - Investigate an alert, incident, or anomaly for a specific tenant
    - Find root cause of latency, errors, or performance degradation
    - Analyze telemetry data (metrics, logs, spans) stored in a database
    - Perform RCA investigation

    Do NOT use check_cloudwatch for these — check_cloudwatch only queries live AWS CloudWatch.
    This tool queries the tenant's own telemetry database with full investigation capability."""
    return _invoke_specialist("investigator", prompt)


# --- Memory ---
def _load_memory(actor_id: str, session_id: str) -> str:
    """Load last 3 turns from AgentCore Memory."""
    if not MEMORY_ID:
        return ""
    try:
        client = _get_memory_client()
        resp = client.list_events(
            memoryId=MEMORY_ID, actorId=actor_id, sessionId=session_id, includePayloads=True
        )
        events = resp.get("events", [])[-3:]
        if not events:
            return ""
        lines = []
        for ev in events:
            for msg in ev.get("payload", []):
                conv = msg.get("conversational", {})
                role = conv.get("role", "")
                text = conv.get("content", {}).get("text", "")[:500]
                if text:
                    lines.append(f"{role}: {text}")
        return "Previous conversation:\n" + "\n".join(lines) + "\n\n" if lines else ""
    except Exception as e:
        logger.warning(f"Memory load failed: {e}")
        return ""


def _save_memory(actor_id: str, session_id: str, user_msg: str, assistant_msg: str):
    """Save turn to AgentCore Memory."""
    if not MEMORY_ID:
        return
    try:
        client = _get_memory_client()
        client.create_event(
            memoryId=MEMORY_ID,
            actorId=actor_id,
            sessionId=session_id,
            eventTimestamp=datetime.now(timezone.utc),
            payload=[
                {"conversational": {"content": {"text": user_msg}, "role": "USER"}},
                {"conversational": {"content": {"text": assistant_msg[:4000]}, "role": "ASSISTANT"}},
            ]
        )
    except Exception as e:
        logger.warning(f"Memory save failed: {e}")


# --- LangGraph Agent ---
SUPERVISOR_PROMPT = """You are an AWS Multi-Service Supervisor that orchestrates specialist agents to solve operational problems for tenants.
The user has already selected a tenant/account from the UI — the account_name is passed
automatically with every request. Never ask which account or tenant to investigate.
All tool calls automatically operate on the selected tenant's account and data — you do not need to specify the tenant.

<available_tools>
- **investigate_scenario**: Deep RCA — queries the selected tenant's telemetry database (otel_metrics, otel_logs, otel_spans). Use for: root cause analysis, anomaly investigation, performance degradation, incident investigation, latency issues, error spikes.
- **check_cloudwatch**: Live infrastructure state — queries the selected tenant's AWS CloudWatch for current alarms, metrics, and logs. Use for: active alarms, current resource health, real-time metric values, validation of findings.
- **check_security**: Security posture — queries the selected tenant's Security Hub for findings and compliance status.
- **analyze_costs**: Cost analysis — queries the selected tenant's Cost Explorer for spending patterns and optimization.
- **check_advisor**: Best practices — queries the selected tenant's Trusted Advisor for recommendations.
- **manage_jira**: Ticket management — search, create, update, comment, transition Jira tickets for the tenant.
- **search_knowledge**: Documentation — searches AWS troubleshooting guides and best practices.
</available_tools>

<reasoning_approach>
Think like a Site Reliability Engineer (SRE) investigating the tenant's environment:

1. **Understand the intent** — Is this a monitoring query, an investigation, a cost question, or a general ask?

2. **For investigations/RCA** — Follow the standard RCA methodology:
   a. First, gather evidence from the tenant's telemetry (investigate_scenario) to find root cause
   b. Then, validate findings against the tenant's live infrastructure (check_cloudwatch) to confirm current state
   c. Synthesize into a complete RCA report with: root cause, evidence, current state, recommendation

3. **For monitoring queries** — Route directly to the relevant specialist (operates on the tenant's account).

4. **For multi-domain queries** — Use multiple tools and synthesize the combined findings from the tenant's data.

5. **Decide tool usage dynamically** — Based on what each tool returns, decide if additional tools are needed to get a complete picture of the tenant's situation.
</reasoning_approach>

<rules>
1. Call tools without preamble — act immediately based on the query intent
2. For RCA queries: investigate first (tenant's DB telemetry), then validate (tenant's live AWS) — this mirrors how a human SRE operates
3. NEVER retry a tool call that returns an error — report the error and stop
4. Synthesize findings with business context — what is the impact on the tenant, is it still happening, what should be done
5. For greetings or casual questions, respond directly without calling any tool
6. All tools are tenant-scoped — they automatically target the selected account. You never need to cross into a different tenant's data.
</rules>
"""

_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        llm = ChatBedrockConverse(
            model_id=MODEL_ID,
            region_name=AWS_REGION,
            max_tokens=4096,
            temperature=0,
        )
        tools = [check_cloudwatch, check_security, analyze_costs, check_advisor, manage_jira, search_knowledge, investigate_scenario]
        _graph = create_react_agent(llm, tools, prompt=SUPERVISOR_PROMPT)
        logger.info(f"LangGraph supervisor created: model={MODEL_ID}, tools={len(tools)}")
    return _graph


@app.post("/invocations")
async def invoke(request: Request):
    """Main supervisor entry point — AgentCore calls this."""
    payload = await request.json()
    prompt = sanitize_user_input(payload.get("prompt", payload.get("input", "")))
    user_id = payload.get("user_context", {}).get("user_id", "anonymous")
    session_id = payload.get("session_id", f"msp-{user_id}")
    account_name = payload.get("account_name", "default")

    logger.info(f"Supervisor invoked: {prompt[:50]}... (user={user_id[:8]}, account={account_name})")

    # Set account context for tools (per-request, not global)
    _current_account_ctx.set(account_name)

    # Load memory context
    memory_ctx = _load_memory(user_id, session_id)
    enriched_prompt = memory_ctx + prompt

    try:
        # Run LangGraph
        graph = _get_graph()
        result = await graph.ainvoke({"messages": [HumanMessage(content=enriched_prompt)]})
        response = result["messages"][-1].content

        # Save to memory
        _save_memory(user_id, session_id, prompt, response)

        # Determine agent type from tool calls
        agent_type = "supervisor"
        for msg in result["messages"]:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                tool_name = msg.tool_calls[0].get("name", "supervisor")
                agent_type = tool_name.replace("check_", "").replace("analyze_", "").replace("manage_", "").replace("search_", "")
                break

        return {"response": response, "agent_type": agent_type}

    except Exception as e:
        logger.error(f"Supervisor error: {e}", exc_info=True)
        return {"response": "An error occurred while processing your request. Please try again.", "agent_type": "error"}


@app.get("/ping")
def ping():
    """Health check endpoint — AgentCore calls this during startup."""
    return {"status": "healthy", "agent": "supervisor", "protocol": "HTTP", "port": 8080}


if __name__ == "__main__":
    logger.info("Starting MSP Supervisor Runtime on port 8080...")
    uvicorn.run(app, host="0.0.0.0", port=8080)
